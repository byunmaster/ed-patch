"""크레딧 자막(V20) 표 회귀 — **원본 없이 돈다**.

🔴 이 검사가 지키는 건 **표의 꼴**이다. 스텁은 항목을 `idx` 로 앞으로만 걸으며(시작 < 끝, 시작 오름차순)
   포인터를 그대로 따라간다. 표가 조금만 틀려도 게임은 **조용히 자막을 안 그리거나** 남의 자리를 읽는다 —
   빌드도 게이트도 못 본다(크레딧은 인게임에서 20 분 걸려야 나온다).
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import subtitle_stub as SS
import voice_credits as VC


def parse(t, ctab):
    n, pad = struct.unpack(">HH", t[:4])
    assert pad == 0
    ents = [struct.unpack(">III", t[4 + 12 * i : 16 + 12 * i]) for i in range(n)]
    return n, ents


class CreditsTable(unittest.TestCase):
    def setUp(self):
        _, w = SS.build_credits(SS.build()[2]["draw_line9"])
        self.ctab = w["ctab"]
        self.doc = VC.load()
        self.t = VC.blob(self.ctab, self.doc)

    def test_entries_are_ordered_and_pointers_stay_inside(self):
        n, ents = parse(self.t, self.ctab)
        self.assertEqual(n, len(VC.merged(self.doc["subs"])))  # 그림 쪽 때문에 쪼갠 항목은 합친다
        prev = -1
        for a, b, p in ents:
            self.assertLess(a, b)
            self.assertGreaterEqual(a, prev)  # 시작 오름차순 — 스텁이 앞으로만 걷는다
            prev = a
            off = p - self.ctab
            self.assertTrue(4 + 12 * n <= off < len(self.t), hex(p))
            self.assertEqual(off % 2, 0)  # 글자 포인터는 짝수(mov.w)

    def test_record_shape(self):
        n, ents = parse(self.t, self.ctab)
        for _, _, p in ents:
            off = p - self.ctab
            frames, x, y, xc, yc, xr, xcr = struct.unpack(">Hhhhhhh", self.t[off : off + 14])
            self.assertIn(frames, (0, 1, 2))  # 쪽을 못박는 값 — 0 = 게임이 정한다(`CV_FORCE`)
            self.assertTrue(-200 <= x <= 60 and -200 <= xr <= 60, (x, xr))  # 로컬 좌표(원점 = 화면 가운데)
            self.assertLess(xr, x)  # 그림 오른쪽 → 자막은 왼쪽
            self.assertTrue(40 <= y <= 110, y)
            self.assertEqual(self.t[off + 14], 0)  # 이름 줄 비움

    def test_only_the_pinned_subtitle_forces_a_side(self):
        # 마스터 10-05 — #23 만 처음부터 왼쪽 칸(그림 오른쪽 = 2). 나머지는 게임이 정한다
        n, ents = parse(self.t, self.ctab)
        forced = []
        for i, (_, _, p) in enumerate(ents):
            if struct.unpack(">H", self.t[p - self.ctab : p - self.ctab + 2])[0]:
                forced.append(i)
        self.assertEqual(len(forced), 1)

    def test_fits_the_dead_region(self):
        blob, _ = SS.build_credits(SS.build()[2]["draw_line9"], self.t)
        self.assertLessEqual(SS.CRED + len(blob), SS.STUB)

    def test_no_line_overflows_the_buffer(self):
        for s in self.doc["subs"]:
            VC.record(s, VC.H.load())  # 넘으면 SystemExit

    def test_origin_shifts_every_time(self):
        doc = dict(self.doc, origin=2.0)
        n, e0 = parse(self.t, self.ctab)
        _, e1 = parse(VC.blob(self.ctab, doc), self.ctab)
        shift = round((2.0 - float(self.doc.get("origin", 0.0))) * float(self.doc["fps"]))
        for (a0, _, _), (a1, _, _) in zip(e0, e1):
            self.assertLessEqual(abs(a1 - (a0 + shift)), 1)  # 반올림 ±1 프레임


class CreditsCode(unittest.TestCase):
    def test_assembles_with_all_labels(self):
        blob, w = SS.build_credits(SS.build()[2]["draw_line9"])
        self.assertEqual(w["cred"], SS.CRED)
        self.assertEqual(w["ctab"] % 4, 0)
        self.assertEqual(w["var"] % 4, 0)
        # 첫 명령은 r9 저장, 끝은 원래 함수로의 꼬리 점프(jmp @r1 + nop)
        self.assertEqual(blob[:2], bytes.fromhex("2f96"))
        self.assertIn(bytes.fromhex("412b0009"), blob)

    def test_patch_redirects_the_task_literal(self):
        base = SS.BASE
        data = bytearray(0x60000)
        data[SS.DEBUG_GATE - base : SS.DEBUG_GATE - base + 2] = SS.GATE_ORIG
        data[SS.STUB - base : SS.STUB - base + 8] = SS.STUB_ORIG
        data[SS.HOOK - base : SS.HOOK - base + 10] = SS.HOOK_ORIG
        data[SS.TASK_LIT - base : SS.TASK_LIT - base + 4] = struct.pack(">I", SS.TASK_ORIG)
        data[SS.HOOK2 - base : SS.HOOK2 - base + 12] = SS.HOOK2_ORIG
        data[SS.EMIT_LIT - base : SS.EMIT_LIT - base + 4] = struct.pack(">I", SS.EMIT)
        out = SS.patch(bytes(data), table_fn=lambda c: b"\x00\x00\x00\x00")
        got = struct.unpack(">I", out[SS.TASK_LIT - base : SS.TASK_LIT - base + 4])[0]
        self.assertEqual(got, SS.CRED)
        # 메인 스레드 등록 루틴 — 크레딧 글자 함수 에필로그가 우리 `cemit` 으로 점프한다
        h = out[SS.HOOK2 - base : SS.HOOK2 - base + 12]
        self.assertEqual(h[:8], bytes.fromhex("d801482b00090009"))
        self.assertTrue(SS.CRED <= struct.unpack(">I", h[8:])[0] < SS.STUB)
        # 글자 등록 호출은 `cwrap`(XA 최솟값 수집)을 거친다
        lit = struct.unpack(">I", out[SS.EMIT_LIT - base : SS.EMIT_LIT - base + 4])[0]
        self.assertTrue(SS.CRED <= lit < SS.STUB)
        # 예상과 다르면(다른 빌드) 조용히 덮지 않고 멈춘다
        data[SS.TASK_LIT - base : SS.TASK_LIT - base + 4] = b"\x00\x00\x00\x00"
        with self.assertRaises(AssertionError):
            SS.patch(bytes(data), table_fn=lambda c: b"\x00\x00\x00\x00")


class GlyphCoverage(unittest.TestCase):
    def test_a_syllable_missing_from_the_credit_font_stops_the_build(self):
        # 마스터 10-05 — 표에 없는 글자는 본 글리프로 새어 나가 깨진다. 조용히 넘기지 않는다
        sub = {"n": 0, "lines": ["쀍"]}
        with self.assertRaises(SystemExit):
            VC.record(sub, VC.table_cred())


class Centering(unittest.TestCase):
    def test_one_char_longer_line_starts_at_the_same_x(self):
        # 마스터 10-05 — 한 글자(0.5칸) 차이 줄은 시작 x 가 같다(왼쪽 기준)
        a, b = "설령 세상이 멸망한다 해도", "끝내 움직이지 않았을 게다."
        self.assertEqual(len(set(VC.pads([a, b]))), 1)

    def test_far_apart_lines_stay_centered(self):
        p = VC.pads(["쥬리오, 그리고 크리스.", "정말 잘해 주었다."])
        self.assertLess(p[0], p[1])

    def test_exact_half_goes_left(self):
        # 정확히 반 칸에 걸치면 작은 쪽(왼쪽)이다 — `round` 의 짝수 쏠림이 아니다
        self.assertEqual(VC._pad("가"), max(0, __import__("math").ceil(VC._exact("가") - 0.5)))


if __name__ == "__main__":
    unittest.main()
