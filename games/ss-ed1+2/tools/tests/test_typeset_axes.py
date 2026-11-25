"""조판 정적 게이트 축의 양성 대조 — 일부러 틀린 문안이 걸리는지 (마스터 10-31 조판 검사)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_wrap_rules as W


class Axes(unittest.TestCase):
    def test_punct_glued(self):
        self.assertTrue(W.prose_marks("그래,알겠어.").get("부호 뒤 붙임"))
        self.assertTrue(W.prose_marks("정말?아니야").get("부호 뒤 붙임"))

    def test_punct_ok(self):
        for s in ("그래, 알겠어.", "3.5배", "끝났다.\n다음", "정말?」"):
            self.assertFalse(W.prose_marks(s).get("부호 뒤 붙임"), s)

    def test_line_head_space(self):
        bad = W.scan_lines("가나 다라", ["가나", " 다라"], [False, True])
        self.assertTrue(bad.get("줄머리 공백"))

    def test_line_head_punct(self):
        bad = W.scan_lines("가나다,", ["가나다", ","], [False, True])
        self.assertTrue(bad.get("줄머리 부호"))

    def test_word_split(self):
        bad = W.scan_lines("가나다라마", ["가나다", "라마"], [False, True])
        self.assertTrue(bad.get("어절 중간"))

    def test_clean(self):
        bad = W.scan_lines("가나 다라", ["가나 ", "다라"], [False, True])
        self.assertFalse(dict(bad))


if __name__ == "__main__":
    unittest.main()
