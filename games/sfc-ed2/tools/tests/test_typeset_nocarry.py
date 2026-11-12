"""규칙 2-17 — 보조용언 붙임(2-6)을 지키느라 원문 한 창이 둘로 갈리면 붙임을 포기하고 창 수를 지킨다(마스터 11-05)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import typeset as T


class NoCarryTest(unittest.TestCase):
    # 가짜 문장 — 「쓰게 될」 붙임을 지키면 첫 문장이 3줄이 되어 쪽이 넘어간다
    TEXT = "설마 보물상자 안의 무기를 쓰게 될 줄은 생각도 못 했습니다.\n이런 일이 벌어지다니…"

    def test_window_kept_when_carry_would_overflow(self):
        T.LEANS.clear()
        out = T.typeset(self.TEXT)
        self.assertNotIn("<05>", out)
        self.assertEqual(len(T.LEANS), 1)

    def test_carry_kept_when_room(self):
        T.LEANS.clear()
        out = T.typeset("표가 없잖아. 저쪽에서 사 오라고.")
        self.assertIn("사 오라고", out)
        self.assertEqual(T.LEANS, [])

    def test_page_break_moves_to_sentence_boundary(self):
        # 가짜 문안 — 조판기가 낸 쪽 경계가 둘째 문장 한가운데면 둘째 문장을 통째로 다음 쪽 머리로 옮긴다(규칙 2-17)
        out = T.typeset("근데 부자가 나란히 이런 데로 끌려오다니 피는 못 속인다니까. 뭐 아무튼 그래서 알게 되어 이런저런 일이 있었지.")
        self.assertIn("속인다니까.<05>뭐 아무튼", out)
        self.assertEqual(out.count("<05>"), 1)


if __name__ == "__main__":
    unittest.main()
