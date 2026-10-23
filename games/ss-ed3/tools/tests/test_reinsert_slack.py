"""재삽입 — 줄 폭 상한(17 칸) — 종결 뒤 `FF FF` 패딩은 없다 (원본 없이 돈다)."""

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

    def test_no_ff_ff_slack_path(self):
        # 🔴 10-22: 종결 뒤 `FF FF` 패딩은 다음 대사가 안 불려 걷었다 — 되살아나지 않게
        self.assertFalse(hasattr(R, "fit_slack"))
        self.assertFalse(hasattr(R, "slack_ok"))


if __name__ == "__main__":
    unittest.main()
