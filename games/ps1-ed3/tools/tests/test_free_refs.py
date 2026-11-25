"""원판 EXE 재사용 구간 바깥 참조 검사기 — 양성 대조(심은 참조를 잡는가)."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_free_refs as F


class FreeRefs(unittest.TestCase):
    def test_selftest_catches_planted_refs(self):
        self.assertTrue(F.selftest())

    def test_reference_inside_region_ignored(self):
        s = F.REGIONS["R1 커서 훅"][0]
        buf = struct.pack("<I", (3 << 26) | (((s + 8) & 0x0FFFFFFF) >> 2))
        self.assertFalse(F.scan(buf, s).get("R1 커서 훅"))


if __name__ == "__main__":
    unittest.main()
