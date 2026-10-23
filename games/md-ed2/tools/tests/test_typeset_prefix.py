"""앞 폭 반영 조판(`build.typeset(prefix_w=…)`) — 같은 줄에 이미 쓰인 폭만큼 첫 줄이 짧아져야 한다(10-23)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import build
from text import krwrap


class TypesetPrefix(unittest.TestCase):
    def test_no_prefix_is_old_behaviour(self):
        t = "가나다라마바사 아자차카타파하 갸냐댜랴먀뱌샤 햐"
        self.assertEqual(build.typeset(t), build.typeset(t, "", 0.0))

    def test_first_line_shrinks_by_prefix(self):
        t = "가나다라마바사 아자차카타파하."
        free = build.typeset(t)[0]
        pre = build.typeset(t, "", 6.0)[0]
        self.assertLessEqual(krwrap.text_width(pre[0]) + 6.0, build.WIDTH)
        self.assertGreaterEqual(len(pre), len(free))

    def test_break_right_after_prefix_when_allowed(self):
        # 앞 글이 문장 끝이고 다음 어절이 안 들어가면 첫 줄이 비고(= 앞 글 뒤에서 줄이 갈리고) 글은 다음 줄로 간다
        pg = build.typeset("가나다라마바사아자차카", "", 14.0, True)[0]
        self.assertEqual(pg[0], "")
        self.assertEqual(pg[1], "가나다라마바사아자차카")

    def test_glued_word_overflow_falls_back(self):
        # 끊을 자리 없이 붙은 어절이 남은 폭을 넘으면 옛 조판으로 물러나 기록한다(런타임 어절 줄넘김 몫)
        n = len(build.PREFIX_UNFIT)
        t = "가나다라마바사아자차카"
        self.assertEqual(build.typeset(t, "", 14.0, False), build.typeset(t))
        self.assertEqual(len(build.PREFIX_UNFIT), n + 1)


if __name__ == "__main__":
    unittest.main()
