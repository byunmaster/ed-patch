"""디버그 W(`debug_warp`) — 날개 목록 훅: 자리·호출 대상·분기 모양. 원본 디스크가 필요한 검사는 원본이 없으면 건너뛴다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cpu65
import debug_warp as W


class WarpHookTest(unittest.TestCase):
    def test_hook_fits_bank_tail(self):
        """훅은 뱅크 0x6F 끝 FF 196B 안."""
        hc = W.hook_code()
        self.assertLessEqual(W.HOOK_ORG - 0x8000 + len(hc), 0x2000)
        self.assertGreaterEqual(W.HOOK_ORG - 0x8000, 0x1F3C)

    def test_site_replaces_four_bytes_with_jsr_nop(self):
        s = W.hook_site_new()
        self.assertEqual(len(s), len(W.HOOK_SITE_OLD))
        self.assertEqual(s[0], 0x20)
        self.assertEqual(int.from_bytes(s[1:3], "little"), W.HOOK_ORG)
        self.assertEqual(s[3], 0xEA)

    def test_hook_never_writes_visit_flags(self):
        """진행 깃발 `$C178~$C17F` 에 쓰는 명령이 없다(STA/STZ abs $C1xx)."""
        hc = W.hook_code()
        for i in range(len(hc) - 2):
            if hc[i] in (0x8D, 0x9C):  # STA abs · STZ abs
                self.assertNotEqual(hc[i + 2], 0xC1, hc.hex())

    def test_skip_returns_to_next_index_step(self):
        hc = W.hook_code()
        self.assertIn(
            bytes(
                [
                    0xA9,
                    (W.HOOK_SKIP_TO - 1) >> 8,
                    0x48,
                    0xA9,
                    (W.HOOK_SKIP_TO - 1) & 0xFF,
                    0x48,
                    0x60,
                ]
            ),
            hc,
        )

    def test_reach_table_bits(self):
        """장별 도착 표 — 1장은 네리아항구(5)를 포함하고, 4장은 엘아스타(1)·곶의동굴(48)뿐이며, 이름 없는 번호·idx 0 은 어느 장에도 없다."""
        t = W.reach_table()
        self.assertEqual(len(t), 48)

        def has(ch, i):
            return bool(t[ch * 8 + (i >> 3)] & (1 << (i & 7)))

        self.assertTrue(has(0, 5))
        self.assertEqual([i for i in range(64) if has(3, i)], [1, 16, 17, 18, 19, 48, 53, 56])
        for ch in range(6):
            for i in (0, *range(28, 32), *range(39, 48)):
                self.assertFalse(has(ch, i), (ch, i))
            self.assertTrue(has(ch, 1))  # 엘아스타는 어느 장에서나 간다
            self.assertTrue(
                has(ch, 48)
            )  # 곶의동굴은 어느 장에서나 도착(어둡다 — 횃불을 쓰면 밝아진다. 원판도 같다)

    def test_reach_table_dungeons_11_21(self):
        """번호 50~63(구엔의탑…바니스성) — 11-21 실측: 2장은 구엔의탑(50)·시련의동굴(51), 종장은 바니스성(63)까지. 1장엔 하나도 없다."""
        t = W.reach_table()

        def has(ch, i):
            return bool(t[ch * 8 + (i >> 3)] & (1 << (i & 7)))

        self.assertTrue(has(1, 50) and has(1, 51))  # 2장(`$6B`=1)
        self.assertFalse(any(has(0, i) for i in range(50, 64)))  # 1장
        self.assertTrue(has(5, 63))  # 종장 바니스성
        self.assertFalse(has(4, 63))  # 5장엔 없다
        for ch in range(6):
            self.assertFalse(has(ch, 54), ch)  # 용의알 — 마스터 판정(날개에 등록되는 지명이 아니다)
            self.assertFalse(has(ch, 55), ch)  # 바람의탑 — 어느 장에서도 도착 안 함
        self.assertEqual([i for i in range(50, 64) if has(1, i)], [50, 51])  # 2장
        self.assertEqual([i for i in range(50, 64) if has(2, i)], [52, 53])  # 3장
        self.assertEqual([i for i in range(50, 64) if has(4, i)], [52, 57, 58])  # 5장
        self.assertEqual([i for i in range(50, 64) if has(5, i)], [52, 57, 58, 59, 60, 61, 62, 63])  # 종장

    def _hook(self, chapter, idx, flag_off, wmode=True):
        """훅을 한 번 부른다 — (올렸나, W 모드가 남았나). 호출 시점 Z=1 이면 방문 비트가 꺼진 것(원래 `BEQ` 가 보던 값)."""
        W_ORG = W.HOOK_ORG
        hc = W.hook_code()
        mem = bytearray(0x10000)
        mem[W_ORG : W_ORG + len(hc)] = hc
        mem[W.MASK_AT : W.MASK_AT + 8] = bytes(1 << i for i in range(8))
        t = W.reach_table()
        mem[W.TABLE_AT : W.TABLE_AT + len(t)] = t
        mem[W.CHAPTER] = chapter
        mem[0xFE] = idx
        if wmode:
            mem[W.WMODE], mem[W.WMODE + 1] = W.WMODE_KEY
        c = cpu65.CPU(mem)
        c.sp = 0xF0
        c.z = 1 if flag_off else 0
        sentinel = 0xFFFF
        c.push((sentinel - 1) >> 8)
        c.push((sentinel - 1) & 0xFF)
        c.pc = W_ORG
        for _ in range(2000):
            if c.pc in (sentinel, W.HOOK_SKIP_TO):
                break
            c.step()
        self.assertIn(c.pc, (sentinel, W.HOOK_SKIP_TO))
        return c.pc == sentinel, bool(mem[W.WMODE])

    def test_hook_decisions(self):
        """장 표에 있으면 방문 깃발이 꺼져 있어도 올리고, 없으면 깃발을 따른다. idx 63 도 장 표로 판정하며 W 모드를 푼다."""
        self.assertEqual(self._hook(1, 50, flag_off=True), (True, True))  # 2장 구엔의탑 — 깃발 꺼짐에도 올림
        self.assertEqual(self._hook(0, 50, flag_off=True), (False, True))  # 1장 — 표 밖 + 깃발 꺼짐 → 건너뜀
        self.assertEqual(self._hook(0, 50, flag_off=False), (False, True))  # 1장 — 표 밖 던전은 방문했어도 건너뜀(11-22: 도착 못 하는 곳 — 빈 틀에서 멈춘다)
        self.assertEqual(self._hook(3, 28, flag_off=False), (False, True))  # 4장 노부부의집(28) — 표 밖 + 방문 깃발 → 건너뜀(11-22)
        self.assertEqual(self._hook(3, 29, flag_off=False), (False, True))  # 오레아의집(29)
        self.assertEqual(self._hook(3, 14, flag_off=False), (True, True))  # 4장 세리스(14) — 마을은 앞 장 방문 마을이 그대로(마스터 11-18)
        self.assertEqual(self._hook(3, 27, flag_off=False), (True, True))  # 마을 번호 마지막(27)
        self.assertEqual(self._hook(5, 63, flag_off=True), (True, False))  # 종장 바니스성 — 표 안, 모드 풀림
        self.assertEqual(self._hook(4, 63, flag_off=True), (False, False))  # 5장 — 표 밖 + 깃발 꺼짐
        self.assertEqual(self._hook(1, 1, flag_off=True), (True, True))  # 엘아스타
        self.assertEqual(self._hook(1, 63, flag_off=False, wmode=False), (True, False))  # W 모드 아님 — 원래 깃발 그대로

    def test_hook_reads_chapter_zero_page(self):
        """장 = 영 페이지 `$6B`(`LDA zp`) — `$C1B6` 는 이어하기 직후 0 이라 못 쓴다."""
        hc = W.hook_code()
        self.assertIn(bytes([0xA5, 0x6B]), hc)

    def test_tables_follow_code(self):
        self.assertLessEqual(len(W.hook_code()), W.HOOK_CODE_ROOM)
        self.assertLessEqual(W.TABLE_AT + 48, 0xA000)

    def test_patches_have_matching_lengths(self):
        try:
            ps = W.patches()
        except Exception as e:  # 원본 디스크 없음
            self.skipTest(str(e))
        for p in ps:
            self.assertTrue(p[2] + len(p[4]) <= 2048 and len(p[3]) == len(p[4]))


class BlockedSceneTest(unittest.TestCase):
    """베르가 사령관 처치 뒤 맵(씬 41)에선 W 줄을 빨강으로 다시 그리고 W 를 고르면 무반응 — 그 밖(월드맵 `$C009`=0 · 씬 40)은 그대로."""

    def _run(self, scene, entry_label):
        org, blob, _pool, disp = W.assemble()
        a = W.code(org)
        mem = bytearray(0x10000)
        mem[org : org + len(blob)] = blob
        mem[W.DRAW] = 0x60  # 그리기 · 대기 · 먼 호출은 RTS 로 흉내
        mem[W.WAIT] = 0x60
        mem[W.FAR] = 0x60
        mem[W.SOUND] = 0x60  # 소리 드라이버 입구도 RTS — 부른 효과음 번호는 아래 `cues` 로 잡는다
        mem[W.SCENE_VAR] = scene
        mem[0x37A5] = W.ROW_W
        c = cpu65.CPU(mem)
        c.sp = 0xF0
        drawn = []
        self.cues = []
        orig = c.step

        def step():
            if c.pc == W.SOUND:
                self.cues.append(c.a)
            if c.pc == W.DRAW:
                drawn.append(
                    (
                        mem[0x8A],
                        mem[0x12] | mem[0x13] << 8,
                        bytes(mem[mem[0x10] | mem[0x11] << 8 :][:3]),
                    )
                )
            return orig()

        c.step = step
        c.run(a.labels[entry_label], ret=0xFFFF)
        return drawn, mem

    def test_wdraw_red_only_in_scene_41(self):
        drawn, _m = self._run(W.BLOCK_SCENE, "wdraw")
        self.assertEqual(drawn, [(W.RED, W.BAT_W, b"\x82\x76\x06")])
        for scene in (0, 40, 42):
            self.assertEqual(self._run(scene, "wdraw")[0], [], scene)

    def test_pmi_rows_redraw_not_e_handler(self):
        """P·M·I 행(0·1·5)은 원판이 `$64E0` 의 창 다시 그리기로 돌아온다 — 스텁 진입이 E 행 처리(`ORIG_E`)로 새면 안 된다(마스터 11-18 「P M 이 ON 으로 안 바뀌네」)."""
        for row in (0, 1, 5):
            org, blob, _pool, disp = W.assemble()
            a = W.code(org)
            mem = bytearray(0x10000)
            mem[org : org + len(blob)] = blob
            mem[W.DRAW] = mem[W.WAIT] = mem[W.FAR] = mem[W.SOUND] = 0x60
            mem[W.SCENE_VAR] = 0
            mem[0x37A5] = row
            mem[W.ORIG_E] = 0x00  # 새어 가면 BRK 처럼 모르는 옵코드/이상 동작 — 아래 PC 검사로 잡는다
            c = cpu65.CPU(mem)
            c.sp = 0xF0
            visited = []
            orig = c.step

            def step():
                visited.append(c.pc)
                if c.pc == W.FAR:  # 먼 호출은 인자 3B(뱅크·주소)를 건너뛰고 돌아온다 — 호출은 흉내만(RTS 스텁이 인자를 실행하지 않게 돌아갈 주소를 +3)
                    lo = c.m[0x2100 + ((c.sp + 1) & 0xFF)]
                    hi = c.m[0x2100 + ((c.sp + 2) & 0xFF)]
                    ret = ((hi << 8 | lo) + 3) & 0xFFFF
                    c.m[0x2100 + ((c.sp + 1) & 0xFF)] = ret & 0xFF
                    c.m[0x2100 + ((c.sp + 2) & 0xFF)] = ret >> 8
                return orig()

            c.step = step
            c.run(a.labels["disp"], ret=0xFFFF)
            self.assertNotIn(W.ORIG_E, visited, row)
            self.assertIn(a.labels["redraw"], visited, row)
            self.assertEqual(mem[W.WMODE], 0)

    def test_w_press_blocked_in_scene_41(self):
        drawn, mem = self._run(W.BLOCK_SCENE, "disp")
        self.assertEqual(
            mem[W.WMODE], 0
        )  # W 모드 암호를 세우지 않고 돌아온다(날개 목록으로 안 간다)
        self.assertEqual(drawn, [])
        self.assertEqual(self.cues, [W.CUE_DENY])  # 사용 불가 아이템과 같은 효과음(0x27)


if __name__ == "__main__":
    unittest.main()
