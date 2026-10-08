"""「…」 는 한국식 바닥 — 점 셋이 마침표와 같은 행(10행)에 있다(마스터 10-08, 전 기종 공통 · 일본식 가운데 점 금지)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import font


def rows(g: bytes) -> list[int]:
    return [(g[2 * i] << 8 | g[2 * i + 1]) >> 4 for i in range(12)]


class Ellipsis(unittest.TestCase):
    def test_dots_are_on_the_period_row(self):
        e, p = rows(font.glyph("…")), rows(font.glyph("."))
        ink = [i for i, r in enumerate(e) if r]
        self.assertEqual(ink, [10], "점 셋은 한 행(10행)에만")
        self.assertEqual([i for i, r in enumerate(p) if r], ink, "마침표와 같은 행")
        self.assertEqual(e[10].bit_count(), 3)

    def test_not_in_the_middle(self):
        self.assertEqual(sum(rows(font.glyph("…"))[:9]), 0, "위쪽(가운데) 행에 잉크가 없다")


if __name__ == "__main__":
    unittest.main()
