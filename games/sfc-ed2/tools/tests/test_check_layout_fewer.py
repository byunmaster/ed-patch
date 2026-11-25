"""조판 지표 `fewer`(창 줄임) — 양성·음성 대조. 원문 두 창을 한 창에 합친 결과는 잡고, 끝 `<05>` 반복·같은 창 수는 안 잡는다(가짜 문장)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_layout as C


class FewerTest(unittest.TestCase):
    def test_positive_merged_windows(self):
        self.assertTrue(C.fewer_windows("가나다<05>라마바<05>", "가나다\n라마바<05>"))

    def test_negative_same_windows(self):
        self.assertFalse(C.fewer_windows("가나다<05>라마바<05>", "가나다<05>\n라마바<05>"))

    def test_negative_trailing_repeat_is_not_a_window(self):
        self.assertFalse(C.fewer_windows("가나다<05><05>", "가나다<05>"))

    def test_more_windows_not_fewer(self):
        self.assertFalse(C.fewer_windows("가나다라마바<05>", "가나다<05>라마바<05>"))


if __name__ == "__main__":
    unittest.main()
