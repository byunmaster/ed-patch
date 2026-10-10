"""장 카드 꼬리 재배치 — 꼴 판별(`A` 세션 끝 · `B` 단독)과 세션 시작 찾기."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import choice_tail as CT


def blk(off, body, head):
    return {"off": off, "body": body, "head": head}


class CardKind(unittest.TestCase):
    def test_a_ends_with_10_00(self):
        data = bytearray(64)
        data[10:12] = b"\x10\x00"
        self.assertEqual(CT._card_kind(bytes(data), [blk(4, b"x" * 6, "420e")], 0), "A")

    def test_b_needs_head_and_00_09(self):
        data = bytearray(64)
        data[2:12] = CT._CARD_B_HEAD
        data[16:18] = b"\x00\x09"
        self.assertEqual(CT._card_kind(bytes(data), [blk(12, b"x" * 4, "0d0d")], 0), "B")

    def test_other_is_none(self):
        self.assertIsNone(CT._card_kind(bytes(64), [blk(12, b"x" * 4, "0d0d")], 0))

    def test_session_start_walks_0e_chain(self):
        data = bytearray(64)
        data[4:6] = b"\xff\x00"
        data[12] = 0x0E  # 첫 블록(6..12) 뒤 `0E`
        blocks = [blk(6, b"a" * 6, "ff00"), blk(13, b"b" * 4, "420e")]
        self.assertEqual(CT._session_start(bytes(data), blocks, 1), (0, 4))


if __name__ == "__main__":
    unittest.main()
