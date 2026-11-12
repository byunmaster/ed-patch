"""check_color 양성 대조 — 닫기 누락·열기 누락·순서·빈 범위·쪽 가로지름·낱말 가운데 열림이 각각 걸리는지."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_color as C

JP = "<1c>あいう。<04><05>えお"


class T(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(C.check(JP, "<1c>가나다.<04><05>라마"), [])

    def test_axes(self):
        self.assertTrue(any("닫기" in x for x in C.check(JP, "<1c>가나다.<05>라마")))
        self.assertTrue(any("열기 개수" in x for x in C.check(JP, "가나다.<04><05>라마")))
        self.assertTrue(
            any("순서" in x for x in C.check("<1c>あ<04>い<1c>う<04>", "<1c>가<1c>나<04>다<04>"))
        )
        self.assertTrue(any("빈 색" in x for x in C.check(JP, "<1c><04><05>라마")))
        self.assertTrue(any("가로지름" in x for x in C.check(JP, "<1c>가나<05>다.<04>라마")))
        self.assertTrue(any("낱말 가운데" in x for x in C.check(JP, "그<1c>가나다.<04><05>라마")))

    def test_same_as_original_crossing(self):
        self.assertEqual(C.check("<1c>あ<05>い<04>", "<1c>가<05>나<04>"), [])


if __name__ == "__main__":
    unittest.main()
