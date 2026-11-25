"""컨테이너 밖 씬 블록 사본 게이트(`check_orphan_blocks`) — 사본 판정(`same_block`)이 LZ 스트림을 풀어 원판 블록과 비교하는지(양성 · 음성 대조)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_orphan_blocks as C
import lz


class SameBlock(unittest.TestCase):
    def setUp(self):
        self.data = bytes(range(200)) * 3 + b"abcabcabc" * 20
        enc = lz.encode(self.data)
        self.b = {"packed": len(enc), "len": len(self.data), "data": self.data}
        self.track = b"\x55" * 100 + enc + b"\xaa" * 200

    def test_positive(self):
        self.assertTrue(C.same_block(self.track, 100, self.b))

    def test_negative_wrong_place_and_changed(self):
        self.assertFalse(C.same_block(self.track, 101, self.b))
        bad = bytearray(self.track)
        bad[100 + 5] ^= 0xFF
        self.assertFalse(C.same_block(bytes(bad), 100, self.b))
        self.assertFalse(C.same_block(b"", 0, self.b))


if __name__ == "__main__":
    unittest.main()
