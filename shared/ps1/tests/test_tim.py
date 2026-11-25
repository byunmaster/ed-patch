"""TIM 파서 회귀 — **원본 없이 돈다**(합성 TIM). 🔴 `w` 는 픽셀이 아니라 16비트 워드 수다(4bpp 면 ×4)."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from shared.ps1 import tim


def _tim8(w_words, h, clut_colors=256):
    clut = struct.pack("<I4H", clut_colors * 2 + 12, 0, 480, clut_colors, 1) + b"".join(
        struct.pack("<H", 0x7FFF if i else 0) for i in range(clut_colors)
    )
    pix = struct.pack("<I4H", w_words * h * 2 + 12, 0, 0, w_words, h) + bytes(range(256)) * (
        (w_words * h * 2) // 256 + 1
    )
    pix = pix[: w_words * h * 2 + 12]
    return struct.pack("<II", 0x10, 9) + clut + pix


class TestTim(unittest.TestCase):
    def test_8bpp_가로는_워드의_2배(self):
        t = tim.parse(_tim8(16, 4))
        self.assertEqual(t["bpp"], 8)
        self.assertEqual(tim.width(t), 32)

    def test_매직이_아니면_실패(self):
        with self.assertRaises(tim.TimError):
            tim.parse(b"\x00" * 64)

    def test_블록_크기가_안_맞으면_실패(self):
        data = bytearray(_tim8(16, 4))
        i = 8 + 524  # 픽셀 블록 머리
        data[i : i + 4] = struct.pack("<I", 999)
        with self.assertRaises(tim.TimError):
            tim.parse(bytes(data))

    def test_잘리면_실패(self):
        with self.assertRaises(tim.TimError):
            tim.parse(_tim8(16, 4)[:-10])

    def test_find_all_이_매직을_규격으로_거른다(self):
        blob = b"\x10\x00\x00\x00junk" + _tim8(8, 2) + bytes(20)
        found = tim.find_all(blob)
        self.assertEqual(len(found), 1)

    def test_색_변환_STP(self):
        self.assertEqual(tim.rgba(0)[3], 0)  # 0x0000 = 투명
        self.assertEqual(tim.rgba(0x8000)[3], 255)  # STP 가 서면 불투명 검정


if __name__ == "__main__":
    unittest.main()
