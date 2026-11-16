"""디버그 W(`debug_warp`) — 날개 목록 훅: 자리·호출 대상·분기 모양. 원본 디스크가 필요한 검사는 원본이 없으면 건너뛴다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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
        self.assertIn(bytes([0xA9, (W.HOOK_SKIP_TO - 1) >> 8, 0x48, 0xA9, (W.HOOK_SKIP_TO - 1) & 0xFF, 0x48, 0x60]), hc)

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
            self.assertTrue(has(ch, 48))  # 곶의동굴은 어느 장에서나 도착(어둡다 — 횃불을 쓰면 밝아진다. 원판도 같다)

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


if __name__ == "__main__":
    unittest.main()
