"""가게 목록 이름 칸 채우기 루프 — 홀수 바이트 이름(반각 공백 포함)에서 무한 루프가 나지 않게 `beq` → `bcs` 로 고쳤는지 본다(10-24)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import common
import patches


class ShopPad(unittest.TestCase):
    def test_loop_exit_is_bcs(self):
        hit = [p for p in patches.PATCHES if p[0] == 0xC0DD37]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0][1], bytes([0xF0]))  # 원본: cpy #$11 / beq
        self.assertEqual(hit[0][2], bytes([0xB0]))  # bcs — 색인이 짝수로 떨어져도 끝난다

    @unittest.skipUnless(common.ORIG_ROM.exists(), "원본 롬 없음")
    def test_original_context(self):
        o = common.snes2off(0xC0DD35)
        self.assertEqual(common.rom_bytes()[o : o + 4], bytes.fromhex("C011F006"))  # cpy #$11 · beq +6


if __name__ == "__main__":
    unittest.main()
