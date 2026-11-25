"""패널 지명 칸 가운데 맞춤(labels.recenter_*, 마스터 11-04) — 여백만 다시 정하고 글은 안 건드린다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import labels

G = bytes.fromhex("f148f1d8f2def148f1d8")  # 한글 글리프 5개(60px) — 코드는 아무거나


class Recenter(unittest.TestCase):
    def test_pad_by_width(self):
        self.assertEqual(labels.panel_pad(60), 8)  # 5음절 — 잉크 쏠림 −1
        self.assertEqual(labels.panel_pad(72), 4)  # 6음절 — 가장 가까운 4px 격자(내림 0 이면 쏠림 −5, 올림 4 면 +3 — 11-09 「최대한 가운데」)
        self.assertEqual(labels.panel_pad(48), 16)  # 4음절 — 내림 12 면 쏠림 −5, 16 이면 +3
        self.assertEqual(labels.panel_pad(84), 0)  # 7음절 — 칸이 꽉 찬다
        self.assertEqual(labels.panel_pad(60, b"\x08\x08"), 0)  # 머리 `08` 둘 = 8px 를 뺀다

    def test_line_pads_are_replaced(self):
        raw = bytes([0x06, 0xA0, 0x04]) + G + bytes([0x60, 0x60])
        out = labels.recenter_line(raw)
        self.assertEqual(out, bytes([0x60, 0x60]) + G)  # 앞뒤 여백·스타일 토글 걷고 앞 8px

    def test_box_line_centered(self):
        w4 = bytes.fromhex("f148f1d8f2def148")  # 4음절 48px
        raw = b"\x10\x30" + w4 + b"\x11\x33\x30"  # 여백 없이 글만 — 박스 왼쪽에 붙던 줄
        out = labels.recenter_box(raw)
        self.assertEqual(out, b"\x10\x30" + bytes([0xA0, 0x60, 0x60]) + w4 + bytes([0xA0, 0x60]) + b"\x11\x33\x30")  # 앞 20px · 뒤 16px(합 84)
        self.assertEqual(labels.recenter_box(b"\x10\x30" + w4 + b"\x15\x85\x11\x33\x30"), b"\x10\x30" + w4 + b"\x15\x85\x11\x33\x30")

    def test_wide_line_starts_earlier(self):
        g7 = bytes.fromhex("f148f1d8f2def148f1d8f1d8f1d8")  # 7음절 84px — 칸에 꽉 찬다
        out = labels.recenter_line(bytes([0x06]) + g7 + bytes([0x04]))
        self.assertEqual(out, b"\x09" + g7)  # 시작을 왼쪽 4px(`09`) 앞당겨 잉크가 오른쪽 선에 안 닿는다
        g6 = g7[:12]
        self.assertNotIn(0x09, labels.recenter_line(g6))  # 그 밖의 줄은 그대로

    def test_strip_narrow(self):
        raw = bytes([0x06]) + G + bytes([0x04])
        self.assertEqual(labels.strip_narrow(raw), G + bytes([0x04]))
        self.assertEqual(labels.strip_narrow(bytes([0x16, 0x06]) + G), bytes([0x16, 0x06]) + G)  # 대사 제어가 낀 줄은 그대로

    def test_ctrl_inside_untouched(self):
        raw = G[:4] + bytes([0x15, 0x85]) + G[4:]
        self.assertEqual(labels.recenter_line(raw), raw)


if __name__ == "__main__":
    unittest.main()
