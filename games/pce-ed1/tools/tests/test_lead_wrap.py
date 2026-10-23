"""앞 메시지가 쓴 줄 끝에 이어 붙는 메시지의 첫 줄 짜기(`typeset.pages(lead_px=…)`) — 씬 64 「세리/오스」(10-22). 가짜 문안으로(원본 없이)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import typeset as T

TEXT = "가나다라마 바사아자차 카타파하 거너더러 머버서어"  # 가짜 문안 — 낱말마다 5·5·4·4·5자


class Lead(unittest.TestCase):
    def test_zero_lead_is_unchanged(self):
        self.assertEqual(T.pages(TEXT, speaker=False, lead_px=0), T.pages(TEXT, speaker=False))

    def test_first_word_that_does_not_fit_goes_to_the_next_row(self):
        pg = T.pages(TEXT, speaker=False, lead_px=128)  # 남은 28px — 5자 낱말(60px)이 안 들어간다
        self.assertEqual(pg[0][0], "")  # 빈 첫 줄 = 본문 첫머리에서 개행

    def test_first_line_fits_the_remaining_width(self):
        pg = T.pages(TEXT, speaker=False, lead_px=60)
        self.assertTrue(pg[0][0])
        self.assertLessEqual(T.px(pg[0][0]) + 60, 152)  # 칸 13 에 안 닿는다 — 닿으면 인터프리터가 먼저 넘긴다

    def test_no_word_is_split(self):
        words = set(TEXT.split())
        for lead in (0, 28, 60, 96, 128, 148):
            for pg in T.pages(TEXT, speaker=False, lead_px=lead):
                for ln in pg:
                    for w in ln.split():
                        self.assertIn(w, words, (lead, ln))

    def test_page_lines_stay_within_the_window(self):
        for lead in (0, 60, 128):
            for pg in T.pages(TEXT, speaker=False, lead_px=lead):
                self.assertLessEqual(len(pg), T.LINES)


if __name__ == "__main__":
    unittest.main()
