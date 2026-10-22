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


class Continuation(unittest.TestCase):
    def test_end_state_last_line(self):
        self.assertEqual(typeset.end_state("가나\n다라마", {}), (9, 1))
        self.assertEqual(typeset.end_state("가나<05>다라", {}), (6, 0))

    def test_continuation_starts_at_lead_width(self):
        # 앞 구간이 줄 폭 36 까지 썼으면 「나다라마바사」(18)는 남은 14로 안 들어가 다음 줄로 간다
        t = typeset.typeset(" 가나다라 마바사아자차", {}, (36, 0))
        self.assertIn("\n", t)
        self.assertEqual(typeset.typeset(" 가나", {}, (0, 0)), " 가나")

    def test_glued_first_word_not_wrapped(self):
        self.assertTrue(typeset.typeset("{*이/가} 가나", {}, (48, 0)).startswith("{*이/가}"))


if __name__ == "__main__":
    unittest.main()
