"""자막 전용 반각 글꼴(네오둥근모) — 글꼴 태그 덧붙임과 전각 말줄임표 글리프."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import captions
import hangul


class FontTags(unittest.TestCase):
    def test_wraps_narrow_font_once(self):
        s = "<fd85><fe10>안녕.<fd80><06>"
        out = captions.font_tags(s)
        self.assertEqual(out, "<fd85><fd05><fe10>안녕.<fd80><fd00><06>")
        self.assertEqual(captions.font_tags(out), out)  # 두 번 불러도 같다

    def test_plain_dialog_untouched(self):
        self.assertEqual(captions.font_tags("안녕."), "안녕.")


class EllipsisFull(unittest.TestCase):
    def test_three_square_dots_spread_over_cell(self):
        g = hangul.ellipsis_full(16)
        ink = [(x, y) for y, row in enumerate(g) for x, v in enumerate(row) if v]
        self.assertEqual(len(ink), 12)  # 2×2 점 셋
        self.assertEqual({y for _, y in ink}, {10, 11})  # 네오둥근모 마침표와 같은 행
        self.assertEqual(sorted({x for x, _ in ink}), [2, 3, 7, 8, 12, 13])


if __name__ == "__main__":
    unittest.main()
