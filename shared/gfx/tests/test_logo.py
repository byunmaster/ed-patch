"""타이틀 로고 자간 회귀 — 「광학 간격이 정말 같은가」."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from shared.gfx import logo


class TestTitleLogo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.im = logo.title_logo()

    def test_four_letters_and_aspect(self):
        # 원본 한자 상자(290x69)에 담기려면 비율이 그 언저리여야 한다
        self.assertAlmostEqual(self.im.width / self.im.height, 4.29, delta=0.15)
        a = np.array(self.im)
        self.assertGreater(int((a[:, :, 3] > 60).sum()), 100_000)

    def test_gaps_match_canon(self):
        """정본의 글자 간격이 확정값과 같은가.

        ⚠ 자간은 **계산으로 안 닫힌다** — 균등도 광학(넓이 맞춤)도 유저 눈에는 틀렸고,
          둘 사이에서 사람이 골랐다(`GAPS`). 그래서 시험은 「공식이 맞나」가 아니라
          「정본이 확정값대로인가」를 본다.
        """
        a = np.array(self.im)
        rgb = a[:, :, :3].astype(np.int32)
        _owner, xb = logo.split(rgb)
        got = tuple(xb[i + 1][0] - xb[i][1] - 1 for i in range(3))
        for g, want in zip(got, logo.GAPS, strict=True):
            self.assertLessEqual(abs(g - want), 1, f"간격이 다르다: {got} vs {logo.GAPS}")

    def test_background_is_transparent(self):
        # ⚠ 원화는 검은 배경이 구워져 있다 — 알파를 못 만들면 지도 위에 검은 상자가 뜬다
        a = np.array(self.im)
        corner = a[:8, :8, 3]
        self.assertEqual(int(corner.max()), 0, "모서리가 불투명하다 — 알파 추출 실패")


if __name__ == "__main__":
    unittest.main()
