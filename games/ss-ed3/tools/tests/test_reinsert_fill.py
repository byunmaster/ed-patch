import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import reinsert as R
import typeset as T


class FitFill(unittest.TestCase):
    def test_fills_remaining_bytes_regardless_of_terminator(self):
        text = "짧은 말이다."
        budget = T.body_bytes(text) + 21
        out, n = R.fit_fill(text, budget)
        self.assertEqual((out, n), (text, 21))

    def test_refuses_when_text_exceeds_budget(self):
        self.assertIsNone(R.fit_fill("이 문장은 칸보다 길다", 4))

    def test_filler_is_the_unused_control_code(self):
        self.assertEqual(R.FILL, b"\x1a")


if __name__ == "__main__":
    unittest.main()
