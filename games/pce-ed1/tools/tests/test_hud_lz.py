"""HUD 글자판 LZ(`hud_lz`) — 원본 없이 도는 왕복·비트 순서 시험."""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import hud_lz


class HudLz(unittest.TestCase):
    def roundtrip(self, data):
        enc = hud_lz.encode(data)
        dec, _ = hud_lz.decode(enc + bytes(4), 0, len(data))
        self.assertEqual(dec, data)
        return enc

    def test_roundtrip_random_and_runs(self):
        rnd = random.Random(26)
        data = bytes(rnd.randrange(4) for _ in range(900)) + bytes(300) + b"\x7f\x84" * 200
        self.assertLess(len(self.roundtrip(data)), len(data))

    def test_length_bits_follow_offset_byte(self):
        """길이 4비트가 플래그 바이트 경계를 넘으면 새 플래그는 오프셋 바이트 **뒤**에 온다."""
        self.roundtrip(bytes(range(7)) + bytes(range(7)) * 3)

    def test_planar_roundtrip(self):
        t = bytes(range(32))
        self.assertEqual(hud_lz.vram_to_planar(hud_lz.planar_to_vram(t)), t)


if __name__ == "__main__":
    unittest.main()
