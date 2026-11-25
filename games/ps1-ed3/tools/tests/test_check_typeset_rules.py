"""조판 규칙 검사의 「글꼴 섞임」 항 — 숫자·Goa/Pia(소지금 창 글꼴)와 Galmuri 영문이 한 낱말에 섞이면 운다."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_typeset_rules as r


def mixed(text):
    return [p for p in r.line_problems(text) if "글꼴이 섞임" in p]


class TestFontMix(unittest.TestCase):
    def test_uniform_words_pass(self):
        for t in ("300 Goa 를 받았다", "5 Pia", "Goa 와 Pia", "12345"):
            self.assertEqual(mixed(t), [], t)

    def test_mixed_words_fail(self):
        for t in ("3rd 번째", "Goal 이다", "Lv3 이다", "OK3"):
            self.assertTrue(mixed(t), t)

    def test_galmuri_only_passes(self):
        self.assertEqual(mixed("CIA 와 LA"), [])


if __name__ == "__main__":
    unittest.main()
