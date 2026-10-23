"""포인터 목표 검사 — 파서가 놓친 글 목표(목록 밖)가 새는지 합성 데이터로 못 박는다."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_ptr_targets as C
import messages as M


def block_with_pointer_to_text() -> tuple[bytes, int]:
    text = b"\x1f" + "男".encode("cp932") + b"\x04\x01" + "やあ、王子さま".encode("cp932") + b"\x00"
    head = bytes([0x0F, 0x00, 0x00])  # `0F` 점프 — 피연산자를 아래서 채운다
    pad = b"\xea" * 5
    off = len(head) + len(pad)
    head = bytes([0x0F, (M.BASE + off) & 0xFF, (M.BASE + off) >> 8])
    return head + pad + text, off


class PtrTargets(unittest.TestCase):
    def test_파서가_안_잡은_글_목표는_목록_밖으로_센다(self):
        blk, off = block_with_pointer_to_text()
        with mock.patch.object(M, "parse", return_value=[]):  # 파서가 그 구간을 못 훑은 상황
            r = C.scan_block(blk)
        self.assertEqual(r["bad"], [off])

    def test_파서가_잡았으면_통과(self):
        blk, off = block_with_pointer_to_text()
        m = M.Message(start=off + 5, end=len(blk) - 1, tokens=[], speaker="男", common=None)
        with mock.patch.object(M, "parse", return_value=[m]):
            r = C.scan_block(blk)
        self.assertEqual(r["bad"], [])

    def test_분기_머리는_글_목표가_아니다(self):
        b = b"\x1f" + "男".encode("cp932") + b"\x04\x01\x12\x45\x00\x0f\x00\x00" + b"\xea" * 8
        self.assertFalse(C.looks_like_text(b, 0))


if __name__ == "__main__":
    unittest.main()
