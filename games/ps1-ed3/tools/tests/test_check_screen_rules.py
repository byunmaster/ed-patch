"""한 줄 문장(2-10)·쉼표(2-13) 검사기의 양성 대조 — 일부러 깬 줄을 넣어 걸리는지, 멀쩡한 줄은 안 걸리는지."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from check_screen_rules import comma_candidates, pages, row_end_commas, split_fit_sentences


class OneLineSentence(unittest.TestCase):
    def test_split_short_sentence_is_caught(self):
        got = split_fit_sentences(["쥬리오는 어릴 적", "병뚜껑을 모았었지."])
        self.assertEqual(len(got), 1)

    def test_sentence_that_fits_on_own_rows_passes(self):
        self.assertEqual(split_fit_sentences(["오늘은 맑다.", "내일은 흐리다."]), [])

    def test_long_sentence_may_split(self):
        long = ["이 문장은 한 줄 격자에 도저히 들어가지 않는 아주", "긴 문장이라서 둘로 나눌 수밖에 없다."]
        self.assertEqual(split_fit_sentences(long), [])

    def test_pages_split_on_op2(self):
        self.assertEqual(pages(["가", "나", "다"], [[], [1], [2]]), [["가", "나"], ["다"]])


class CommaCandidates(unittest.TestCase):
    def test_topic_comma(self):
        self.assertEqual(comma_candidates("파렌 왕국은, 작다."), [("주제", "왕국은")])

    def test_adverb_and_connective(self):
        self.assertEqual(comma_candidates("처음에는, 그랬다.")[0][0], "부사어")
        self.assertEqual(comma_candidates("계획 범죄에 능하고, 조심성 많다.")[0][0], "연결")

    def test_kept_classes_pass(self):
        for t in ("아트라스, 왔구나.", "그래, 알았어.", "란도, 플로라, 왔니?", "아이고, 큰일이다."):
            self.assertEqual(comma_candidates(t), [], t)

    def test_row_end_comma(self):
        self.assertEqual(row_end_commas(["앞 절이 끝나고,", "뒤 절이 이어진다."]), ["앞 절이 끝나고,"])
        self.assertEqual(row_end_commas(["끝났다.", "다음."]), [])


if __name__ == "__main__":
    unittest.main()
