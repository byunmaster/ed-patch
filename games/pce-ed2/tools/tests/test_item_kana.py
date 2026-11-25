"""항목 토큰 가나 잔존 검사 — 합성 바이트(원본 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_item_kana as c


class Kana(unittest.TestCase):
    def test_번역한_줄의_가나_인자는_걸린다(self):
        self.assertEqual(
            c.kana_args(bytes.fromhex("0c1dcaf9240d")), [0xCA]
        )  # 1D CA 뒤 한글 글리프(F9 24)

    def test_채움_FF_가_껴도_한글로_본다(self):
        self.assertEqual(c.kana_args(bytes.fromhex("0c1dcafff9240d")), [0xCA])

    def test_빈_칸이면_통과(self):
        self.assertEqual(c.kana_args(bytes.fromhex("0c1d60f924")), [])

    def test_번역_안_한_줄은_검사_밖(self):
        self.assertEqual(c.kana_args(bytes.fromhex("0c1dca0d")), [])  # 한글 글리프 없음

    def test_두_바이트_글자_안의_1D_는_제어가_아니다(self):
        self.assertEqual(c.kana_args(bytes.fromhex("f21dca")), [])


if __name__ == "__main__":
    unittest.main()
