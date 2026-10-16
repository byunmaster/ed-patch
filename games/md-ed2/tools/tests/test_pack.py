"""대본 아카이브 재배치 — **원본 없이** 돈다(합성 블록)."""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import lz


class Pack(unittest.TestCase):
    def test_색인과_왕복(self):
        blocks = [bytes(range(50)) * 3, b"\x1e" + b"abc" * 40, b"x"]
        arch = build.pack_archive(blocks)
        offs = struct.unpack(">3I", arch[:12])
        self.assertEqual(offs[0], 12)  # 첫 값 = 4n
        for o, b in zip(offs, blocks, strict=True):
            self.assertEqual(o % 2, 0)  # 2B 정렬
            self.assertEqual(lz.decode(arch, o)[0], b)

    def test_결정적(self):
        blocks = [bytes(range(200)) * 5]
        self.assertEqual(build.pack_archive(blocks), build.pack_archive(blocks))


if __name__ == "__main__":
    unittest.main()
