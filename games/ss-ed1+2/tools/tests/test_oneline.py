import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_oneline as K
import linerules as L
import typeset_scn as T


class OneLine(unittest.TestCase):
    def test_short_sentence_split_over_two_lines_is_found(self):
        got = K.page_sentences(["그러십니까? 그것 참", "아쉽군요. 이 복권은"])
        self.assertEqual([s for s, _p in got], ["그것 참 아쉽군요."])

    def test_sentence_longer_than_a_line_is_not_flagged(self):
        page = ["가나다라마바사아자차카타 하", "파하가나다라마바사아자차 카타파하."]
        self.assertEqual(K.page_sentences(page), [])

    def test_sentence_on_one_line_is_not_flagged(self):
        self.assertEqual(K.page_sentences(["그러십니까?", "그것 참 아쉽군요."]), [])

    def test_message_hand_break_in_short_fixed_sentence_is_found(self):
        got = [one for one, rows, var in K.sentences("가나다\n라마바.") if rows >= 2 and not var]
        self.assertEqual(got, ["가나다 라마바."])

    def test_sentence_boundary_ignores_short_front_guard(self):
        # 앞 문장이 MIN_LEFT 보다 짧아도 문장 경계에서는 새 줄에서 시작한다 (규칙 2-10)
        kk = L.clause_split(["그러십니까?", "그것", "참"], ["아쉽군요.", "이", "복권은"], T._wf)
        self.assertEqual(kk, 1)

    def test_comma_boundary_still_keeps_short_front_guard(self):
        self.assertIsNone(L.clause_split(["네,", "그것", "참"], ["아쉽군요.", "이", "복권은"], T._wf))


if __name__ == "__main__":
    unittest.main()
