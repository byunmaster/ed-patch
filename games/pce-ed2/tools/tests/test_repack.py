"""덩이 다시 싣기 — **원본 없이** 돈다(합성 패키지). 제자리 · 이사 · 안 고친 덩이 불변 · 표 갱신."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lz
import package
import repack
from test_package import build

TEXTS = [b"\x16abc\x00\x16def\x00" * 5, b"hello world\x00" * 9, b"line\x00" * 30]


def dec(pkg: bytes, start: int, n: int) -> bytes:
    return lz.decode(pkg, start, n)[0]


class Repack(unittest.TestCase):
    def setUp(self):
        self.pkg, _ = build(TEXTS)
        _first, _limit, self.real = repack.text_region(self.pkg)
        self.starts = [a for a, _b in self.real]

    def test_안_고치면_바이트도_같다(self):
        new, place = repack.repack(self.pkg, {})
        self.assertEqual(new, self.pkg)
        self.assertEqual(place, {})

    def test_작아지면_제자리_뒤_덩이는_안_움직인다(self):
        a = self.starts[1]
        small = b"hi\x00"
        new, place = repack.repack(self.pkg, {a: small})
        self.assertEqual(place[a], a)
        self.assertEqual(dec(new, a, len(small)), small)
        # 안 고친 덩이는 칸 그대로
        c0, c2 = self.real[0], self.real[2]
        self.assertEqual(new[c0[0] : c0[1]], self.pkg[c0[0] : c0[1]])
        self.assertEqual(new[c2[0] : c2[1]], self.pkg[c2[0] : c2[1]])

    def test_커지면_이사하고_표가_따라간다(self):
        a = self.starts[0]
        big = bytes(range(1, 250)) * 6  # 압축이 안 되는 큰 덩이
        new, place = repack.repack(self.pkg, {a: big})
        self.assertNotEqual(place[a], a)
        _t, tab = package.msg_table(new)
        self.assertIn(place[a], tab)
        self.assertNotIn(a, tab)
        self.assertEqual(dec(new, place[a], len(big)), big)
        # 다른 덩이는 안 움직였다
        for s, e in self.real[1:]:
            self.assertEqual(new[s:e], self.pkg[s:e])

    def test_자리가_없으면_멈춘다(self):
        a = self.starts[0]
        huge = bytes(range(1, 250)) * 100
        with self.assertRaises(repack.RepackError):
            repack.repack(self.pkg, {a: huge})

    def test_모르는_시작은_멈춘다(self):
        with self.assertRaises(repack.RepackError):
            repack.repack(self.pkg, {12345: b"x\x00"})


if __name__ == "__main__":
    unittest.main()
