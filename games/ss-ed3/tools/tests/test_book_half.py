"""서책 반각 「」 · ' — 글리프 칸 셋이 연속이고(스텁이 코드 범위로 가른다), 줄 나눔이 닫는/여는 부호로 알고, 도안이 칸 안에 든다."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import book as B
import build_font as BF
import hangul_map as H
import patch_book_half as P


class BookHalf(unittest.TestCase):
    def test_codes_consecutive(self):
        c = P.codes()
        self.assertEqual(list(c), [c[0], c[0] + 1, c[0] + 2])

    def test_fullwidth_maps_kagi_to_half_slots(self):
        self.assertEqual((B.FULLWIDTH["「"], B.FULLWIDTH["」"]), ("｢", "｣"))
        self.assertIn("｣", B.PUNCT)
        self.assertIn("＇", B.PUNCT)
        self.assertIn("｢", B.OPEN)

    def test_glyphs_left_six_columns(self):
        for ch, rows in BF.BOOKQ.items():
            self.assertEqual(len(rows), 12, ch)
            self.assertTrue(all(len(r) == 6 for r in rows), ch)
        self.assertEqual(set(BF.BOOKQ), set(H.load_liga()) - {"⁉"})


if __name__ == "__main__":
    unittest.main()
