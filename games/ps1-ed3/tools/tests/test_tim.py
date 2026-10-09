"""TIM 규격 계약 — 원본 없이 도는 회귀.

밟은 함정을 그대로 박는다(2026-09-03):

1. **`w` 는 픽셀이 아니라 16비트 워드 수**다 — 4bpp면 실제 가로가 `w*4`.
2. **매직만 보면 안 된다** — `blk == w*h*2 + 12` 로 검산해야 `.TI3` 가 65792×32896 으로
   통과하는 일이 없다.
3. **팔레트 0번이 비어 있는 게 흔하다** — 「0번이 기본」으로 두면 새하얀 판이 나온다.
4. **불투명한 검정은 `0x8000`** 이다 — 0 으로 쓰면 화면에서 그 자리가 뚫린다.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tim


def make(bpp, w_px, h, pal, pix, pal_h=1):
    """합성 TIM 한 장. `w_px` 는 **픽셀** 가로. `pal` 은 팔레트 전부(벌 여럿이면 이어서)."""
    words = {4: w_px // 4, 8: w_px // 2, 16: w_px}[bpp]
    mode = {4: 0, 8: 1, 16: 2}[bpp]
    pix = bytes(pix) + bytes(max(0, words * h * 2 - len(pix)))
    out = struct.pack("<II", tim.MAGIC, mode | (8 if pal else 0))
    if pal:
        out += struct.pack("<IHHHH", len(pal) * 2 + 12, 0, 0, len(pal) // pal_h, pal_h)
        out += b"".join(struct.pack("<H", c) for c in pal)
    out += struct.pack("<IHHHH", words * h * 2 + 12, 0, 0, words, h) + pix
    return out


class TestTim(unittest.TestCase):
    def test_width_is_words_not_pixels(self):
        t = tim.parse(make(4, 8, 2, [0] * 16, [0] * 4))
        self.assertEqual(t["w"], 2)
        self.assertEqual(int(tim.width(t)), 8)

    def test_block_size_is_checked(self):
        raw = bytearray(make(8, 4, 2, [0] * 256, [0] * 16))
        hdr = len(raw) - (2 * 2 * 2) - 12  # 픽셀 블록 머리 자리
        struct.pack_into("<I", raw, hdr, 0xFFFF)  # 블록 크기를 흐트러뜨린다
        with self.assertRaises(tim.TimError):
            tim.parse(bytes(raw))

    def test_find_all_rejects_false_magic(self):
        """🔴 매직만 맞는 자리가 통과하면 65792x32896 같은 값이 나온다."""
        junk = b"\x10\x00\x00\x00" + b"\xff" * 64
        self.assertEqual(tim.find_all(junk), [])

    def test_best_palette_skips_the_empty_one(self):
        pal = [0] * 16 + [0x7FFF, 0x03E0, 0x7C00, 0x001F] + [0] * 12
        raw = make(4, 4, 1, pal, [0x10, 0x32], pal_h=2)
        t = tim.parse(raw)
        self.assertEqual(tim.best_palette(t), 1, "색이 다양한 벌을 골라야 한다")

    def test_roundtrip_keeps_the_image(self):
        pal = [0x0000, 0x7FFF] + [0] * 14
        raw = make(4, 4, 2, pal, [0x10, 0x01, 0x11, 0x00])
        t = tim.parse(raw)
        img = tim.to_image(t)
        back = tim.replace(raw, t, img)
        self.assertEqual(len(back), len(raw), "길이는 절대 안 변한다")
        self.assertEqual(list(tim.to_image(tim.parse(back)).getdata()), list(img.getdata()))

    def test_size_change_is_refused(self):
        from PIL import Image

        t = tim.parse(make(4, 4, 2, [0] * 16, [0] * 4))
        with self.assertRaises(tim.TimError):
            tim.from_image(t, Image.new("RGBA", (8, 2)))

    def test_opaque_black_is_stp(self):
        """🔴 0 으로 쓰면 투명이 된다 — 화면에서 그 자리가 뚫린다."""
        self.assertEqual(tim.color15(0, 0, 0, 255), 0x8000)
        self.assertEqual(tim.color15(0, 0, 0, 0), 0x0000)


if __name__ == "__main__":
    unittest.main()
