"""디버그 입구 — 스텁이 자리에 들고, 원래 두 명령(lda $1359 / bit $1B06)으로 끝나며, 입구 한 곳만 건드린다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import debug_patch


class DebugPatch(unittest.TestCase):
    def test_stub_fits_and_ends_with_original_instructions(self):
        s = debug_patch.stub()
        self.assertLessEqual(len(s), debug_patch.CMD_LIMIT)
        self.assertTrue(s.endswith(bytes.fromhex("AD59132C061B6B")))  # lda $1359 / bit $1B06 / rtl
        # 스텁은 뱅크 $C0 의 `$FF00`(사운드 옵션 문자열) 앞에서 끝나야 한다
        self.assertLessEqual((debug_patch.CMD_STUB & 0xFFFF) + len(s), 0xFF00)

    def test_patches_are_stub_and_one_hook_over_original_bytes(self):
        ps = debug_patch.patches()
        self.assertEqual(len(ps), 2)
        stub_addr, stub_old, stub_new = ps[0]
        self.assertEqual(stub_old, b"\xff" * len(stub_new))  # 빈 자리(0xFF)에만 쓴다
        hook_addr, hook_old, hook_new = ps[1]
        self.assertEqual(hook_addr, debug_patch.HOOK)
        self.assertEqual(hook_old, debug_patch.HOOK_OLD)
        self.assertEqual(hook_new[0], 0x22)  # JSL
        self.assertEqual(hook_new[4:], b"\xea\xea")
        self.assertEqual(int.from_bytes(hook_new[1:4], "little"), debug_patch.CMD_STUB)

    def test_key_is_gated_and_removed_extras_are_gone(self):
        s = debug_patch.stub()
        self.assertEqual(s[:3], bytes.fromhex("AD061B"))  # 열쇠 판정이 맨 앞: lda $1B06
        self.assertIn(bytes.fromhex("AD5B0BC9A5"), s)  # lda $0B5B / cmp #$A5 — 켜지지 않았으면 원판 그대로
        # 시험 롬에만 있던 전투 스킵 표지($0B59)는 제품에 없다
        self.assertNotIn(bytes.fromhex("8D590B"), s)
        self.assertNotIn(bytes.fromhex("AD590B"), s)

    def test_hold_is_one_second(self):
        self.assertEqual(debug_patch.HOLD_FRAMES, 60)
        self.assertLess(debug_patch.HOLD_STALE, debug_patch.HOLD_FRAMES)


if __name__ == "__main__":
    unittest.main()
