"""HUD 그림 회귀 — **원본 없이 돈다**(레포 규약).

여기서 못 박는 건 **실제로 물린 사고 둘**이다.

🔴 ① **배경/잉크가 50:50 이면 개수로 못 가른다.** 상태 라벨 10×10 은 잉크와 배경이
   **정확히 반반**이라 `argmax`/`argmin` 이 같은 값을 골라 **글자가 배경색으로 그려진다**
   — 칸이 통째로 빈다(2026-08-26 실측). `draw_status()` 는 **테두리**로 배경을 정한다.
🔴 ② **배경은 0 이 아닐 수 있다.** 같은 그림이 `/FRAME.DAT`(배경 0) 과 `/STAT.DAT`
   (배경 39) 에 따로 있다. 0 으로 못 박으면 STAT 사본에서 조용히 반전된다.

⚠ 폰트가 필요해서 글리프는 가짜로 넣는다 — 여기서 보는 건 **색을 고르는 규칙**이지
  글자 모양이 아니다.
"""

import os
import sys
import unittest

import numpy as np

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import patch_gfx_hud as H


class FakeBdf:
    """`bits()` 만 흉내 낸다 — 대각선 하나."""

    ascent = 9

    def bits(self, ch, rows, width, dy):
        g = np.zeros((rows, width), bool)
        for i in range(2, min(rows, width) - 1):  # ⚠ 모서리를 비운다 — 테두리 판정을 봐야 한다
            g[i, i] = True
        return g


def block(bg, ink):
    """잉크와 배경이 **정확히 50:50** 인 10×10 — 실제 라벨과 같은 조건."""
    b = np.full((H.STATUS_BOX, H.STATUS_BOX), bg, np.uint8)
    b[5:, :] = ink  # 아래 절반
    b[0, 0] = bg  # 테두리 모서리는 배경이어야 한다
    b[5:, 0] = bg  # 왼쪽 테두리도 배경으로 (아래 절반의 첫 열)
    b[9, 1:] = ink
    return b


class DrawStatus(unittest.TestCase):
    def test_tie_does_not_paint_ink_as_background(self):
        """🔴 50:50 이어도 잉크와 배경이 갈려야 한다."""
        for bg, ink in ((0, 148), (39, 146), (146, 39)):
            with self.subTest(bg=bg, ink=ink):
                old = block(bg, ink)
                self.assertEqual(
                    sorted({int(v) for v in np.unique(old)}), sorted({bg, ink}), "시험 자료 오류"
                )
                new, changed = H.draw_status(old, "수", FakeBdf())
                vals = {int(v) for v in np.unique(new)}
                self.assertIn(bg, vals, "배경이 사라졌다")
                self.assertIn(ink, vals, "잉크가 배경색으로 그려졌다 — 칸이 빈다")
                self.assertTrue(changed, "바뀐 화소가 0")

    def test_background_is_not_hardcoded_zero(self):
        """🔴 `/STAT.DAT` 은 배경이 39 다 — 0 으로 못 박으면 반전된다."""
        new, _ = H.draw_status(block(39, 146), "수", FakeBdf())
        self.assertEqual(int(new[0, 0]), 39, "테두리가 배경(39)이 아니다")
        self.assertNotIn(0, {int(v) for v in np.unique(new)}, "쓰지도 않는 0 이 들어갔다")


class StatusTable(unittest.TestCase):
    def test_every_label_has_both_sites(self):
        """라벨마다 자리가 **둘**이다 — 하나만 고치면 화면에 원문이 남는다."""
        for fo, so, jp in H.STATUS:
            self.assertTrue(fo and so, f"{jp}: 자리가 비었다")
            self.assertTrue(H.status_kr(jp).strip(), f"{jp}: 우리 표기가 없다(정본 ui)")
        offs = [(H.FRAME, fo) for fo, _, _ in H.STATUS]
        offs += [(H.STAT, so) for _, so, _ in H.STATUS]
        self.assertEqual(len(offs), len(set(offs)), "같은 자리를 둘이 가졌다")

    def test_strides_differ_per_file(self):
        """⚠ 스트라이드를 하나로 못 박으면 STAT 사본이 어긋난다."""
        self.assertEqual(H.STATUS_STRIDE[H.FRAME], H.ATO_STRIDE)
        self.assertNotEqual(H.STATUS_STRIDE[H.STAT], H.STATUS_STRIDE[H.FRAME])


if __name__ == "__main__":
    unittest.main(verbosity=2)
