"""`graphics.overlay` — 칸 밖은 바이트까지 그대로, 칸 안만 바뀐다(원본 없이 돈다)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import graphics


def _tim(w_px, h):
    # 4bpp: 한 워드 = 4픽셀. 바탕 색인 7, 칸 밖 「흰색」은 색인 1(0 과 같은 색) — 되짚기 함정 재현.
    stride = w_px // 2
    pix = bytearray([0x77] * stride * h)
    pix[0] = 0x11
    t = {"bpp": 4, "w": w_px // 4, "h": h, "end": 16 + len(pix)}
    return bytes(16) + bytes(pix), t


class TestOverlay(unittest.TestCase):
    def test_only_clear_box_changes(self):
        raw, t = _tim(64, 32)
        spec = {
            "clear": [8, 8, 40, 20],
            "bg_at": [20, 20],
            "ink_at": [0, 0],
            "font": "Galmuri14",
            "dx": 0,
            "dy": -3,
            "pitch": 15,
            "lines": [[9, 8, "예"]],
        }
        out = graphics.overlay(raw, t, spec)
        self.assertEqual(len(out), len(raw))
        stride = 32
        changed = set()
        for i, (a, b) in enumerate(zip(raw, out, strict=True)):
            if a != b:
                k = i - 16
                self.assertGreaterEqual(k, 0, "헤더가 바뀌었다")
                changed.add((k % stride * 2, k // stride))
        self.assertTrue(changed, "글자가 안 그려졌다")
        for x, y in changed:
            self.assertTrue(8 <= x < 48 and 8 <= y < 28, (x, y))
        self.assertEqual(out[16], 0x11, "칸 밖 색인이 바뀌었다")


if __name__ == "__main__":
    unittest.main()
