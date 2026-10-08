"""「…」 점 셋은 한국식 바닥(마침표 높이)에 — 일본식 가운데 점이면 안 된다(마스터 10-08, 전 기종 공통). 원본 롬 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hangul_font  # noqa: E402


class Ellipsis(unittest.TestCase):
    def test_점_셋은_마침표_높이(self):
        font = hangul_font.load_font()
        dots = {i for i, r in enumerate(hangul_font.render("…", font)) if r}
        period = {i for i, r in enumerate(hangul_font.render(".", font)) if r}
        self.assertEqual(dots, period)  # 같은 행(바닥) — 글자 가운데(8행 언저리)가 아니다
        self.assertTrue(min(dots) >= 11)


if __name__ == "__main__":
    unittest.main()
