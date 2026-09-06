"""문자표·디코더 — **원본 없이** 돈다(사전 해석기는 스텁)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text


class Table(unittest.TestCase):
    def test_글자_코드는_D0_미만_전부_있다(self):
        for c in range(0xCF):
            self.assertIn(c, text.TABLE, hex(c))

    def test_가나는_안_겹친다(self):
        kana = [v for k, v in text.TABLE.items() if 0x11 <= k <= 0x6F or 0x90 <= k <= 0xC2]
        self.assertEqual(len(kana), len(set(kana)))

    def test_기본_배치(self):
        self.assertEqual(text.TABLE[0x11], "あ")
        self.assertEqual(text.TABLE[0x3F], "ア")
        self.assertEqual(text.TABLE[0x90], "が")
        self.assertEqual("".join(text.TABLE[c] for c in (0x8B, 0x8C, 0x8D, 0x8E)), "GOLD")


class Decode(unittest.TestCase):
    def test_평문과_개행_끝(self):
        b = bytes([0x15, 0x12, 0x84, 0xCF, 0x21, 0x6F, 0x75, 0x24, 0x2F, 0x23, 0x83, 0xE0, 0x11])
        self.assertEqual(text.decode(b), "おい、\nちょっとまて。<END>")

    def test_사전과_색(self):
        res = lambda code, idx: {(0xD3, 8): bytes([0x2D, 0x12, 0x1C])}[(code, idx)]  # へいし
        b = bytes([0xE3, 0xD3, 0x08, 0xCF, 0xE1, 0x11, 0xE0])
        self.assertEqual(text.decode(b, res), "<COLOR_C>{へいし}\n<COLOR_POP>あ<END>")

    def test_사전_해석기_없으면_코드로_남긴다(self):
        self.assertEqual(text.decode(bytes([0xD0, 0x03, 0xE0])), "<D0 03><END>")

    def test_제어_인자_길이(self):
        # ee = 3바이트 네이티브 호출, f9 = 3, fa = 2 — 그 뒤 글자가 살아남아야 한다
        b = bytes(
            [
                0xEE,
                0x88,
                0xF2,
                0x05,
                0x11,
                0xF9,
                0x01,
                0x02,
                0x03,
                0x12,
                0xFA,
                0x10,
                0x00,
                0x13,
                0xE0,
            ]
        )
        self.assertEqual(
            text.decode(b), "<CALL_NATIVE 88f205>あ<CALL_ABS 010203>い<JUMP 1000>う<END>"
        )

    def test_span_은_END_마다_끊는다(self):
        rom = bytes([0x11, 0xE0, 0x12, 0x13, 0xE4, 0x14])
        segs = text.parse_span(rom, 0, 6)
        self.assertEqual(
            [r for _, r in segs], [bytes([0x11, 0xE0]), bytes([0x12, 0x13, 0xE4]), bytes([0x14])]
        )


if __name__ == "__main__":
    unittest.main()
