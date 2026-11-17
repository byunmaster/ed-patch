"""쪽 머리 점프 보정(`translate.remap_page_jumps`) — 마스터 11-18 씬 50 「라고요,」: 메시지 밖 `0F` 가 둘째 쪽 머리로 들어갈 때 새 쪽 머리로 옮긴다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import messages as M
import translate as T


class WalkPagesTest(unittest.TestCase):
    def test_walk_counts_page_ops_by_tokens(self):
        # 글자(2B) 두 개 · 쪽(05) · 글자 · 쪽 · 글자 — 글자 둘째 바이트가 05 여도 쪽으로 안 센다
        buf = bytes([0xF1, 0x05, 0xF1, 0x05, 0x05, 0xF1, 0x10, 0x05, 0xF1, 0x20, 0x00])
        self.assertEqual(T._walk_pages(buf, 0, 1, False), 5)
        self.assertEqual(T._walk_pages(buf, 0, 2, False), 8)
        self.assertIsNone(T._walk_pages(buf, 0, 3, False))

    def test_walk_follows_splice_tail_jump(self):
        base = M.BASE
        tail = 12
        buf = bytearray(20)
        buf[0:2] = bytes([0xF1, 0x01])
        buf[2] = M.JUMP
        buf[3], buf[4] = (base + tail) & 0xFF, (base + tail) >> 8
        buf[tail : tail + 4] = bytes([0xF1, 0x02, 0x05, 0xF1])
        self.assertEqual(T._walk_pages(bytes(buf), 0, 1, True), tail + 3)


if __name__ == "__main__":
    unittest.main()
