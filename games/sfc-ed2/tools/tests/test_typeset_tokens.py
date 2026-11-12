"""조판기가 사전 문장(`<E1:n>`)·호출 조각(`<10 lo hi>`)의 폭을 알면 그 뒤 공백을 줄 첫 공백으로 지우지 않고 줄도 제대로 넘긴다(10-20 qa)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import typeset


class TokenWidth(unittest.TestCase):
    def test_space_after_sentence_token_kept_when_width_known(self):
        names = {"E1:4": "어서 오십시오."}
        out = typeset.typeset("<E1:4> 표는 1장에 100 Gold입니다만", names)
        self.assertIn("<E1:4>", out)
        self.assertIn("표는", out)
        self.assertNotIn("<E1:4>표는", out)  # 줄을 바꿔도(문장 끝에서 끊는 절 규칙) 이어 붙지는 않는다

    def test_unknown_width_drops_the_space(self):  # 폭을 모르면(0) 줄 첫 공백으로 오인한다 — 그래서 빌드가 폭을 넣어 준다
        out = typeset.typeset("<E1:4> 표는", {})
        self.assertNotIn("<E1:4> ", out)

    def test_call_width_counts(self):
        self.assertEqual(typeset.width("<10 27 30>", {"call:2730": "왕자님"}), 9)


class CompoundGlue(unittest.TestCase):
    def setUp(self):
        typeset.GLUE_PAIRS = {("노예", "상인")}

    def tearDown(self):
        typeset.GLUE_PAIRS = set()

    def test_glue_placeholder_restored(self):  # 묶음 자리표시(NBSP)는 출력에 남지 않는다 · 줄·쪽 수는 안 는다
        t = "가나다라마바사아자차카타파하거 노예 상인이다 맞아"
        out = typeset.typeset(t)
        self.assertNotIn("\u00a0", out)
        typeset.GLUE_PAIRS = set()
        self.assertLessEqual(out.count("\n"), typeset.typeset(t).count("\n"))

    def test_unlisted_pair_untouched(self):
        typeset.GLUE_PAIRS = set()
        self.assertEqual(typeset.typeset("노예 상인"), "노예 상인")


if __name__ == "__main__":
    unittest.main()
