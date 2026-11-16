"""게시판 의뢰문 재조판(`board_text.reflow`) — 어절 단위·순서 보존·줄 폭 준수·못 드는 것은 사유."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import board_text as B


class TestReflow(unittest.TestCase):
    def test_넘치는_끝말을_다음_줄로(self):
        body = ["가나다라마바사아 자차카타파하 거너", "더러"]
        out, why = B.reflow("요약", body, limit=144)
        self.assertEqual(why, "")
        self.assertEqual(" ".join(out).split(), " ".join(body).split())  # 낱말·순서 불변
        self.assertTrue(all(B.px(t) <= 144 for t in out))

    def test_줄이_모자라면_사유(self):
        out, why = B.reflow("요약", ["가나다라마바 사아자차카타", "파하거너더러 머버"], limit=72)
        self.assertIsNone(out)
        self.assertIn("줄 필요", why)

    def test_요약이_넘치면_사유(self):
        out, why = B.reflow("가나다라마바사아자차", ["본문"], limit=96)
        self.assertIsNone(out)
        self.assertIn("요약", why)

    def test_바뀐_데_없으면_그대로(self):
        body = ["가나다", "라마바"]
        self.assertEqual(B.reflow("요약", body, limit=192), (body, ""))


if __name__ == "__main__":
    unittest.main()
