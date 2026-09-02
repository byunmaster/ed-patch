"""폰트 기하 계약 — 원본 없이 도는 회귀.

밟은 함정: **자리를 「폰트다워 보이는 밀도」로 찾으려다 한 밤을 태웠다**(후보 2,611건이
전부 그림이었다). 답은 코드에 있었다 — `ED3.EXE` 0x80018AB4 의 `코드×18 + 0x8009E170`.
그래서 여기서는 **그 상수들과 패킹**을 박는다. 하나라도 흔들리면 글자가 통째로 밀린다.
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import font


class TestFontGeometry(unittest.TestCase):
    def test_constants(self):
        """디스어셈블로 읽은 값 — 바꾸려면 그 코드를 다시 읽어야 한다."""
        self.assertEqual(font.FONT_RAM, 0x8009E170)
        self.assertEqual(font.GLYPH_BYTES, 18)
        self.assertEqual(font.FONT_OFF, 0x08E970)
        self.assertEqual((font.ROWS, font.CELL), (12, 12))
        # 18바이트 = 12행 × 12비트 밀착 패킹
        self.assertEqual(font.ROWS * font.CELL, font.GLYPH_BYTES * 8)

    def test_pack_roundtrip(self):
        rnd = np.random.default_rng(7)
        for _ in range(50):
            bits = rnd.integers(0, 2, size=(12, 12), dtype=np.uint8)
            buf = bytearray(font.FONT_OFF + 18 * 4)
            font.write_glyph(buf, 0, bits)
            back = font.read_glyph(bytes(buf), 0)
            self.assertTrue((back == bits).all())

    def test_write_touches_only_its_slot(self):
        """🔴 글리프 하나를 쓰면 **그 18바이트만** 바뀐다 (이웃이 밀리면 전부 틀린다)."""
        buf = bytearray(b"\xaa" * (font.FONT_OFF + 18 * 5))
        before = bytes(buf)
        font.write_glyph(buf, 3, np.ones((12, 12), dtype=np.uint8))
        o = font.FONT_OFF + 3 * 18
        self.assertEqual(bytes(buf[:o]), before[:o])
        self.assertEqual(bytes(buf[o + 18 :]), before[o + 18 :])
        self.assertEqual(bytes(buf[o : o + 18]), b"\xff" * 18)

    def test_hangul_glyph_fits_cell(self):
        g = font.hangul_glyph("한")
        self.assertEqual(g.shape, (12, 12))
        self.assertGreater(int(g.sum()), 10)  # 빈 글리프가 아니다
        self.assertLess(int(g.sum()), 120)


if __name__ == "__main__":
    unittest.main()
