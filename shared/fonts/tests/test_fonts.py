"""BDF 로더·22B 패킹 회귀."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from fonts import CELL, ROWS, WIDTH, convert_chars, galmuri, pack22


class TestBdf(unittest.TestCase):
    def test_galmuri11_로드(self):
        f = galmuri()
        self.assertEqual(f.ascent, 14)
        self.assertGreater(len(f.glyphs), 3000)

    def test_한글_획이_셀_안에_든다(self):
        """dy 보정이 어긋나면 위아래가 잘린다 — 11행 격자에 다 들어와야 한다."""
        f = galmuri()
        for ch in "가힣뷁왕자":
            b = f.bits(ch, dy=-3)
            self.assertTrue(b.any(), ch)
            ys = np.nonzero(b)[0]
            self.assertGreaterEqual(ys.min(), 0, ch)
            self.assertLess(ys.max(), ROWS, ch)
            self.assertLessEqual(np.nonzero(b)[1].max(), CELL, ch)

    def test_pack22_길이와_비트순서(self):
        bits = np.zeros((ROWS, WIDTH), np.uint8)
        bits[0, 0] = bits[1, 15] = 1
        g = pack22(bits)
        self.assertEqual(len(g), 22)
        self.assertEqual(g[0:2], b"\x80\x00")  # MSB 우선
        self.assertEqual(g[2:4], b"\x00\x01")

    def test_convert_chars_는_없는_글자를_알린다(self):
        """폰트에 없는 글자는 **빈 글리프**가 된다 — 조용히 넘기면 화면에 공백이 뜬다."""
        out, missing = convert_chars("가" + chr(0x530))  # 아르메니아 미할당 — Galmuri 에 없다
        self.assertEqual(len(out["가"]), 22)
        self.assertEqual(missing, [chr(0x530)])


if __name__ == "__main__":
    unittest.main()
