"""글리프 자리 정본·폰트 쓰기 회귀 — **원본 없이 돈다**. 🔴 코드가 폰트 밖이면 전개표·문자열을 덮어 대사창 전체가 색색 잡음이 된다."""

import unittest

import _path  # noqa: F401
import common
import font
import hangul
import numpy as np
import textenc


class TestMap(unittest.TestCase):
    def test_정본_무결성(self):
        t = hangul.load()
        self.assertEqual(len(t), 58)
        self.assertEqual(len(set(t.values())), 58)
        kana = textenc.kana_map()
        self.assertFalse(set(t.values()) & set(kana), "한글 자리가 카나 블록을 덮는다")
        self.assertTrue(all(0 <= c < font.font_slots() for c in t.values()))

    def test_인코딩(self):
        t = {"가": 1900, " ": 610}
        self.assertEqual(hangul.encode("가 あ", t), [1900, 610, 64])  # 카나는 원본 코드

    def test_모르는_글자는_조용히_안_뺀다(self):
        with self.assertRaises(KeyError):
            hangul.encode("뷁", {"가": 1})


class TestFont(unittest.TestCase):
    def test_폰트_칸수는_코드에_적힌_값(self):
        self.assertEqual(font.font_slots(), 1936)
        self.assertEqual(font.font_off(), 0x80070BD4 - common.EXE_TADDR + common.EXE_HDR)

    def test_글리프_왕복(self):
        exe = bytearray(font.font_off() + font.font_slots() * font.GLYPH_BYTES)
        bits = np.zeros((12, 12), dtype=np.uint8)
        bits[0, 0] = bits[3, 5] = bits[10, 11] = 1
        font.write_glyph(exe, 5, bits)
        got = font.read_glyph(bytes(exe), 5)
        self.assertTrue((got[:11] == bits[:11]).all())

    def test_몸통은_1행부터_저장된다(self):
        exe = bytearray(font.font_off() + font.font_slots() * font.GLYPH_BYTES)
        bits = np.zeros((12, 12), dtype=np.uint8)
        bits[0, :] = 1
        font.write_glyph(exe, 0, bits)
        raw = bytes(exe[font.font_off() : font.font_off() + 18])
        self.assertEqual(raw[:1], b"\x00")  # 저장 격자 0행은 비고(top=1) 화면 0행은 1행에 앉는다
        self.assertNotEqual(raw, bytes(18))

    def test_폰트_밖_코드는_실패(self):
        exe = bytearray(font.font_off() + font.font_slots() * font.GLYPH_BYTES + 100)
        with self.assertRaises(ValueError):
            font.write_glyph(exe, font.font_slots(), np.zeros((12, 12)))

    def test_한글_글리프는_무손실로_뽑힌다(self):
        g = font.hangul_glyph("가")
        self.assertEqual(g.shape[0], 12)
        self.assertGreater(int(g.sum()), 5)
        self.assertTrue((font.hangul_glyph("가") == g).all())  # 결정적


if __name__ == "__main__":
    unittest.main()
