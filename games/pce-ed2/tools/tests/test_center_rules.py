"""장 끝 카드 줄별 가운데 · 장 제목 띠 잉크 가운데(마스터 11-08 「입장배너·HUD·장제목·장끝제목 중앙정렬」)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import chapter
import endcard


class CenterRules(unittest.TestCase):
    def test_카드_줄마다_가운데(self):
        self.assertEqual(endcard._row_left("제３장   용의 알"), 40)
        self.assertEqual(endcard._row_left("제１장   열려버린 나락"), 20)
        self.assertEqual(endcard._row_left("끝"), 76)  # 제목 길이와 무관 — 짧은 제3장 카드의 「끝」이 18px 쏠리던 것

    def test_띠_잉크_쏠림_한계(self):
        for extra in (16, 36, 48, 72):
            left = min(range(0, extra + 1, 4), key=lambda x: (abs(2 * x - extra - chapter.BAND_SLACK_PX + 0 - 1), x))
            self.assertLessEqual(abs(2 * left - extra - chapter.BAND_SLACK_PX - 1), 4)


if __name__ == "__main__":
    unittest.main()
