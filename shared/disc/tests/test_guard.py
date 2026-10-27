"""쓰기 가드 회귀 — **원본 없이 돈다**. 무변경 구간 침범·사전조건 불일치는 쓰기 전에 그 자리에서 실패해야 한다."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from shared.disc.guard import Guard, WriteGuard, check_expect


class TestGuard(unittest.TestCase):
    def setUp(self):
        self.g = Guard()
        self.g.add(10, 2048 * 2, [("TOC", 0, 8, "same")])  # lba 10 파일의 앞 8바이트 무변경

    def test_구간_밖은_통과(self):
        base = 10 * 2048
        self.g.check(base + 8, b"\x00\x01", b"\xff\xfe", "x")

    def test_구간_안을_바꾸면_실패(self):
        base = 10 * 2048
        with self.assertRaises(WriteGuard) as cm:
            self.g.check(base, bytes(16), b"\x00" * 3 + b"\x01" + bytes(12), "대본")
        self.assertIn("TOC", str(cm.exception))
        self.assertIn("대본", str(cm.exception))

    def test_구간_안이어도_같은_바이트면_통과(self):
        base = 10 * 2048
        self.g.check(base, bytes(16), bytes(16), "x")

    def test_다른_파일은_안_본다(self):
        self.g.check(99 * 2048, b"\x00\x00", b"\x01\x01", "x")


class TestExpect(unittest.TestCase):
    def test_bytes_사전조건(self):
        check_expect(b"abcdef", b"abc", "x", "lba 1")
        with self.assertRaises(WriteGuard) as cm:
            check_expect(b"abXdef", b"abc", "x", "lba 1")
        self.assertIn("lba 1+0x2", str(cm.exception))

    def test_int_사전조건은_전_범위(self):
        check_expect(bytes(8), 0, "x", "lba 1")
        with self.assertRaises(WriteGuard):
            check_expect(b"\x00" * 7 + b"\x01", 0, "x", "lba 1")


if __name__ == "__main__":
    unittest.main()
