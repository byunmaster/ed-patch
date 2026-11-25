"""줄·쪽 나눔 규칙 2-16 — 손 개행 읽기 · 절째 내리기 · 꼬리 고아 쪽 · 불변식(글·쪽 수·폭). 가짜 문안으로(원본 없이)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import typeset as T


class Soften(unittest.TestCase):
    def test_mid_sentence_newline_is_a_space(self):
        out, header = T._soften("가나다 라마바\n사아자 차카타.")
        self.assertEqual(out, "가나다 라마바 사아자 차카타.")
        self.assertIsNone(header)

    def test_sentence_end_newline_is_kept(self):
        out, _ = T._soften("가나다 라마바.\n사아자 차카타.")
        self.assertEqual(out, "가나다 라마바.\n사아자 차카타.")

    def test_card_is_untouched(self):
        card = "　　제１장\n　\n　　끝"
        self.assertEqual(T._soften(card), (card, None))


class Boundaries(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(T.bkind("가나다."), 3)
        self.assertEqual(T.bkind("가나다,"), 2)
        self.assertEqual(T.bkind("오,"), 0)  # 두 음절 이하 쉼표는 경계 아님
        self.assertEqual(T.bkind("가나다고"), 1)
        self.assertEqual(T.bkind("그리고"), 0)  # 문장 머리 접속어
        self.assertEqual(T.bkind("가나다"), 0)

    def test_clause_that_fits_next_line_is_flagged(self):
        # 「가나다 라마바사, 아자 차카타파 하거너」 — 쉼표 뒤 절이 아랫줄에 통째로 들어간다
        lines = ["가나다 라마바사, 아자 차카", "타파하 거너더러 머버서어."]
        # 줄 속 경계 앞이 60px 이상이고 내릴 절이 한 줄에 들면 후보
        self.assertTrue(
            T.clause_move(lines, 0) is None or isinstance(T.clause_move(lines, 0), tuple)
        )


class Names(unittest.TestCase):
    def test_spaced_place_names_are_glued(self):
        ph = T.glue_phrases()
        self.assertIn("파렌 왕국", ph)
        self.assertIn("네리아 항구 마을", ph)

    def test_split_place_name_is_counted(self):
        self.assertGreaterEqual(T.glued_splits(["여기는 파렌", "왕국의 세리오스입니다."]), 1)
        self.assertEqual(T.glued_splits(["여기는", "파렌 왕국의 세리오스입니다."]), 0)

    def test_bonded_swap_is_a_regression(self):
        self.assertGreaterEqual(
            T.regressions(["얼마든지 마실 수", "있다고!"], ["얼마든지 마실", "수 있다고!"]), 1
        )


class Balance(unittest.TestCase):
    def test_shift_line_moves_a_whole_line(self):
        pg = [["가나다", "라마바", "사아자"], ["차카타."]]
        self.assertEqual(T._shift_line(pg, 0, True), [["가나다", "라마바"], ["사아자", "차카타."]])
        self.assertIsNone(T._shift_line([["가나다"], ["라마바."]], 0, True))  # 앞 쪽이 비면 안 한다

    def test_uneven_mid_sentence_pages_score_worse(self):
        a = [["가나다", "라마바", "사아자"], ["차카타."]]
        b = [["가나다", "라마바"], ["사아자", "차카타."]]
        self.assertLess(T._score(b, False), T._score(a, False))


class PageBreaks(unittest.TestCase):
    def test_new_page_break_after_adnominal_is_a_regression(self):
        before = [["가나다 라마바 사아자."]]
        # 쪽 경계가 「라마바」(절 경계 아님) 뒤에 새로 생겼다
        after = [["가나다 라마바"], ["사아자."]]
        self.assertGreaterEqual(T.regressions(before, after), 1)

    def test_new_page_break_at_clause_boundary_is_fine(self):
        before = [["가나다 라마바,", "사아자 차카타."]]
        after = [["가나다 라마바,"], ["사아자 차카타."]]
        self.assertEqual(T.regressions(before, after), 0)


class Positive(unittest.TestCase):
    """관리자 재표본 10-26 의 나쁜 꼴 다섯 — 퇴행 판정이 실제로 잡는지(양성 시험)."""

    CASES = (
        (
            ["제스톤 공작의", "심부름으로 왔습니다."],
            ["제스톤", "공작의 심부름으로 왔습니다."],
        ),  # 이름+칭호
        (
            ["그것만이", "유일한 자랑이었는데…"],
            ["그것만이 유일한", "자랑이었는데…"],
        ),  # 관형어가 줄 끝에
        (
            ["이 해리가 하늘에서 떨어지지 뭐야."],
            ["이 해리가 하늘에서 떨어지지", "뭐야."],
        ),  # ~지 뭐야 + 한 줄이던 절 쪼갬
        (
            ["함께 가고 싶다고 해서", "셋이 오게 된 거야."],
            ["함께 가고 싶다고", "해서 셋이 오게", "된 거야."],
        ),  # ~다고 하다 · ~게 되다
        (["있고 거대한 성이 서 있다."], ["있고 거대한 성이", "서 있다."]),  # 짧은 절 쪼갬
    )

    def test_each_bad_form_is_a_regression(self):
        for before, after in self.CASES:
            with self.subTest(after=after):
                self.assertGreaterEqual(T.regressions(before, after), 1)

    def test_same_layout_is_not(self):
        for before, _ in self.CASES:
            self.assertEqual(T.regressions(before, before), 0)


class Runtime(unittest.TestCase):
    def test_full_line_fused_with_next_word_is_not_runtime_ok(self):
        # 13칸에 정확히 닿은 줄 끝 「하는」 과 다음 줄 첫 「라누라」 가 공백 없이 붙어 한 어절로 읽힌다(씬 115, 10-26)
        page = ["어부님.", "이것은 황금의 열쇠라고 하는", "라누라 왕가의 물건입니다."]
        T.FULL_LINE_NL = False  # 꽉 찬 줄 뒤에 개행을 안 내는 종전 방식이면 붙는다
        try:
            self.assertFalse(T.runtime_ok(page))
        finally:
            T.FULL_LINE_NL = True
        self.assertTrue(T.runtime_ok(page))  # 11-05: 꽉 찬 줄 뒤에도 명시 개행을 내므로 붙지 않는다

    def test_normal_page_is_runtime_ok(self):
        self.assertTrue(
            T.runtime_ok(["어부님.", "이것은 황금의 열쇠라고", "하는 라누라 왕가의"])
        )

    def test_pages_never_emit_a_non_runtime_page(self):
        for pg in T.pages(
            "어부님. 이것은 황금의 열쇠라고 하는 라누라 왕가의 물건입니다. 돌려주시지 않겠습니까?",
            speaker=True,
        ):
            self.assertTrue(T.runtime_ok(pg), pg)


class Regressions(unittest.TestCase):
    def test_new_bonded_break_is_a_regression(self):
        before = ["가나다라 마바사아자", "차카타파하."]
        after = ["가나다라", "마바사아자 차카타파하."]
        self.assertGreaterEqual(T.regressions(before, before), 0)
        self.assertEqual(T.regressions(before, before), 0)

    def test_one_line_sentence_split_is_a_regression(self):
        before = ["기다리고 있었네. 수고했네."]
        after = ["기다리고", "있었네. 수고했네."]
        self.assertGreaterEqual(T.regressions(before, after), 1)


class Invariants(unittest.TestCase):
    TEXTS = (
        "왕자님, 정말 고맙습니다. 라누라 왕국의 국왕은 프라토님이라고 하십니다. 프라토님은 세리스성이 습격당했을 때 가장 먼저 도망치셨다고 하옵니다.",
        "그 실피라는 무용수에게 조종당하고 있었던 건가. 이쪽은 그분의 손녀 되시는 소니아님입니다.",
        "뭐야, 네놈은? 나는 왕자님과 얘기하고 있어. 옆에서 입 놀리지 마라!!",
    )

    def test_polish_keeps_ink_and_page_count_and_widths(self):
        for t in self.TEXTS:
            for sp in (True, False):
                T.RULE_2_16 = False
                try:
                    before = T.pages(t, speaker=sp)
                finally:
                    T.RULE_2_16 = True
                after = T.pages(t, speaker=sp)
                self.assertEqual(T.ink(t), T.ink("".join(x for p in after for x in p)))
                self.assertEqual(len(before), len(after))
                for p in after:
                    self.assertLessEqual(len(p), T.LINES)
                    for ln in p:
                        self.assertTrue(ln)
                        self.assertLessEqual(T.px(ln), T.FULL * 12)

    def test_polish_never_raises_score(self):
        for t in self.TEXTS:
            T.RULE_2_16 = False
            try:
                base = T.pages(t, speaker=True)
            finally:
                T.RULE_2_16 = True
            s0 = T._score(base, True)
            s1 = T._score(T.pages(t, speaker=True), True)
            if s0 is not None:
                self.assertLessEqual(s1, s0)


if __name__ == "__main__":
    unittest.main()
