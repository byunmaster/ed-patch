"""원문 대본 읽기(`jptext`) · 장 제목 띠(`chapter`) — 원본 없이 돈다(바이트는 실측에서 옮긴 짧은 조각)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chapter
import font
import jptext

L0 = bytes.fromhex("a0a0a08f988fcda095bd9861c593fa8158a0a0a0")  # 서장 줄(원문)
L5 = bytes.fromhex("a0a08f498fcda08b46d8a4bfbcc38af396 5da0".replace(" ", ""))  # 종장 줄


class Jp(unittest.TestCase):
    def test_히라가나_가타카나_탁음(self):
        self.assertEqual(jptext.decode(bytes([0xB1, 0xB2])), "あい")
        self.assertEqual(jptext.decode(bytes([0x0E, 0xB1, 0xB2, 0x0F])), "{0E}アイ{0F}")
        self.assertEqual(jptext.decode(bytes([0x6B, 0x6E, 0x65])), "だでご")  # $61~ 탁음 표

    def test_제어_인자(self):
        self.assertEqual(jptext.decode(bytes([0x11, 0x33, 0x30, 0xB1])), "{11 33 30}あ")
        self.assertEqual(jptext.decode(bytes([0x10, 0x30, 0xB1])), "{10 30}あ")

    def test_sjis_한자(self):
        self.assertEqual(jptext.decode(bytes.fromhex("8f988fcd")), "序章")


class Chapter(unittest.TestCase):
    def test_원문_줄이_읽힌다(self):
        self.assertIn("平和な日々", jptext.decode(L0).replace("　", ""))

    def test_모든_줄이_14칸(self):
        orig = L0 + b"\x00" + L5 + b"\x00" + (L0 + b"\x00") * 4
        self.assertTrue(chapter.is_chapter_chunk(orig))
        t = font.GlyphTable()
        for l in chapter.lines(orig, t):
            px, k = 0, 0
            while k < len(l):  # `a0` 12px · `60` 4px · 리드 F0~ 두 바이트 12px
                if l[k] == chapter.SPACE:
                    px, k = px + chapter.SPACE_PX, k + 1
                elif l[k] == chapter.PAD:
                    px, k = px + chapter.CELL_PX, k + 1
                else:
                    px, k = px + chapter.CELL_PX, k + 2
            self.assertEqual(px, chapter.BAND_PX)


if __name__ == "__main__":
    unittest.main()
