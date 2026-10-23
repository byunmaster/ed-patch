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
        self.assertIn("<E1:4> 표는", out)

    def test_unknown_width_drops_the_space(self):  # 폭을 모르면(0) 줄 첫 공백으로 오인한다 — 그래서 빌드가 폭을 넣어 준다
        out = typeset.typeset("<E1:4> 표는", {})
        self.assertNotIn("<E1:4> ", out)

    def test_call_width_counts(self):
        self.assertEqual(typeset.width("<10 27 30>", {"call:2730": "왕자님"}), 9)


if __name__ == "__main__":
    unittest.main()
