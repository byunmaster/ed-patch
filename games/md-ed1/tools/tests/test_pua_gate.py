"""check_text.PUA — PS1 자리표시(사용자 영역) 문자가 우리 문안에 섞이면 잡는다. 원본 없이 도는 합성 검사."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_text as c


class PuaGate(unittest.TestCase):
    def test_nobreak_space_is_caught(self):
        self.assertTrue(c.PUA.search("봤습죠.\ue003그랬더니"))

    def test_hard_newline_marker_is_caught(self):
        self.assertTrue(c.PUA.search("가\ue000나"))

    def test_plain_korean_and_tags_pass(self):
        self.assertFalse(c.PUA.search("<0e> 말이군. 정말 고마워.\f<06>"))


if __name__ == "__main__":
    unittest.main()
