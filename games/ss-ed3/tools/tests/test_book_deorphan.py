"""책 줄 나누기 — 부호 고아 세기와 `deorphan` (원본 없이 돈다)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import book as B


class Deorphan(unittest.TestCase):
    def test_orphans_counts_closing_first_and_opening_last(self):
        self.assertEqual(B.orphans(["가나다", "．라마"]), 1)  # 줄 첫머리 닫는 부호
        self.assertEqual(B.orphans(["가나「", "다라마"]), 1)  # 줄 끝 여는 부호
        self.assertEqual(B.orphans(["가나다．", "라마"]), 0)
        self.assertEqual(B.orphans(["．가나다"]), 0)  # 첫 줄은 문단 머리라 센다 안 함

    def test_noop_when_nothing_to_fix(self):
        t, n = B.deorphan("가나다　라마바", [10, 10])
        self.assertEqual((t, n), ("가나다　라마바", 0))

    def test_never_increases_orphans(self):
        for text, w in (("가나　다라마바．사아자", [10, 10, 10]), ("가나다라마．바사아자", [10, 10])):
            before = B.orphans(B.split_to(text, w)[0])
            t, _ = B.deorphan(text, w)
            rows, ok = B.split_to(t, w)
            self.assertTrue(ok)
            self.assertLessEqual(B.orphans(rows), before)


if __name__ == "__main__":
    unittest.main()
