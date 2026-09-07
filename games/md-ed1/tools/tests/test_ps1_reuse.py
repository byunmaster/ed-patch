"""PS1 재사용 매칭 — **끝나는가**. 마지막 페이지에서 무한 루프에 빠지던 회귀(2026-09-06)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ps1_reuse


class MatchPages(unittest.TestCase):
    def test_no_match_returns_none(self):
        self.assertIsNone(ps1_reuse.match_pages(["없는문장"], {}))

    def test_last_page_without_match_terminates(self):
        cp = {ps1_reuse.norm("있는문장"): ("SCN1", 1, "우리 문안", None)}
        self.assertIsNone(ps1_reuse.match_pages(["있는문장", "없는문장"], cp))

    def test_single_page_match(self):
        cp = {ps1_reuse.norm("있는문장"): ("SCN1", 1, "우리 문안", "화자")}
        got = ps1_reuse.match_pages(["있는문장"], cp)
        self.assertEqual(got, [("SCN1", 1, "우리 문안", "화자")])


if __name__ == "__main__":
    unittest.main()
