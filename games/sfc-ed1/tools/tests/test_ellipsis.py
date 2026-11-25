"""「…」 점 셋은 한국식 바닥(마침표 높이)에 — 일본식 가운데 점이면 안 된다(마스터 10-08, 전 기종 공통). 점 하나는 대사 「.」 와 같은 2×2 잉크(마스터 11-16). 원본 롬 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hangul_font  # noqa: E402


class Ellipsis(unittest.TestCase):
    def test_점_셋은_마침표_높이와_모양(self):
        font = hangul_font.load_font()
        er = hangul_font.render("…", font)
        pr = hangul_font.render(".", font)  # 대사창 합성 경로(hook.rawtab)가 쓰는 그림 — 실화면에 찍히는 마침표
        dots = {i for i, r in enumerate(er) if r}
        self.assertEqual(dots, {i for i, r in enumerate(pr) if r})  # 같은 행(바닥) — 글자 가운데(8행 언저리)가 아니다
        self.assertTrue(min(dots) >= 11)
        # 점 하나의 잉크가 마침표와 픽셀 단위로 같다: 마침표 점(열 1-2)을 첫 점(열 0-1)으로 옮겨 견준다
        self.assertEqual([r & 0b11000000 for r in er[12:14]], [(r << 1) & 0b11000000 for r in pr[12:14]])
        self.assertEqual(er[12], 0b11011011)  # 같은 점 셋, 간격 1px

    def test_쉼표_머리는_마침표_점(self):
        font = hangul_font.load_font()
        pr, cr = hangul_font.render(".", font), hangul_font.render(",", font)
        self.assertEqual(cr[12:14], pr[12:14])  # 머리 = 마침표 점 2×2
        self.assertEqual(cr[14], 0b11000000)  # 꼬리(왼쪽 아래)는 유지


if __name__ == "__main__":
    unittest.main()
