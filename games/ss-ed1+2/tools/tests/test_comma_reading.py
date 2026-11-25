"""쉼표 규칙 2-13 ⑨의 음절 계수 — **읽는 소리대로**(마스터 10-24 「권장대로」). 숫자·영문도 읽는 대로 세고 공백·부호는 안 센다.

가짜 문장만 쓴다(원문·정발 문장 인용 금지).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import patch_scn as P


class SinoSyllables(unittest.TestCase):
    def test_numbers_read_as_sino(self):
        # 십(1) · 이백(2) · 만(1) · 백오십(3) · 사(1) · 이십(2) · 천(1) · 만이천(3) — 십·백·천·만 앞의 「일」은 안 읽는다
        for n, want in ((10, 1), (200, 2), (10000, 1), (150, 3), (4, 1), (20, 2), (1000, 1), (12000, 3), (0, 1)):
            self.assertEqual(P.sino_syllables(n), want, n)

    def test_read_syllables_counts_numbers_and_latin(self):
        # `10 Gold` = 십 골드 = 3음절(공백 안 셈)
        self.assertEqual(P.read_syllables("10 Gold"), 3)
        self.assertEqual(P.read_syllables("가나다 10 Gold입니다만"), 3 + 3 + 4)
        self.assertEqual(P.read_syllables("가, 나!?"), 2)  # 부호·공백은 0
        self.assertEqual(P.read_syllables("４층"), 2)  # 전각 숫자도 읽는 대로: 사 + 층


class CommaRule(unittest.TestCase):
    def test_short_clause_drops_comma(self):
        # 앞 절 = 가나다라마 사아자차다만 (5 + 6 = 11음절)
        self.assertEqual(P.comma_rule("가나다라마 사아자차다만, 타파"), "가나다라마 사아자차다만 타파")

    def test_long_clause_keeps_comma(self):
        # 12음절 이상이면 쉼표를 남긴다
        t = "가나다라마바 사아자차카다만, 타파"  # 6 + 6 = 12
        self.assertEqual(P.comma_rule(t), t)

    def test_numbers_count_toward_the_clause(self):
        # 한글만으로는 9음절(≤11 → 뺌)인데 읽는 소리로는 십이만오천(5)을 더해 14음절이라 쉼표를 남겨야 한다
        t = "가나다라 125000 값입니다만, 다"
        self.assertEqual(P.read_syllables("가나다라 125000 값입니다만"), 4 + 5 + 5)
        self.assertEqual(P.comma_rule(t), t)
        # 같은 자리에 작은 숫자면(10 → 십 1음절) 11음절 이하라 쉼표를 뺀다
        self.assertEqual(P.comma_rule("가나다라 10 값입니다만, 다"), "가나다라 10 값입니다만 다")

    def test_wide_candidates_catch_n_batchim_de(self):
        # 「~듯한데,」「~얘긴데,」 — 좁은 열거(`는데`)가 놓치던 꼴. 앞 절 11음절 이하면 쉼표를 뺀다
        self.assertEqual(P.comma_rule("가나다 듯한데, 라마바"), "가나다 듯한데 라마바")
        self.assertEqual(P.comma_rule("가나다 얘긴데, 라마바"), "가나다 얘긴데 라마바")

    def test_noun_de_keeps_comma_and_conjunctive_adverbs_drop_it(self):
        # 명사 「데」(앞이 공백)와 부사 「가만,」은 건드리지 않는다
        for t in ("이런 데, 저런 데", "가만, 이게 뭐지?", "그런 곳, 이런 곳, 하나"):
            self.assertEqual(P.comma_rule(t), t, t)
        # 접속부사 뒤 쉼표는 규칙 2-13 ③ 대로 뺀다(「다만」「그런데」「근데」 — manager 10-24)
        self.assertEqual(P.comma_rule("다만, 알겠습니다."), "다만 알겠습니다.")
        self.assertEqual(P.comma_rule("그런데, 좋다."), "그런데 좋다.")
        self.assertEqual(P.comma_rule("근데, 좋다."), "근데 좋다.")

if __name__ == "__main__":
    unittest.main()
