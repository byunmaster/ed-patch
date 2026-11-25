"""패턴 치환 감사 — 디코드 동기 판정 단위 검사(원본 없이)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import pattern_audit


class Reach(unittest.TestCase):
    def test_명령_열_끝의_JSR_은_닿는다(self):
        code = bytes([0xA9, 0x01, 0xA0, 0x05, 0x20, 0xC1, 0x49]) + b"\x20\x3e\x50\x2c\x00\x61"
        self.assertTrue(pattern_audit.reaches(code, 7))

    def test_불법_바이트_자료_속은_안_닿는다(self):
        code = bytes([0x03, 0x02, 0x22, 0x42, 0x82, 0x44, 0xF2, 0xDC]) + b"\x20\x3e\x50\x2c\x00\x61"
        self.assertFalse(pattern_audit.reaches(code, 8))


if __name__ == "__main__":
    unittest.main()
