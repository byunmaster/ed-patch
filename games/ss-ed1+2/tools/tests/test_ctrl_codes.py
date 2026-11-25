"""check_ctrl_codes 의 토큰 서명 — 누락·여분·순서가 서명 열에서 갈리는지."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import check_ctrl_codes as C


def seq(raw):
    return [t for t, _, _ in C._sig(raw)]


class Sig(unittest.TestCase):
    def test_sequence_detects_missing_color_off(self):
        orig = b"%c%s%c" + b"x" + b"%c"
        built_missing = b"%c%s" + b"x" + b"%c"  # 되돌림 하나 누락
        self.assertNotEqual(seq(orig), seq(built_missing))

    def test_sequence_detects_extra_and_order(self):
        self.assertNotEqual(seq(b"%c%s%c"), seq(b"%c%c%s%c"))
        self.assertNotEqual(seq(b"%s%c"), seq(b"%c%s"))

    def test_text_between_tokens_does_not_change_sequence(self):
        self.assertEqual(seq(b"%cabc%c"), seq(b"%c\xed\x95\x9c%c"))

    def test_shape_marks_leading_newline_as_text(self):
        self.assertEqual(C._sig(b"%c%s%c")[0], ("%c", "S", "T"))
        self.assertEqual(C._sig(b"\n%c%s%c")[0], ("%c", "T", "T"))


if __name__ == "__main__":
    unittest.main()
