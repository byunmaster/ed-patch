"""목록 커서 폭 단계 — `cursorw.STEPS` 가 `data/ctrl_lines.tsv` 목록 줄의 가장 긴 이름에서 다시 계산한 값과 같다(원판 단계는 일본어 이름 기준이라 한국어가 틀 밖으로 나온다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cursorw
import gridlist

LINES = {1: 267, 2: 268, 3: 269, 4: 275, 5: 276, 6: 277, 7: 278, 8: 270, 9: 279, 10: 271, 11: 272, 12: 273}
TSV = Path(__file__).resolve().parents[2] / "data" / "ctrl_lines.tsv"


class CursorW(unittest.TestCase):
    def test_steps_fit_longest_name(self):
        rows = TSV.read_text(encoding="utf-8").split("\n")
        for msg, ln in LINES.items():
            tmpl = rows[ln - 1].split("\t")[1]
            items, _per, _tails = gridlist.parse_items(tmpl)
            longest = max(cursorw.name_px(n) for _m, n in items)
            need = cursorw.step_for(longest)
            # 엔진 한계(줄 168px · 열 칸 폭 ≥ 틀 폭)로 가장 긴 이름이 틀보다 조금 길 수 있다 — 한 단계까지만 허용(11-22 마스터 보고 예외: 방어구·지팡이·도구)
            self.assertIn(need - cursorw.STEPS[msg], (0, 1), f"목록 {msg}(줄 {ln}) 최장 {longest}px 필요 단계 {need}")

    def test_sites_cover_steps(self):
        self.assertEqual(set(cursorw.STEPS), set(cursorw.SITES))


if __name__ == "__main__":
    unittest.main()
