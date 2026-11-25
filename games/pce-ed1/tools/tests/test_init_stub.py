"""init 스텁 지우개 — 11-07: 뱅크 0x69 +0x1852~ 는 원판이 RAM 변수로 쓰는 구간이라 스텁이 끝나기 전에 자기 자리를 0 으로 되돌리고 진입 JSR 도 원판 값으로 돌려놓는다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hook


class InitStubEraser(unittest.TestCase):
    def test_length_fits_loop(self):
        self.assertLessEqual(len(hook.init_stub()), 128)  # DEX/BPL 루프 한계

    def test_eraser_ends_with_orig_entry(self):
        s = hook.init_stub()
        self.assertEqual(s[-3:], bytes([0x4C, hook.ORIG_INIT & 0xFF, hook.ORIG_INIT >> 8]))

    def test_eraser_covers_whole_stub_and_restores_entry(self):
        s = hook.init_stub()
        er = s[-hook.ERASER_LEN :]
        self.assertEqual(er[0], 0xA2)
        self.assertEqual(er[1] + 1, len(s))  # LDX #len-1 — 코드+자료 전체를 지운다
        self.assertEqual(er[2:5], bytes([0x9E, hook.STUB_ADDR & 0xFF, hook.STUB_ADDR >> 8]))
        lo = hook.ENTRY_JSR_OPERAND
        self.assertIn(bytes([0x8D, lo & 0xFF, lo >> 8]), er)
        self.assertIn(bytes([0x8D, (lo + 1) & 0xFF, (lo + 1) >> 8]), er)

    def test_eraser_copy_source_is_inside_stub(self):
        s = hook.init_stub()
        j = s.rindex(bytes([0x73]), 0, len(s) - hook.ERASER_LEN)  # 마지막 TII = 지우개 복사
        src = s[j + 1] | s[j + 2] << 8
        self.assertEqual(src, hook.STUB_ADDR + len(s) - hook.ERASER_LEN)
        self.assertEqual(s[j + 3] | s[j + 4] << 8, hook.ERASER_ADDR)


if __name__ == "__main__":
    unittest.main()
