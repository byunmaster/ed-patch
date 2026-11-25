"""가운데 맞춤 검사기(2-8)의 양성 대조 — 어긋난 줄은 걸리고 맞춘 줄(홀수 폭의 1px 차 포함)은 안 걸린다."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from check_centered import margin_problems


class Centered(unittest.TestCase):
    def test_off_center_is_caught(self):
        self.assertEqual(margin_problems([("장 끝", "A", 26, 23)]), [("장 끝", "A", 3)])
        self.assertEqual(len(margin_problems([("내레이션", "줄", 10, 20)])), 1)

    def test_centered_and_odd_width_pass(self):
        self.assertEqual(margin_problems([("a", "x", 30, 30), ("a", "y", 30, 31), ("a", "z", 31, 30)]), [])

    def test_two_px_is_caught(self):
        self.assertEqual(len(margin_problems([("a", "x", 30, 32)])), 1)


if __name__ == "__main__":
    unittest.main()
