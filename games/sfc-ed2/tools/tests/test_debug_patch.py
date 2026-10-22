"""시험 빌드 전용 디버그 훅 — 스텁이 자리에 들고, 원래 두 명령(lda $1359 / bit $1B06)으로 끝나며, 제품 경로는 건드리지 않는다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import debug_patch


class DebugPatch(unittest.TestCase):
    def test_stub_fits_and_ends_with_original_instructions(self):
        s = debug_patch.stub()
        self.assertLessEqual(len(s), debug_patch.STUB_LIMIT)
        self.assertTrue(s.endswith(bytes.fromhex("AD59132C061B6B")))  # lda $1359 / bit $1B06 / rtl

    def test_apply_patches_hook_only(self):
        rom = bytearray(0x200000)
        h = 0x01E306  # $C1:E306
        h2 = 0x019CE4  # $C1:9CE4
        rom[h : h + 6] = debug_patch.HOOK_OLD
        rom[h2 : h2 + 5] = debug_patch.HOOK2_OLD
        out = debug_patch.apply(bytes(rom))
        diff = [i for i in range(len(rom)) if out[i] != rom[i]]
        self.assertTrue(all(h <= i < h + 6 or debug_patch.STUB_OFF <= i < debug_patch.STUB_OFF + 0x200 or h2 <= i < h2 + 5 for i in diff))
        self.assertEqual(out[h], 0x22)  # JSL

    def test_skip_stub_branch_lands_on_normal_path(self):
        k = debug_patch.skip_stub()
        self.assertEqual(k[3:5], bytes([0xC9, 0xA5]))
        bne = 5  # `D0 rel` 위치
        self.assertEqual(k[bne], 0xD0)
        self.assertEqual(k[bne + 2 + k[bne + 1]], 0xAD)  # 분기 목적지 = normal 의 `lda $11BF`
        self.assertEqual(k[-1], 0x6B)

    def test_warp_flags_are_49_bits_in_flag_array(self):
        s = debug_patch.stub()
        self.assertEqual(len(debug_patch.WARP_FLAGS), 49)
        self.assertEqual(s.count(bytes([0x09])) >= 7, True)  # ora #mask 가 일곱 바이트에 걸쳐 있다

    def test_apply_refuses_wrong_original(self):
        with self.assertRaises(SystemExit):
            debug_patch.apply(bytes(0x200000))


if __name__ == "__main__":
    unittest.main()
