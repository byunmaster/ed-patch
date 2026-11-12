"""고정 배치 합침 지표(joined) — 양성·음성 대조(11-06 3장 카드: 첫 줄이 짧아 손 개행을 합쳤다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_layout as C
import typeset as T


class JoinedTest(unittest.TestCase):
    CARD = "<08>" + " " * 9 + "제３장  용의 알\n \n" + "　" * 9 + "끝\n"  # 가짜 카드 — 3장 꼴

    def test_positive_card_joined_by_typesetter(self):
        out = T.typeset(self.CARD)
        self.assertEqual(C.joined_windows(self.CARD, out), 1)

    def test_negative_raw_kept(self):
        self.assertEqual(C.joined_windows(self.CARD, self.CARD), 0)

    def test_negative_plain_dialog(self):
        t = "안녕하세요.\n저는 여기서 일하는 사람입니다."
        self.assertEqual(C.joined_windows(t, T.typeset(t)), 0)


if __name__ == "__main__":
    unittest.main()
