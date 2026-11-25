"""이음 대조(`check_joints`) — 판정 함수 셋의 양성·음성 대조."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_joints as cj


class GluedVar(unittest.TestCase):
    def test_hangul_before_token_is_caught(self):
        self.assertTrue(cj.glued_var("{1C 38}{josa} 상자에는{1D 61}{josa}↵들어 있었다."))

    def test_space_before_token_ok(self):
        self.assertFalse(cj.glued_var("{1C 38}{josa} 상자에는 {1D 61}{josa}↵들어 있었다."))

    def test_speaker_head_is_exempt(self):
        self.assertFalse(cj.glued_var("{16}병사{name}↵이런, 왕자님."))
        self.assertFalse(cj.glued_var("{16}병사{14}↵이런, 왕자님."))

    def test_token_after_token_ok(self):
        self.assertFalse(cj.glued_var("{1C 38}{1D 61}{josa}"))


class LostEnd(unittest.TestCase):
    def test_missing_trailing_newline(self):
        self.assertTrue(cj.lost_end("{1C 38}は↵{1D A6}取りました↵", "{1C 38}{josa}↵{1D A6}{josa} 집었다."))

    def test_present(self):
        self.assertFalse(cj.lost_end("{1C 38}は↵取りました↵", "{1C 38}{josa}↵집었다.↵"))

    def test_trailing_timing_code_is_skipped(self):
        self.assertFalse(cj.lost_end("あ↵{11 33 30}", "아↵{11 33 30}"))

    def test_original_without_newline_is_not_flagged(self):
        self.assertFalse(cj.lost_end("取りました", "집었다."))


class OverPages(unittest.TestCase):
    def test_five_lines(self):
        self.assertEqual(cj.over_pages("a↵b↵c↵d↵e⏎"), [5])

    def test_four_lines_ok_and_head_not_counted(self):
        self.assertEqual(cj.over_pages("{16}병사{14}↵a↵b↵c↵d⏎"), [])

    def test_second_page_break_resets(self):
        self.assertEqual(cj.over_pages("a↵b↵c{12}↵d↵e↵f⏎"), [])


class WordSplit(unittest.TestCase):
    def test_split_word_is_caught(self):
        self.assertTrue(cj.word_split("용감한 사내였다네", [["용감한 사내였", "다네"]]))

    def test_break_between_words_ok(self):
        self.assertFalse(cj.word_split("용감한 사내였다네", [["용감한"], ["사내였다네"]]))


if __name__ == "__main__":
    unittest.main()
