"""줄·쪽 나눔 전면 규칙 2-16 회귀 — 원본 없이 돈다 (가짜 문장만 쓴다)."""

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import linerules as L
import typeset_scn as T


class SoftHand(unittest.TestCase):
    def test_mid_sentence_becomes_space(self):
        self.assertEqual(
            L.soften_hand("가나다 라마바\n사아자 차카타."), "가나다 라마바 사아자 차카타."
        )

    def test_sentence_end_and_blank_kept(self):
        self.assertEqual(L.soften_hand("가나다.\n라마바 사아자"), "가나다.\n라마바 사아자")
        self.assertEqual(L.soften_hand("가나다\n\n라마바"), "가나다\n\n라마바")
        self.assertEqual(
            L.soften_hand("「가나다 라마바\n      마바」"), "「가나다 라마바\n      마바」"
        )  # 들여쓴 서명 줄

    def test_counts(self):
        self.assertEqual(L.mid_sentence_nl("가나다\n라마바."), 1)
        self.assertEqual(L.mid_sentence_nl(L.soften_hand("가나다\n라마바.")), 0)


class ClauseDown(unittest.TestCase):
    def test_fits_whole_clause_moves_down(self):
        # 「가나다라 마바사, 아자차」/「카타파하 갸냐.」 — 쉼표 뒤 절이 다음 줄에 통째로 든다
        got = T.clause_down(["가나다라 마바사, 아자차", "카타파하 갸냐."])
        self.assertEqual(got, ["가나다라 마바사,", "아자차 카타파하 갸냐."])

    def test_no_change_when_line_ends_on_boundary(self):
        ls = ["가나다라 마바사,", "아자차 카타파하 갸냐."]
        self.assertEqual(T.clause_down(ls), ls)

    def test_never_exceeds_cols(self):
        for ls in (["가나다라 마바사, 아자차", "카타파하 갸냐 거너."],):
            for ln in T.clause_down(ls):
                self.assertLessEqual(T.width(ln.replace(T._NB, " ")), T.COLS)

    def test_keeps_text(self):
        ls = ["가나다라 마바사, 아자차", "카타파하 갸냐."]
        self.assertEqual(T._strip_ws("".join(T.clause_down(ls))), T._strip_ws("".join(ls)))


if __name__ == "__main__":
    unittest.main()
