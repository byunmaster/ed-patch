"""`!?` 합자 금지 — 인코딩이 `!?` 를 합자 글자 `⁉` 로 바꾸지 않는다(마스터 11-13 · 11-17)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hangul_map as H


class NoLiga(unittest.TestCase):
    def test_text_unchanged(self):
        for s in ("뭐!?", "!?!?", "뭐?!", "가나다"):
            self.assertEqual(H.liga_text(s), s)

    def test_check_no_loss_does_not_fold_liga_back(self):
        import check_no_loss as N

        rev = N.reverse({"⁉": 6252, "＇": 6255})
        self.assertIn("⁉", rev.values())  # 풀지 않으니 쓰이면 원문 `!?` 와 어긋난다
        self.assertIn("'", rev.values())


if __name__ == "__main__":
    unittest.main()
