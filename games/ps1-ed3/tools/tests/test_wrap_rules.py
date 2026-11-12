"""줄 나눔 규칙 2-16 — ② 절째 내리기 · ③ 끝 줄 고아 방지(가짜 문장으로)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import typeset


class TestClauseSplit(unittest.TestCase):
    def test_clause_moves_down_whole(self):
        a, b = "가나다라마 바사아자차카타 파하거너더지만 러머버서", "어저처커 터퍼허고노도로."
        sp = typeset.clause_split(a, b, "ed3", 24)
        self.assertEqual(sp, ("가나다라마 바사아자차카타 파하거너더지만", "러머버서"))

    def test_short_head_stays(self):
        self.assertIsNone(
            typeset.clause_split("가나지만 러머버서", "어저처커 터퍼허고노도로.", "ed3", 24)
        )

    def test_two_syllable_comma_is_not_boundary(self):
        self.assertFalse(typeset.clause_bound(["오,", "가나다"], 0))

    def test_sentence_end_row_skipped(self):
        self.assertIsNone(
            typeset.clause_split(
                "가나다라마 바사아자차카타 파하거너더지만. 러머버.", "어저처커.", "ed3", 24
            )
        )


class TestOrphan(unittest.TestCase):
    def test_tail_word_orphan(self):
        self.assertTrue(typeset.orphan_tail(["가나다라 마바사아", "자차카타파."]))
        self.assertFalse(typeset.orphan_tail(["가나다라 마바사아.", "자차카타파."]))

    def test_rebreak_pulls_word_down(self):
        rows = typeset.rebreak(
            ["가나다라마바 사아자차카타 파하거너", "더러머버서어저."], lambda t: [t], "ed3", 24
        )
        self.assertFalse(typeset.orphan_tail(rows))


if __name__ == "__main__":
    unittest.main()


class TestBalance(unittest.TestCase):
    def test_even_split_moves_row_at_clause_end(self):
        a = ["가나다라마 바사.", "아자차카타 파하거너,", "더러머버서 어저처커"]
        out = typeset.balance_windows([a, ["고노도로"]], [3, 3])
        self.assertEqual([len(w) for w in out], [2, 2])
        self.assertEqual(
            "".join(sum(out, [])).replace(" ", ""), "".join(a + ["고노도로"]).replace(" ", "")
        )

    def test_never_moves_boundary_into_mid_sentence(self):
        a = ["가나다라마 바사아", "자차카타 파하거너", "더러머버서 어저처커"]
        out = typeset.balance_windows([a, ["고노도로"]], [3, 3])
        self.assertEqual(out[0], a)  # 새 쪽 경계가 절 경계가 아니라 거부

    def test_sentence_end_page_stays(self):
        a = ["가나다라마.", "바사아자차카.", "타파하거너더."]
        out = typeset.balance_windows([a, ["고노도로"]], [3, 3])
        self.assertEqual(out[0], a)

    def test_cap_respected(self):
        a = ["가나다라마 바사.", "아자차카타 파하거너,", "더러머버서 어저처커"]
        out = typeset.balance_windows([a, ["고노도로"]], [3, 1])
        self.assertEqual(out[0], a)


class TestRegressions(unittest.TestCase):
    def test_sentence_split_is_regression(self):
        self.assertTrue(
            typeset.regressions(["가나다라 마바사아자차."], ["가나다라", "마바사아자차."])
        )

    def test_same_layout_is_clean(self):
        self.assertEqual(typeset.regressions(["가나다라 마바사."], ["가나다라 마바사."]), [])


class TestBonded(unittest.TestCase):
    def test_adnominal_plus_bound_noun_with_josa(self):
        self.assertTrue(typeset.bonded("왔을", "때만은"))
        self.assertTrue(typeset.bonded("갈", "수도"))

    def test_plain_noun_pair_is_free(self):
        self.assertFalse(typeset.bonded("마을", "사람들이"))
