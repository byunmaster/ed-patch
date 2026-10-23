"""재삽입 — 줄 폭 상한(17 칸)과 무동작 패딩(`FF FF`) (원본 없이 돈다)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import reinsert as R
import typeset as T


class Slack(unittest.TestCase):
    def test_cap_keeps_padded_line_inside_window(self):
        # 원문이 한 줄로 길게 쓴 블록 — 옛 길은 원문 폭까지 열어 17 칸을 넘겼다
        text = "마침 잘됐네.\n늦기 전에"
        jp = "あ" * 24 + "\n"  # 원문 폭 24 칸
        budget = T.body_bytes(text) + 40
        old, _ = R.fit(text, budget, None, jp)
        new, _ = R.fit(text, budget, None, jp, cap=True)
        self.assertTrue(max(T.cols(x) for x in T.lines(old)) > 17)
        self.assertTrue(all(T.cols(x) <= 17 for x in T.lines(new)))

    def test_slack_pairs_and_parity(self):
        t, m = R.fit_slack("가나다\n라마", 30)
        self.assertEqual(T.body_bytes(t) + 2 * m, 30)
        t, m = R.fit_slack("가나다\n라마", 31)  # 홀수 — 반각 하나가 줄에 들어간다
        self.assertEqual(T.body_bytes(t) + 2 * m, 31)

    def test_slack_none_when_too_long(self):
        self.assertIsNone(R.fit_slack("가나다라마바사", 4))

    def test_slack_ok_needs_ended_text_mode(self):
        d = bytes([0xFF, 0xFF, 0x10, 0x00, 0x09])
        self.assertTrue(R.slack_ok(d, 0, 2))
        self.assertFalse(R.slack_ok(bytes([0, 0, 0x0E, 0x02, 0x00]), 0, 2))  # 글 모드가 이어진다
        self.assertFalse(R.slack_ok(d, 0, 99))


if __name__ == "__main__":
    unittest.main()
