"""번역 규칙 부호 검사 — 합성 문안으로 걸리는 꼴과 통과하는 꼴을 못 박는다(원본 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import check_punct as c


class Rules(unittest.TestCase):
    def test_걸리는_꼴(self):
        self.assertIn("1-7 `～.`", c.violations("불렀어～."))
        self.assertIn("2-1 부호 뒤 글자 붙임", c.violations("안녕,친구"))
        self.assertIn("2-2 부호 앞 공백", c.violations("안녕 ."))
        self.assertIn("2-12 부호+…", c.violations("뭐?…"))
        self.assertIn("2-11 문장 앞 … 뒤 공백", c.violations("… 그랬다."))
        self.assertIn("전각 부호", c.violations("뭐？"))
        self.assertIn("1-3 점 연속·가운뎃점", c.violations(".............."))  # 점만으로 된 침묵 대사는 …×round(n/3)
        self.assertIn("1-3 점 연속·가운뎃점", c.violations("・・・"))

    def test_통과하는_꼴(self):
        for t in ("…그랬다.", "세…리…오…스…", "그대도… 잊었다", "1.5배", "안녕, 친구.", "뭐…?", "첫째.¶둘째."):
            self.assertEqual(c.violations(t), [], t)

    def test_쪽_표지를_넘어_붙지_않는다(self):
        self.assertEqual(c.violations("끝.¶…다음"), [])

    def test_말줄임_개수는_원문_점수의_삼분의일(self):
        self.assertFalse(c.dot_violation("………", 10))  # 10점 → 3
        self.assertTrue(c.dot_violation("………", 14))  # 14점 → 5
        self.assertFalse(c.dot_violation("…그래…", 6))  # 긴 말줄임이 아니면 보지 않는다
        self.assertFalse(c.dot_violation("…… 그래", 6))  # 6점 → 2

    def test_쉼표_후보는_참고만(self):
        self.assertEqual(c.comma_suspects("아트라스, 사람"), [])
        self.assertEqual(c.comma_suspects("세 마스터는, 말한다"), ["주제 뒤"])
        self.assertEqual(c.comma_suspects("당하고, 말았다"), ["짧은 연결어미 뒤"])

    def test_PUA_혼입은_실패(self):
        # PS1 붙임 공백(U+E003)이 문안에 남으면 이쪽 동적 조사 표지로 읽혀 엉뚱한 글자가 된다
        self.assertTrue(c.has_pua("\ue003말이군요."))
        self.assertTrue(c.has_pua("되도록\f\ue000하자"))
        self.assertFalse(c.has_pua("말이군요. 가나다 …"))

    def test_PS1_붙임_공백은_공백으로(self):
        import dialogue

        orig = dialogue._load
        dialogue._load = lambda: ({"S": {"1": {"t": "황제\ue003폐하"}, "2": {"t": "\ue003말이군"}}}, None)
        try:
            self.assertEqual(dialogue.ps1_text([("S", 1)]), "황제 폐하")
            self.assertEqual(dialogue.ps1_text([("S", 2)]), "말이군")
        finally:
            dialogue._load = orig


if __name__ == "__main__":
    unittest.main()
