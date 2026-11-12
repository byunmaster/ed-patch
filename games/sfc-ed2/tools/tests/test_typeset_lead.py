"""문안 맨 앞 공백은 남는다 — 앞 구간 끝의 이름·수치 변수에 이어 붙는 자리(「<품목> 말이군요」 · 「150 Gold」). 줄 첫 공백은 여전히 지운다(규칙 2-5)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import typeset


class Lead(unittest.TestCase):
    def test_text_initial_space_kept(self):
        self.assertTrue(typeset.typeset(" 말이군요.<05>", {}).startswith(" 말이군요"))

    def test_mid_text_line_first_space_still_dropped(self):
        t = typeset.typeset("가나\n 다라", {})
        self.assertNotIn("\n ", t)

    def test_speaker_head_then_space_dropped(self):
        self.assertNotIn(" ", typeset.typeset("<1e>남자<04>\n 가나", {}).split("<04>")[1][:2])


class Continuation(unittest.TestCase):
    def test_end_state_last_line(self):
        self.assertEqual(typeset.end_state("가나\n다라마", {}), (9, 1))
        self.assertEqual(typeset.end_state("가나<05>다라", {}), (6, 0))

    def test_continuation_starts_at_lead_width(self):
        # 앞 구간이 줄 폭 36 까지 썼으면 「나다라마바사」(18)는 남은 14로 안 들어가 다음 줄로 간다
        t = typeset.typeset(" 가나다라 마바사아자차", {}, (36, 0))
        self.assertIn("\n", t)
        self.assertEqual(typeset.typeset(" 가나", {}, (0, 0)), " 가나")

    def test_glued_first_word_not_wrapped(self):
        self.assertTrue(typeset.typeset("{*이/가} 가나", {}, (48, 0)).startswith("{*이/가}"))


class AuxKeepTogether(unittest.TestCase):
    def test_main_plus_auxiliary_verb_not_split(self):
        # 본용언+보조용언(`사` + `오라고`) 은 줄이 갈려도 함께 간다 — 판정은 공용 krwrap.split_reason
        t = typeset.typeset("표가 없잖아. 저쪽에서 사 오라고.", {})
        self.assertIn("\n사 오라고", t)

    def test_plain_wrap_unchanged(self):
        t = typeset.typeset("가나다라마바사아자 차카타파하가나다 라마바사아자차", {})
        self.assertNotIn("\n ", t)


class HandNewlineInsideUnit(unittest.TestCase):
    def test_hand_newline_inside_aux_chain_is_soft(self):
        # 번역에 손으로 넣은 개행이 본용언+보조용언 사이면 공백으로 읽고 조판기가 끊는다
        t = typeset.typeset("딱하다 싶으시면 뭐라도 사\n가 주십시오.", {})
        self.assertIn("사 가 주십시오.", t)
        self.assertNotIn("사\n가", t)

    def test_hand_newline_after_sentence_end_kept(self):
        self.assertEqual(typeset.typeset("가나다.\n라마바", {}), "가나다.\n라마바")

    def test_hand_newline_inside_sentence_is_soft(self):  # 문장 중간 손 개행은 줄 맞춤용이라 공백으로 읽는다(마스터 10-25 전체 개행 점검)
        self.assertEqual(typeset.typeset("가나다\n라마바", {}), "가나다 라마바")

    def test_clause_moves_whole_to_next_line(self):  # 줄이 넘칠 때 이 줄에서 시작한 절이 한 줄에 들어가면 절째 내린다(문장 끝 우선)
        t = typeset.typeset("아, 아트라스 왕자님. 세상이 평화로워져 버려서 무기가 통 안 팔립니다.", {})
        self.assertEqual(t.split("\n"), ["아, 아트라스 왕자님.", "세상이 평화로워져 버려서", "무기가 통 안 팔립니다."])


class GlueAndLeadRules(unittest.TestCase):
    def test_noun_phrase_not_split(self):  # 「슬라임⏎괴롭히기」·「사제⏎바바라」 — 공백이 든 정본 이름·이 게임 명사구는 줄 사이에서 갈리지 않는다
        t = typeset.typeset("왕자님은 저희가 대지진 뒷수습을 하는 틈에 마을을 빠져나가 슬라임 괴롭히기를 하고 계셨지요?", {})
        self.assertIn("슬라임 괴롭히기를", t)
        t = typeset.typeset("용의 알에 들어갈 수 있는 건 사제 바바라뿐인데 지금은 행방불명입니다.", {})
        self.assertIn("사제 바바라뿐인데", t)

    def test_second_sentence_after_lead_gets_page_rule(self):  # 이름 뒤 조각이라도 둘째 문장부터는 문장 단위 쪽 나눔을 쓴다(고아 「있습니다.」 방지)
        t = typeset.typeset(", 슬라임 괴롭히기를 해 보신 적이 있사옵니까?\n몸 만들기에는 의외로 효험이 있습니다.", {}, (24, 0))
        self.assertNotIn("<05>있습니다.", t)

    def test_no_sliver_left_before_clause_move(self):  # 앞에 낱말 하나만 남기는 자리에서는 절을 내리지 않는다
        t = typeset.typeset("나 크면 시라스 낚시 명인이 되어서 아빠를 깜짝 놀라게 해 줄 거야.", {})
        self.assertNotIn("\n되어서\n", t)


if __name__ == "__main__":
    unittest.main()
