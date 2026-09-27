"""빈 공간 할당기(`freespace`) — 원본 없이 도는 시험."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import freespace as F


class Pool(unittest.TestCase):
    def test_alloc_in_order_with_gap(self):
        p = F.Pool([F.Span(0x6D, 0x100, 20, 0xFF, "t")])
        self.assertEqual(p.alloc(0x6D, 8)[1], 0x100)
        self.assertEqual(p.alloc(0x6D, 8)[1], 0x109)  # 한 칸 띄운다
        self.assertIsNone(p.alloc(0x6D, 3))  # 17 쓰고 남은 3 — 틈 1 을 빼면 2

    def test_other_bank_is_not_used(self):
        p = F.Pool([F.Span(0x6D, 0, 64, 0xFF, "t")])
        self.assertIsNone(p.alloc(0x6C, 4))

    def test_check_original_rejects_changed_bytes(self):
        p = F.Pool([F.Span(0x6D, 4, 4, 0xFF, "t")])
        p.check_original(lambda b: b"\0" * 4 + b"\xff" * 4)
        with self.assertRaises(ValueError):
            p.check_original(lambda b: b"\0" * 4 + b"\xff\xff\x00\xff")


if __name__ == "__main__":
    unittest.main()
