"""조사 훅 표 — 런타임 색인(0x7da0 흉내)과 받침 판정이 음절표와 어긋나지 않나."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import josa_tables as J


class TestJosaTables(unittest.TestCase):
    def test_roundtrip(self):
        J.check()

    def test_samples(self):
        for ch, want in (
            ("스", False),
            ("난", True),
            ("일", True),
            ("1", True),
            ("2", False),
            ("A", False),
        ):
            self.assertEqual(J.has_batchim(ch), want, ch)

    def test_sizes(self):
        self.assertEqual(len(J.batchim_bitmap()), 294)
        self.assertEqual(J.digit_mask(), 0b111001011)


if __name__ == "__main__":
    unittest.main()
