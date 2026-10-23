"""HUD 그래픽 압축 해제기(`hudlz.decode`) — 손으로 짠 스트림으로 돈다(원본 없이)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hudlz


class Decode(unittest.TestCase):
    def test_날바이트와_복사(self):
        # 제어 11000000: 날바이트 41 42 · 복사(오프셋 EF · 니블 0 → 2바이트)
        out, end = hudlz.decode(bytes([0b11000000, 0x41, 0x42, 0xEF, 0x00]), 0, 4)
        self.assertEqual(out, b"\x41\x42\x41\x42")
        self.assertEqual(end, 5)

    def test_니블은_두_번에_한_바이트를_쓴다(self):
        # 복사 둘: 첫 니블 = 바이트 윗(0), 둘째 = 같은 바이트 아랫(1) → 길이 2 · 3
        src = bytes([0b11001000, 0x41, 0x42, 0xEF, 0x01, 0xEF])
        out, end = hudlz.decode(src, 0, 2 + 2 + 3)
        self.assertEqual(out, b"\x41\x42" + b"\x41\x42" + b"\x41\x42\x41")
        self.assertEqual(end, len(src))


if __name__ == "__main__":
    unittest.main()
