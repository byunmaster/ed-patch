"""규칙 2-16 줄·쪽 나눔 후처리(linebreak.py) — 절째 내림과 경계 판정."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import linebreak


class LineBreak(unittest.TestCase):
    def test_clause_pushed_whole(self):
        linebreak.set_width(17.5)
        page = ["가나다라마바사 사아자차카 타파", "하라는 말을 했다."]
        out = linebreak.improve_clause(list(page))
        self.assertLessEqual(len(out), len(page))
        self.assertTrue(all(linebreak._width(x) <= 17.5 for x in out))

    def test_boundary(self):
        self.assertEqual(linebreak.boundary_strength("시라스라고"), 0)
        self.assertEqual(linebreak.boundary_strength("가면서,"), 2)
        self.assertEqual(linebreak.boundary_strength("오,"), 0)


if __name__ == "__main__":
    unittest.main()
