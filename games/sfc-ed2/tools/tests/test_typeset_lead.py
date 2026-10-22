"""문안 맨 앞 공백은 남는다 — 앞 구간 끝의 이름·수치 변수에 이어 붙는 자리(「<품목> 말이군요」 · 「150 Gold」). 줄 첫 공백은 여전히 지운다(규칙 2-5)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import typeset


class Lead(unittest.TestCase):
    def test_text_initial_space_kept(self):
        self.assertTrue(typeset.typeset(" 말이군요.<05>", {}).startswith(" 말이군요"))

    def test_mid_text_line_first_space_still_dropped(self):
        t = typeset.typeset("가나\n 다라", {})
        self.assertNotIn("\n ", t)

    def test_speaker_head_then_space_dropped(self):
        self.assertNotIn(" ", typeset.typeset("<1e>남자<04>\n 가나", {}).split("<04>")[1][:2])


if __name__ == "__main__":
    unittest.main()
