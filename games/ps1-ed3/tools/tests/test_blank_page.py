"""빈 쪽 방지 — 글 있는 줄이 앞에 몰려 빈 조각만으로 쪽이 서면 재조판을 거부한다(11-06 화면 실측)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import typeset


class BlankPage(unittest.TestCase):
    def test_flags_tail_page(self):
        self.assertTrue(typeset.blank_page(["가", "나", "다", "", ""]))  # 3줄 쪽: 둘째 쪽이 빔
        self.assertTrue(typeset.blank_page(["가", "나", "다", "라", ""]))  # 4줄 쪽: 둘째 쪽이 빔

    def test_ok(self):
        self.assertFalse(typeset.blank_page(["가", "나", "다", "라", "마"]))
        self.assertFalse(typeset.blank_page(["가", "나", "다"]))  # 한 쪽
        self.assertFalse(typeset.blank_page(["가", "", ""]))  # 조각이 3 이하면 쪽이 안 선다

    def test_reflow_keeps_original_structure(self):
        texts = ["첫 줄이다.", "둘째 줄이다.", "셋째 줄이다.", "넷째 줄이다.", "다섯째 줄이다."]
        rows = typeset.reflow(texts)
        self.assertTrue(rows is None or not typeset.blank_page(rows))


if __name__ == "__main__":
    unittest.main()
