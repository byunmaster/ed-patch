"""BDF 로더·글리프 패킹 회귀 — 22B(16×11)와 18B(12×12 밀착) 둘 다."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import fonts
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


class TestPack18(unittest.TestCase):
    """12×12 **밀착 패킹** — 행이 바이트 경계를 안 지킨다(새턴 ED3 `KANJI12.FON`)."""

    def test_크기(self):
        bits = np.zeros((12, 12), dtype=np.uint8)
        self.assertEqual(len(fonts.pack18(bits)), 18)  # 144비트 = 18B, 남는 비트 없음

    def test_왕복(self):
        rng = np.random.default_rng(20260824)  # 고정 시드 — 빌드는 결정적이어야 한다
        for _ in range(50):
            bits = rng.integers(0, 2, (12, 12), dtype=np.uint8)
            np.testing.assert_array_equal(fonts.unpack18(fonts.pack18(bits)), bits)

    def test_행이_바이트_경계를_안_지킨다(self):
        """🔴 `pack22` 처럼 행마다 바이트를 맞추면 글자가 조용히 밀린다."""
        bits = np.zeros((12, 12), dtype=np.uint8)
        bits[1, 0] = 1  # 전체 12번 비트 → 1번 바이트의 다섯째 자리
        self.assertEqual(fonts.pack18(bits)[1], 0b0000_1000)

    def test_convert_chars_가_격자를_고른다(self):
        g22, _ = fonts.convert_chars("가", rows=11, packer=fonts.pack22)
        g18, _ = fonts.convert_chars("가", rows=12, packer=fonts.pack18, width=12)
        self.assertEqual(len(g22["가"]), 22)
        self.assertEqual(len(g18["가"]), 18)

    def test_없는_글자는_이름을_돌려준다(self):
        """⚠ 조용히 빈칸이 되면 화면에서만 사라진다."""
        _, missing = fonts.convert_chars("가\u0888", rows=12, packer=fonts.pack18, width=12)
        self.assertEqual(missing, ["\u0888"])


if __name__ == "__main__":
    unittest.main()
