"""나눈 글리프 — 커맨드 창 「시 스 템」(마스터 판정 2026-09-27). 원본 없이 돈다.

계약: 두 조각을 붙이면 **그 글자의 도트 그대로**를 반 칸 민 것이다(새로 그리지 않는다).
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import font


class TestSplitGlyph(unittest.TestCase):
    def test_halves_rejoin_to_the_original_dots(self):
        for left, right in (("", ""),):
            base = font.SPLIT[left][0]
            self.assertEqual(font.SPLIT[right][0], base)
            joined = np.hstack([font.glyph_bits(left), font.glyph_bits(right)])
            g = np.asarray(font.hangul_glyph(base), dtype=np.uint8)
            s = font.SPLIT_SHIFT
            np.testing.assert_array_equal(joined[:, s : s + g.shape[1]], g)
            self.assertEqual(int(joined.sum()), int(g.sum()), "잘리면서 도트가 빠졌다")

    def test_each_half_fits_one_cell(self):
        for ch in font.SPLIT:
            self.assertEqual(font.glyph_bits(ch).shape[1], font.CELL)


if __name__ == "__main__":
    unittest.main()
