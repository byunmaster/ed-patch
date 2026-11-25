"""rulings_corpus 의 정규화 — 공백·제어부호를 뺀 꼴로 대조하고, 어긋난 줄을 잡는다."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import rulings_corpus as M


class Norm(unittest.TestCase):
    def test_strips_layout_and_control(self):
        self.assertEqual(M.norm("%c병사%c\n잘 있었{p}습니다."), "병사잘있었습니다.")

    def test_speaker_tag_removed(self):
        self.assertEqual(M.norm("【병사】왕자님, 안녕하십니까"), "왕자님,안녕하십니까")

    def test_old_register_not_matched(self):
        self.assertNotIn(M.norm("주무시옵소서"), M.norm("편히 주무십시오"))


if __name__ == "__main__":
    unittest.main()
