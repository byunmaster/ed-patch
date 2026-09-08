"""번역 단위 추출과 글리프 변환 — **원본 없이** 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text  # noqa: F401, I001  (common 보다 먼저)
import hangul_font
import script
import units


class Units(unittest.TestCase):
    def test_가나_런만_단위가_된다(self):
        # 숫자만 있는 런("12"+개행)은 단위가 아니고, 가나가 든 런은 개행·공백을 포함해 한 단위
        blk = bytes(
            [0x01, 0x02, 0xCF, 0xE3, 0xD3, 0x08, 0xCF, 0xE1, 0x11, 0x10, 0x12, 0xCF, 0x13, 0xE0]
        )
        rom = bytearray(0x100000)
        at = 0x3C000
        rom[at : at + len(blk)] = blk
        items = script.parse_region(bytes(rom), at, at + len(blk))
        us = units.units_of(items)
        self.assertEqual(len(us), 1)
        self.assertEqual(us[0][2], bytes([0x11, 0x10, 0x12, 0xCF, 0x13]))

    def test_화자는_E3_사전_뒤에서_읽는다(self):
        blk = bytes([0xE3, 0xD3, 0x08, 0xCF, 0xE1, 0x11, 0xE0])
        rom = bytearray(0x100000)
        at = 0x3C000
        rom[at : at + len(blk)] = blk
        items = script.parse_region(bytes(rom), at, at + len(blk))
        res = lambda code, idx: bytes([0x2D, 0x12, 0x1C])  # へいし
        i = next(k for k, it in enumerate(items) if it.kind == "char")
        self.assertEqual(units.speaker_before(items, i, res), "へいし")


class Glyph(unittest.TestCase):
    def test_2bpp_타일_넷은_좌상_우상_좌하_우하(self):
        # 왼쪽 위 픽셀 하나만 켠 글리프 → 타일 0 의 첫 행 평면0 = $80, 나머지 타일 평면0 = 0, 평면1 은 전부 $FF
        g = bytearray(32)
        g[0] = 0x80
        t = hangul_font.to_2bpp_tiles(bytes(g))
        self.assertEqual(len(t), 64)
        self.assertEqual(t[0], 0x80)
        self.assertTrue(all(t[i] == 0xFF for i in range(1, 64, 2)))
        self.assertTrue(all(t[i] == 0 for i in range(2, 64, 2)))

    def test_오른쪽_아래_픽셀은_넷째_타일(self):
        g = bytearray(32)
        g[31] = 0x01  # 행 15, 열 15
        t = hangul_font.to_2bpp_tiles(bytes(g))
        self.assertEqual(t[48 + 14], 0x01)


if __name__ == "__main__":
    unittest.main()
