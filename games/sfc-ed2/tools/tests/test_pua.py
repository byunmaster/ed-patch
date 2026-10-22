"""문안에 사용자 영역(PUA) 문자가 섞이면 운다 — PS1 문안을 가져올 때 붙임 공백(U+E003) 등이 딸려 와 다른 글리프로 구워진다(md-ed2 발견, 10-18)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import common

NAME = "PUA 문자 섞임(U+E000~F8FF — PS1 붙임 공백 등 자리표시)"


@unittest.skipUnless(common.ORIG_ROM.exists(), "원본 롬 없음")
class Pua(unittest.TestCase):
    def setUp(self):
        import check_rules

        self.rule = dict(check_rules.RULES)[NAME]
        self.texts = check_rules.kr_strings()

    def test_rule_catches_pua(self):
        self.assertTrue(self.rule("너혼자"))
        self.assertTrue(self.rule(""))
        self.assertFalse(self.rule("너 혼자"))

    def test_product_text_has_no_pua(self):
        self.assertEqual([g for g, t in self.texts if self.rule(t)], [])


if __name__ == "__main__":
    unittest.main()
