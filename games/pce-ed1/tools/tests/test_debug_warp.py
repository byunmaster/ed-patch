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
        self.assertEqual([i for i in range(64) if has(3, i)], [1, 48])
        for ch in range(6):
            for i in (0, *range(28, 32), *range(39, 48)):
                self.assertFalse(has(ch, i), (ch, i))
            self.assertTrue(has(ch, 1))  # 엘아스타는 어느 장에서나 간다
            self.assertTrue(
                has(ch, 48)
            )  # 곶의동굴은 어느 장에서나 도착(어둡다 — 횃불을 쓰면 밝아진다. 원판도 같다)

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
