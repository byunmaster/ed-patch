"""줄·쪽 나눔 지표(`check_linebreak.scan`)와 절째 내림(`reflow_script.wrap_clause`) 회귀 — 원본 없이 돈다. 문안은 가짜다.

🔴 지키는 것: 문장 중간 손 개행(c)·쪽 끝 한 어절 고아(a)를 잡고, 문장 끝 개행·쪽 넘김은 안 잡고,
   줄 나눔이 글자를 안 바꾸며(쉼표만 줄 끝에서 빠진다) 모든 줄이 17칸 안이다.
"""

import itertools
import os
import sys
import unittest
from typing import ClassVar

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_linebreak as L
import reflow_script as R


class Scan(unittest.TestCase):
    def test_soft_break_is_c(self):
        r = L.scan("오늘은 날씨가\n좋아서 산책을 간다.")
        self.assertEqual(len(r["c"]), 1)

    def test_sentence_end_break_is_fine(self):
        r = L.scan("오늘은 날씨가 좋다.\n내일은 비가 온다.")
        self.assertEqual(sum(len(v) for v in r.values()), 0)

    def test_page_end_orphan_is_a(self):
        r = L.scan("어쩌면 비가 올지도\n모른다\f그래서 우산을 챙겼다.")
        self.assertEqual(len(r["a"]), 1)

    def test_page_end_sentence_is_fine(self):
        r = L.scan("비가 온다.\f우산을 챙겼다.")
        self.assertEqual(sum(len(v) for v in r.values()), 0)


class Wrap(unittest.TestCase):
    def test_rows_fit_and_letters_kept(self):
        s = "그 아이는 어제 시장에 가서 사과와 배를 사 왔고, 동생에게 나눠 주었다."
        rows = R.wrap_clause(s)
        self.assertTrue(all(R._fits(x) for x in rows))
        self.assertEqual(R._letters("".join(rows)), R._letters(s))

    def test_no_clause_left_split(self):
        s = "시장에 다녀오는 길에 만난 친구가 말하길 내일 비가 온다고 해서 우산을 챙겼다."
        rows = R.wrap_clause(s)
        self.assertGreater(len(rows), 1)
        for a, b in itertools.pairwise(rows):
            self.assertIsNone(L.clause_tail(a.split(), b.split()))


class Regress(unittest.TestCase):
    """f — 마스터가 짚은 나빠진 꼴 여섯(전→후)은 전부 퇴행으로 잡혀야 한다. 문안은 가짜가 아니라 표본이다(우리 번역 문안)."""

    CASES: ClassVar[list] = [
        ("아무리 크다 해도\n이 배 안에 있는 건", "아무리 크다 해도 이 배 안에\n있는 건"),
        ("둘은\n왠지 입을 다물었다.", "둘은 왠지 입을\n다물었다."),
        ("그래서 순례\n이야기를 해 둬야겠구나", "그래서 순례 이야기를 해\n둬야겠구나"),
        ("큰 멧돼지\n고기일지도 몰라", "큰 멧돼지 고기일지도\n몰라"),
        ("전역을\n여행하는 순례 여행자니까", "전역을 여행하는 순례\n여행자니까"),
        ("그날\n끼니도 걱정인 때가 있었다", "그날 끼니도\n걱정인 때가 있었다"),
    ]

    def test_all_six_are_regressions(self):
        for old, new in self.CASES:
            with self.subTest(old=old):
                self.assertTrue(L.regress(old, new), (old, new))

    def test_fine_change_is_not(self):
        self.assertEqual(
            L.regress("오늘은 날씨가\n좋아서 산책을 간다.", "오늘은 날씨가 좋아서\n산책을 간다."),
            [],
        )


class WithLikeTest(unittest.TestCase):
    """「~와/과 달리·같이·함께」는 한 덩어리 — 갈리면 퇴행(마스터 10-26 MAP042#98)."""

    def test_split_is_regression(self):
        self.assertTrue(
            L.regress(
                "흥, 변경 담당인 우리와 달리\n성에서 오는",
                "흥, 변경 담당인 우리와\n달리 성에서 오는",
            )
        )

    def test_adverb_i_is_not_josa_end(self):
        self.assertFalse(L.josa_end("같이"))


class FullwidthLatinTest(unittest.TestCase):
    """약어를 전각으로 바꾼 줄은 퇴행이 아니다 — 전각 영문은 반각과 한 낱말로 견준다(10-27)."""

    def test_abbreviation_swap_is_not_regression(self):
        self.assertEqual(L.regress("더미용 NPC입니다.", "더미용 ＮＰＣ입니다."), [])


if __name__ == "__main__":
    unittest.main()
