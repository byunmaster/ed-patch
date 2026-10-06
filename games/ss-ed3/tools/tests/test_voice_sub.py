"""음성 자막 칸 계획 회귀 — **원본 없이 돈다**(가짜 맵 바이트).

🔴 이 검사가 지키는 건 **시간**이다. 대기 `FF 35 n` 을 쪼개 칸 사슬을 만들 때 총 프레임이
   그대로여야 장면이 안 늘어지고(음성은 제 속도로 흐른다), 서명 칸마다 최소 한 프레임
   머물러야 스텁이 PC 를 본다. 바이트가 그럴듯해도 이게 틀리면 **자막만 밀린다** — 빌드도
   게이트도 못 본다.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import subtitle_stub as SS
import voice_sub as VS


def wait_frames(op):
    assert op[:2] == b"\xff\x35"
    return struct.unpack(">H", op[2:4])[0] + 1


def follow(tail, n, entry, ret):
    """칸 사슬을 걷는다 → `(총 대기 프레임, [서명 칸의 (머무는 프레임, 글자 오프셋)])`.

    `tail` 은 옛 파일 끝(`n`)부터 붙는 꼬리다(칸 정렬 패딩 포함).
    """
    total, seen, at = 0, [], entry
    while at != ret:
        s = tail[at - n : at - n + SS.SLOT]
        body = s[: SS.MAGIC_OFF]
        frames = 0
        p = 0
        while body[p : p + 2] == b"\xff\x35":
            frames += wait_frames(body[p : p + 4])
            p += 4
        if body[p : p + 2] == b"\xff\x24":  # 가짜 맵의 앞 옵코드(4B) 하나
            p += 4
            while body[p : p + 2] == b"\xff\x35":
                frames += wait_frames(body[p : p + 4])
                p += 4
        assert body[p : p + 2] == VS.GOTO, body.hex()
        nxt = struct.unpack(">I", body[p + 2 : p + 6])[0] - VS.BASE
        if s[SS.MAGIC_OFF : SS.MAGIC_OFF + 4] == struct.pack(">I", SS.MAGIC):
            seen.append((frames, struct.unpack(">I", s[SS.PTR_OFF :])[0] - VS.BASE))
        total += frames
        at = nxt
    return total, seen


class Chain(unittest.TestCase):
    def setUp(self):
        #   가짜 맵 — 0x100 에 `FF 24 00 00 · FF 35 00 d2 · FF 35 01 0e`(4 + 211 + 271 프레임)
        raw = bytearray(b"\x11" * 0x100)
        raw += bytes.fromhex("ff240000ff3500d2ff35010e") + b"\x22" * 100
        self.raw = bytes(raw)
        self.site = {"off": 0x100, "len": 12}
        self.table = None

    def hooks(self, *delays):
        return [dict(self.site, delay=d, lines=[f"줄{i}"], dur=1.0) for i, d in enumerate(delays)]

    def test_total_wait_is_preserved_and_each_sub_stays_a_frame(self):
        hooks = self.hooks(34, 238, 418)
        tail, patches = VS.plan(self.raw, hooks, self.table)
        self.assertEqual([p[0] for p in patches], [0x100])
        entry = struct.unpack(">I", patches[0][1][2:])[0] - VS.BASE
        total, seen = follow(tail, len(self.raw), entry, 0x100 + 12)
        self.assertEqual(total, 211 + 271)
        self.assertEqual([f for f, _ in seen], [238 - 34, 418 - 238, 482 - 418])
        #   글자 포인터는 칸들 뒤 글자 표를 순서대로 가리킨다
        self.assertEqual(len({o for _, o in seen}), 3)
        self.assertTrue(all(o % 2 == 0 for _, o in seen))

    def test_delay_zero_without_prefix_starts_in_a_signed_slot(self):
        raw = self.raw[:0x100] + self.raw[0x104:]  # 앞 옵코드를 뺀다 → 대기 둘만
        site = {"off": 0x100, "len": 8}
        hooks = [
            dict(site, delay=0, lines=["a"], dur=1.0),
            dict(site, delay=100, lines=["b"], dur=1.0),
        ]
        tail, patches = VS.plan(raw, hooks, None)
        start = -(-len(raw) // SS.SLOT) * SS.SLOT
        entry = struct.unpack(">I", patches[0][1][2:])[0] - VS.BASE
        self.assertEqual(entry, start)  # 첫 칸이 곧 서명 칸
        total, seen = follow(tail, len(raw), entry, 0x108)
        self.assertEqual(total, 482)
        self.assertEqual([f for f, _ in seen], [100, 382])

    def test_single_hook_without_delay_keeps_the_old_shape(self):
        hooks = [dict(self.site, lines=["a"], dur=1.0)]
        tail, _ = VS.plan(self.raw, hooks, None)
        start = -(-len(self.raw) // SS.SLOT) * SS.SLOT
        s = tail[start - len(self.raw) :][: SS.SLOT]
        self.assertEqual(s[:12], self.raw[0x100:0x10C])
        self.assertEqual(s[12:16], VS.WAIT1)
        self.assertEqual(s[16:22], VS.GOTO + struct.pack(">I", VS.BASE + 0x10C))

    def test_rejects_delay_past_the_wait(self):
        with self.assertRaises(SystemExit):
            VS.plan(self.raw, self.hooks(10, 482), None)

    def test_rejects_delay_where_nothing_waits(self):
        raw = self.raw[:0x100] + bytes.fromhex("ff23070000a7001a") + self.raw[0x108:]
        with self.assertRaises(SystemExit):
            VS.plan(raw, [{"off": 0x100, "len": 8, "delay": 5, "lines": ["a"], "dur": 1.0}], None)

    def test_entry_carries_face_name_and_body(self):
        e = VS.entry({"off": 0, "lines": ["a", "b"], "who": "n", "speaker": 1, "dur": 1.0}, None)
        self.assertEqual(struct.unpack(">HHH", e[:6]), (60, 1, 0))
        self.assertEqual(e[6:], b"n\x00a\x00b\x00\x00\x00")  # 이름·줄·줄·끝 + 짝수 채움
        #   맵 이름표(≥0x14) 는 얼굴이 없다 · `face: null` 도 없음 · 닫는 칸은 얼굴 없음+빈 이름
        e = VS.entry({"off": 0, "lines": ["a"], "who": "n", "speaker": 0x15, "dur": 1.0}, None)
        self.assertEqual(struct.unpack(">HH", e[2:6]), (VS.NO_FACE, 0))
        e = VS.entry({"off": 0, "lines": ["a"], "speaker": 0, "face": None, "dur": 1.0}, None)
        self.assertEqual(struct.unpack(">HH", e[2:6]), (VS.NO_FACE, 0))
        e = VS.entry({"off": 0, "lines": [], "who": "n"}, None)
        self.assertEqual(e, bytes.fromhex("0000ffff0000") + b"\x00\x00")
        #   이름 줄이 있으면 본문은 둘까지
        with self.assertRaises(SystemExit):
            VS.entry({"off": 0, "lines": ["a", "b", "c"], "who": "n", "dur": 1.0}, None)
        VS.entry({"off": 0, "lines": ["a", "b", "c"], "dur": 1.0}, None)

    def test_same_speaker_swaps_text_instead_of_reopening(self):
        """같은 화자가 이어지면 창은 그대로 두고 글만 **교체**한다(스크롤 아님) — 앞 칸은 「다음 칸까지」(0) 로 붙잡힌다."""
        hooks = [
            {"off": 0x10, "len": 8, "lines": ["1"], "who": "n", "speaker": 1, "dur": 1.0},
            {"off": 0x20, "len": 8, "lines": ["2"], "who": "n", "speaker": 1, "dur": 1.0},
            {"off": 0x30, "len": 8, "lines": ["3"], "who": "n", "speaker": 1, "dur": 1.0},
            {"off": 0x40, "len": 8, "lines": ["4"], "who": "m", "speaker": 2, "dur": 1.0},
            {
                "off": 0x50,
                "len": 8,
                "lines": ["5"],
                "who": "m",
                "speaker": 2,
                "dur": 1.0,
                "new": True,
            },
        ]
        VS.link(hooks, range(len(hooks)))
        #   앞 줄을 싣지 않는다 — 각 칸은 자기 줄만(교체)
        self.assertEqual([h["_body"] for h in hooks], [["1"], ["2"], ["3"], ["4"], ["5"]])
        self.assertEqual([bool(h.get("_hold")) for h in hooks], [True, True, False, False, False])
        #   붙잡힌 칸은 표시 프레임이 0 이다
        self.assertEqual(struct.unpack(">H", VS.entry(hooks[0], None)[:2])[0], 0)
        self.assertEqual(struct.unpack(">H", VS.entry(hooks[2], None)[:2])[0], 60)

    def test_gap_across_different_slots_closes_the_window(self):
        """자리(`off`)가 달라도 `_t` 로 빈 시간을 잰다 — `HOLD_GAP` 을 넘으면 창을 닫고 새로 띄운다(마스터 10-07, V17 허크)."""
        hooks = [
            {"off": 0x10, "len": 8, "lines": ["1"], "who": "n", "speaker": 1, "dur": 1.65, "_t": "29.2초"},
            {"off": 0x20, "len": 8, "lines": ["2"], "who": "n", "speaker": 1, "dur": 1.0, "_t": "32.8초"},  # 빈 시간 1.95s
            {"off": 0x30, "len": 8, "lines": ["3"], "who": "n", "speaker": 1, "dur": 1.0, "_t": "33.9초"},  # 빈 시간 0.1s
        ]
        VS.link(hooks, range(len(hooks)))
        self.assertEqual([bool(h.get("_hold")) for h in hooks], [False, True, False])

    def test_gap_unknown_without_time_label_keeps_old_behavior(self):
        hooks = [
            {"off": 0x10, "len": 8, "lines": ["1"], "who": "n", "speaker": 1, "dur": 1.0},
            {"off": 0x20, "len": 8, "lines": ["2"], "who": "n", "speaker": 1, "dur": 1.0},
        ]
        VS.link(hooks, range(len(hooks)))
        self.assertTrue(hooks[0].get("_hold"))

    def test_close_slot_breaks_the_scroll(self):
        """닫는 칸·미리 싣기에서 사슬이 끊긴다 — 창이 없어졌는데 이어 붙이면 안 된다."""
        hooks = [
            {"off": 0x10, "len": 8, "lines": ["1"], "who": "n", "speaker": 1, "dur": 1.0},
            {"off": 0x20, "len": 8, "lines": [], "who": "n"},
            {"off": 0x30, "len": 8, "lines": ["3"], "who": "n", "speaker": 1, "dur": 1.0},
        ]
        VS.link(hooks, range(len(hooks)))
        self.assertEqual(hooks[2]["_body"], ["3"])
        self.assertFalse(hooks[0].get("_hold"))

    def test_preload_list_is_collected_per_scene(self):
        doc = {
            "S": {
                "map": "M",
                "hooks": [
                    {"off": 0x10, "len": 8, "preload": True},
                    {"off": 0x20, "len": 8, "lines": ["a"], "speaker": 1, "dur": 1.0},
                    {"off": 0x30, "len": 8, "lines": ["b"], "speaker": 0, "expr": 2, "dur": 1.0},
                    {"off": 0x40, "len": 8, "lines": ["c"], "speaker": 0x15, "dur": 1.0},
                ],
            }
        }
        hooks = VS.by_map(doc)["M"]
        e = VS.entry(hooks[0], None)
        self.assertEqual(e, bytes.fromhex("ffff0000000200010000ffff0000"))
        #   얼굴을 쓰는데 미리 싣기 자리가 없으면 실패 · 미리 싣기 칸은 혼자여야 한다
        doc["S"]["hooks"].pop(0)
        with self.assertRaises(SystemExit):
            VS.by_map(doc)
        doc["S"]["hooks"].insert(0, {"off": 0x20, "len": 8, "preload": True})
        with self.assertRaises(SystemExit):
            VS.by_map(doc)

    def test_face_combos_beyond_the_engine_cache_fail(self):
        """(얼굴, 표정) 조합이 엔진 캐시 8 칸을 넘으면 실패한다 — 밀려난 조합의 조회가 연쇄로 얼굴을 지운다."""

        def scene(n):
            hooks = [{"off": 0x10, "len": 8, "preload": True}]
            for k in range(n):  # 쥬리오(0) 표정 0..n-1 — 서로 다른 조합 n 종
                hooks.append(
                    {"off": 0x20 + 8 * k, "len": 8, "lines": ["a"], "speaker": 0, "expr": k, "dur": 1.0}
                )
            return {"S": {"map": "M", "hooks": hooks}}

        VS.by_map(scene(VS.FACE_CACHE))  # 8 종은 된다
        with self.assertRaises(SystemExit):
            VS.by_map(scene(VS.FACE_CACHE + 1))

    def test_stub_fits_and_hook_is_a_jump(self):
        stub, hook, where = SS.build()
        self.assertLessEqual(SS.STUB + len(stub), SS.STUB_END)
        self.assertEqual(hook, struct.pack(">HHH I", 0xD801, 0x482B, 0x0009, SS.STUB))
        self.assertEqual(where["flag"] % 4, 0)
        #   변수 표 — FACE_ID 는 「없음」으로 시작해야 첫 얼굴이 뜬다 · NOFACE 상수 쌍
        var = where["flag"] - SS.STUB
        self.assertEqual(
            stub[var + SS.V_FACE_ID : var + SS.V_NOFACE + 4], bytes.fromhex("ffff0000ffff0000")
        )
        self.assertEqual(stub[var + SS.VAR_LEN : var + SS.VAR_LEN + 4], bytes.fromhex("00000000"))


class ClockScene(unittest.TestCase):
    """시계 장면 — arm 칸 하나 + 4 정렬 시계 표 + 항목 글자(칸·사슬 없음)."""

    def setUp(self):
        raw = bytearray(b"\x11" * 0x100)
        raw += bytes.fromhex("ff070000000000000000000000000000") + b"\x22" * 100  # FF 07 (14B)
        self.raw = bytes(raw)
        ent = {
            "map": "MAP999",
            "clock": {"off": 0x100, "len": 14, "origin": 0.5},
            "hooks": [],
            "items": [
                {"t": 3.0, "who": "쥬리오", "lines": ["하나"], "dur": 2.0, "face": None},
                {"t": 7.5, "who": "크리스", "lines": ["둘", "셋"], "dur": 1.5, "face": None},
            ],
        }
        self.hooks = VS.by_map({"V99": ent})["MAP999"]

    def test_arm_slot_points_at_an_aligned_clock_table_with_absolute_frames(self):
        tail, patches = VS.plan(self.raw, self.hooks)
        n = len(self.raw)
        self.assertEqual(len(patches), 1)  # 후킹 지점은 arm 하나뿐
        start = -(-n // VS.SLOT) * VS.SLOT
        slot = tail[start - n : start - n + VS.SLOT]
        self.assertEqual(slot[SS.MAGIC_OFF : SS.MAGIC_OFF + 4], struct.pack(">I", SS.MAGIC))
        ptr = struct.unpack(">I", slot[SS.PTR_OFF :])[0] - VS.BASE
        self.assertEqual(ptr % 4, 0)  # 표는 mov.l 로 항목 주소를 읽는다
        tb = tail[ptr - n :]
        self.assertEqual(struct.unpack(">HH", tb[:4]), (VS.CLOCK_MAGIC, 2))
        got = []
        for i in range(2):
            fr, z, addr = struct.unpack(">HHI", tb[4 + 8 * i : 12 + 8 * i])
            self.assertEqual(z, 0)
            got.append((fr, addr - VS.BASE))
        self.assertEqual([g[0] for g in got], [round(3.5 * VS.CLOCK_FPS), round(8.0 * VS.CLOCK_FPS)])  # 원점 +0.5초
        #   각 항목 글자는 `<프레임 수> <얼굴> <표정>` 으로 시작한다 — 마지막은 닫힘(`dur`) 이 있다
        for fr, off in got:
            frames, face, _ = struct.unpack(">HHH", tail[off - n : off - n + 6])
            self.assertEqual(face, VS.NO_FACE)
            self.assertGreaterEqual(frames, 0)

    def test_last_item_must_close_itself(self):
        self.hooks[-1]["_hold"] = True  # 붙잡으면 창이 안 닫힌다
        with self.assertRaises(SystemExit):
            VS.plan(self.raw, self.hooks)


if __name__ == "__main__":
    unittest.main()
