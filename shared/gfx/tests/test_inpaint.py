"""패치 인페인트 회귀 — 결정성과 「구멍이 남지 않는가」."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from shared.gfx import inpaint


def _scene():
    """가로 줄무늬 배경 + 한복판에 지워야 할 사각형."""
    y = np.arange(64)[:, None]
    x = np.arange(96)[None, :]
    one = np.ones((64, 96), int)
    base = np.dstack(
        [(y * 7 + x * 3) % 200 + 30, ((y * 11) % 180 + 40) * one, ((x * 5) % 160 + 50) * one]
    )
    mask = np.zeros((64, 96), bool)
    mask[26:38, 40:58] = True
    src = np.ones((64, 96), bool)
    return base.astype(np.float32), mask, src


class TestInpaint(unittest.TestCase):
    def test_fills_every_hole(self):
        base, mask, src = _scene()
        m = mask.copy()
        inpaint.fill(base, m, src & ~mask)
        self.assertEqual(int(m.sum()), 0, "구멍이 남았다")

    def test_deterministic(self):
        # 🔴 레포 제1 원칙 — 같은 입력이면 같은 바이트. 무작위가 섞이면 여기서 걸린다.
        base, mask, src = _scene()
        a = inpaint.fill(base, mask.copy(), src & ~mask)
        b = inpaint.fill(base, mask.copy(), src & ~mask)
        self.assertTrue(np.array_equal(a, b))

    def test_keeps_known_pixels(self):
        base, mask, src = _scene()
        out = inpaint.fill(base, mask.copy(), src & ~mask)
        self.assertTrue(np.array_equal(out[~mask], base[~mask]), "성한 화소를 건드렸다")


if __name__ == "__main__":
    unittest.main()
