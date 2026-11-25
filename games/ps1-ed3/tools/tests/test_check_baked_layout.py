"""구운 조판 전수 검사기의 양성 대조 — 축마다 일부러 깬 창을 넣어 걸리는지, 멀쩡한 창은 안 걸리는지."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from check_baked_layout import window_problems

W = 24


def axes(pieces, pre, src=None):
    src = src if src is not None else pieces
    return {a for a, _k, _t in window_problems(pieces, pre, src, W)}


class BakedLayout(unittest.TestCase):
    def test_clean_window_passes(self):
        self.assertEqual(axes(["안녕하세요, 여러분.", "오늘도 좋은 하루"], [[], [1]]), set())

    def test_leading_space(self):
        self.assertIn("첫 칸 공백", axes(["안녕", " 하세요"], [[], [1]]))

    def test_leading_space_after_variable_is_ok(self):
        self.assertEqual(axes(["받았다", " 를 얻었다"], [[], [5]]), set())

    def test_orphan_punct(self):
        self.assertIn("고아 부호", axes(["가나다", ". 라마"], [[], [1]]))
        self.assertIn("고아 부호", axes(["가나다\n,라마"], [[]], ["가나다 ,라마"]))

    def test_blank_line_in_middle(self):
        self.assertIn("빈 줄", axes(["가나", "", "다라"], [[], [1], [1]]))

    def test_leading_blank_first_line_and_double_newline(self):
        # 2-18 — 창 머리의 빈 줄 · 조각 안 연속 개행
        self.assertIn("빈 줄", axes(["\n가나다", "라마"], [[], [1]], ["가나다", "라마"]))
        self.assertIn("빈 줄", axes(["가나\n\n다라"], [[]], ["가나 다라"]))
        self.assertIn("빈 줄", axes(["", "가나다"], [[], [1]], ["", "가나다"]))

    def test_trailing_blank_is_fine(self):
        self.assertEqual(axes(["가나 다라", ""], [[], [1]], ["가나 다라", ""]), set())

    def test_punct_glue(self):
        self.assertIn("부호 뒤 공백", axes(["가나,다라"], [[]]))
        self.assertEqual(axes(["값은 3.5 입니다"], [[]]), set())

    def test_word_cut(self):
        self.assertIn("낱말 속 접힘", axes(["안녕하 세요"], [[]], ["안녕하세요"]))

    def test_ellipsis_spacing_is_not_a_cut(self):
        self.assertEqual(axes(["흑… 흑…"], [[]], ["흑…흑…"]), set())

    def test_overflow(self):
        self.assertIn("넘침", axes(["가" * 30], [[]]))


if __name__ == "__main__":
    unittest.main()
