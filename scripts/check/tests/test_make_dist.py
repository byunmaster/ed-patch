"""공용 배포 차분 — BPS 인코더·적용기 왕복(같은 크기 · 늘어난 롬 · 줄어든 롬 · 빈 차이)."""

import os
import random
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "publish"
    ),
)

from make_dist import apply_bps, make_bps


def _rt(src, tgt):
    return apply_bps(src, make_bps(src, tgt)) == tgt


class MakeDistBpsTest(unittest.TestCase):
    def setUp(self):
        r = random.Random(7)
        self.src = bytes(r.randrange(256) for _ in range(4096))

    def test_same_size(self):
        t = bytearray(self.src)
        for i in (0, 1, 2, 100, 101, 4095):
            t[i] ^= 0x5A
        self.assertTrue(_rt(self.src, bytes(t)))

    def test_grown_rom(self):
        t = bytearray(self.src)
        t[10] ^= 1
        self.assertTrue(_rt(self.src, bytes(t) + b"\x00" * 1000 + b"KR"))

    def test_shrunk(self):
        self.assertTrue(_rt(self.src, self.src[:3000]))

    def test_identical(self):
        self.assertTrue(_rt(self.src, self.src))

    def test_bad_source_rejected(self):
        p = make_bps(self.src, self.src[::-1])
        with self.assertRaises(SystemExit):
            apply_bps(self.src[:-1] + b"\x00", p)


if __name__ == "__main__":
    unittest.main()
