"""check_punct 자신의 커버리지 — 위반을 넣으면 잡고, 정상 꼴은 통과한다. 원본 롬 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_punct  # noqa: E402


class Punct(unittest.TestCase):
    def test_점_뒤_붙여쓰기를_잡는다(self):
        self.assertEqual(len(check_punct.violations("가나…다라")), 1)
        self.assertEqual(len(check_punct.violations("\n……다라")), 1)

    def test_정상_꼴은_통과(self):
        for t in ("가나… 다라", "가나…<E0>", "가나…\n다라", "가나…」", "가나……?", "가나…{D0:01}"):
            self.assertEqual(check_punct.violations(t), [], t)

    def test_음절_끊어_말하기는_붙임(self):
        for t in ("세…리…오…스…<E0>", "할… 수… 없…다…"):
            self.assertEqual(check_punct.violations(t), [], t)
        self.assertEqual(len(check_punct.violations("그대도…잊었다")), 1)

    def test_되풀이_의성어와_여는_괄호는_붙임(self):
        for t in ("흑…흑…흑…", "…(화끈!)"):
            self.assertEqual(check_punct.violations(t), [], t)

    def test_문장_첫_말줄임은_뒤를_붙인다(self):
        for t in ("…그런 것처럼", "좋다. …어라?", "이건\\n…지도잖아"):
            self.assertEqual(check_punct.violations(t), [], t)
        for t in ("… 그런 것처럼", "좋다. … 어라?", "이건\\n… 지도잖아"):
            self.assertEqual(len(check_punct.violations(t)), 1, t)
        self.assertEqual(check_punct.violations("뭐라고…!? 어째서"), [])

    def test_물음표_느낌표와_말줄임_순서(self):
        for t in ("어떻게…!!", "소니아…!? 어째서", "뭐…?"):
            self.assertEqual(check_punct.violations(t), [], t)
        for t in ("어떻게!!…", "소니아!?… 어째서", "뭐？…"):
            self.assertTrue(check_punct.violations(t), t)

    def test_물결표_마침표(self):
        self.assertEqual(len(check_punct.violations("불렀어～.")), 1)
        self.assertEqual(check_punct.violations("불렀어～"), [])


if __name__ == "__main__":
    unittest.main()
