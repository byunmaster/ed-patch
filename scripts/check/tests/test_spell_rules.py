"""맞춤법 규칙 검사 — 걸려야 할 것 · 안 걸려야 할 것(가짜 문장)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from check_spell_rules import FAIL, NOTE, scan


def _n(rules, kr):
    return len(list(scan([("x", "", kr, "dialog")], rules)))


class SpellRulesTest(unittest.TestCase):
    def test_osida_fails(self):
        self.assertEqual(_n(FAIL, "자, 가시옵시다."), 1)
        self.assertEqual(_n(FAIL, "내일로 미루기로 하옵시다."), 1)

    def test_proper_endings_pass(self):
        self.assertEqual(_n(FAIL, "자, 가시옵소서."), 0)
        self.assertEqual(_n(FAIL, "자, 가시지요."), 0)
        self.assertEqual(_n(FAIL, "함께 갑시다."), 0)

    def test_spacing_notes(self):
        self.assertEqual(_n(NOTE, "마침 잘 됐군요."), 1)
        self.assertEqual(_n(NOTE, "여기를 지나 가도 좋다."), 1)
        self.assertEqual(_n(NOTE, "한 마디만 하겠다."), 1)
        self.assertEqual(_n(NOTE, "저희 은 제품은 좋습니다."), 1)

    def test_joined_and_context_words_pass(self):
        self.assertEqual(_n(NOTE, "마침 잘됐군요. 지나가도 좋다. 한마디만."), 0)
        # 「그것 참」은 문맥(원문 주어)에 따라 띄움이 맞다 — 목록에 없다
        self.assertEqual(_n(NOTE, "그것 참 잘됐군."), 0)
        # 「잘 되어 간다」류 정도 부사는 알림이 뜨지만 실패는 아니다
        self.assertEqual(_n(FAIL, "일이 잘 되어 간다."), 0)

    def test_untranslated_skipped(self):
        self.assertEqual(len(list(scan([("x", "テスト", None, "dialog")], FAIL + NOTE))), 0)


if __name__ == "__main__":
    unittest.main()
