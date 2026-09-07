"""LZ 코덱 — **원본 없이** 돈다. 왕복 + 헤더 규약 + 길이 부호의 극성을 못 박는다."""

import random
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lz


class RoundTrip(unittest.TestCase):
    def rt(self, data: bytes) -> bytes:
        packed = lz.encode(data)
        out, used = lz.decode(packed, 0)
        self.assertEqual(out, data)
        self.assertEqual(used, len(packed))
        # 헤더 = 길이-1, 색인은 짝수 정렬로 이어진다
        self.assertEqual(struct.unpack("<H", packed[:2])[0], len(packed) - 1)
        self.assertEqual(lz.block_span(packed, 0), len(packed) + (len(packed) & 1))
        return packed

    def test_리터럴만(self):
        self.rt(bytes(range(20)))

    def test_되참조_짧은거리(self):
        p = self.rt(b"\x1e" + "セリオス".encode("cp932") + b"\x04" + b"abcabcabcabc" * 8)
        self.assertLess(len(p), 40)

    def test_되참조_긴거리(self):
        rnd = random.Random(3)
        chunk = bytes(rnd.randrange(256) for _ in range(300))
        filler = bytes(rnd.randrange(256) for _ in range(1000))
        self.rt(chunk + filler + chunk)

    def test_RLE(self):
        p = self.rt(b"\x00" * 5000 + b"A" * 20 + b"B" * 14 + b"C" * 15)
        self.assertLess(len(p), 40)

    def test_길이_경계(self):
        for n in (2, 3, 4, 5, 6, 13, 14, 15, 269, 270, 600):
            self.rt(b"xy" + b"q" * n + b"z" + b"q" * n)

    def test_임의_문안(self):
        rnd = random.Random(7)
        words = ["おはよう", "王子さま", "ライアス", "\x01", "\x05", "。", "セリオス", "\x1e"]
        for _ in range(20):
            s = "".join(rnd.choice(words) for _ in range(rnd.randint(1, 400)))
            self.rt(s.encode("cp932") + b"\x00")

    def test_손으로_짠_스트림(self):
        # 리터럴 'A' · 거리1 길이2('1','0',01,'1') · 끝('1','1',00000,00) · more 0
        # 비트(LSB 부터): 0 1 0 1 | 1 1 0 0 | 0 0 0 → 첫 그룹 8비트 = 0x3A, 다음 워드 = 0
        body = bytes([0x00, 0x3A]) + b"A" + bytes([0x01]) + bytes([0, 0]) + bytes([0]) + bytes([0])
        stream = struct.pack("<H", len(body) + 1) + body
        out, used = lz.decode(stream, 0)
        self.assertEqual(out, b"AAA")
        self.assertEqual(used, len(stream))


if __name__ == "__main__":
    unittest.main()
