"""전투 블록 코드의 「외톨이 알파벳 숨김」 쓰기(`move.b #6,$FF1Exx.l`) 자리 찾기 — 원본 없이 합성 바이트로."""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import battle


class LetterHide(unittest.TestCase):
    def test_sites_map_to_slot_and_offset(self):
        # 배우 4 의 이름 칸(0xFF1DBC + 4*0x40 + 0x30) + 11 = 0xFF1EF7 → 슬롯 0, 오프셋 11
        code = b"\x4e\x71" + b"\x13\xfc\x00\x06\x00\xff" + struct.pack(">H", 0x1EF7) + b"\x4e\x75"
        self.assertEqual(battle.letter_hide_sites(code), [(2, 0, 11)])

    def test_ignores_non_actor_addresses(self):
        code = b"\x13\xfc\x00\x06\x00\xff" + struct.pack(">H", 0x3606)
        self.assertEqual(battle.letter_hide_sites(code), [])


if __name__ == "__main__":
    unittest.main()
