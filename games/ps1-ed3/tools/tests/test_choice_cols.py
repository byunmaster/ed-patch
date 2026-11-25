"""선택지 창 열 — 가장 긴 항목 px → 맞춤 열(ps1-ed4 실측 12N−6px, 11-06)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import choice_cols as C


class ChoiceCols(unittest.TestCase):
    def test_need_cols(self):
        self.assertEqual(C.need_cols(36), 4)  # 「아니요」 36px → (36+6)/12 올림
        self.assertEqual(C.need_cols(12), 2)  # 최소 2열
        self.assertEqual(C.need_cols(192), 17)  # 12N−6 ≥ 192 인 최소 N
        self.assertEqual(C.need_cols(10_000), C.MAX_COLS)  # x = 148−6×열 이 음수가 되지 않게

    def test_item_px_counts_every_glyph_as_a_cell(self):
        self.assertEqual(C.item_px("코인을 사고 싶다"), 9 * 12)  # 공백도 온칸(11-06 촬영)
        self.assertEqual(C.need_cols(C.item_px("예")), 2)
        self.assertEqual(C.need_cols(C.item_px("아니요")), 4)  # 글자 수 + 1 열


if __name__ == "__main__":
    unittest.main()
