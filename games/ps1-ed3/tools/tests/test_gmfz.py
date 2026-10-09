"""GMF 압축(RLE) — 원본 없이 도는 회귀.

밟은 함정 둘을 박는다:
  · **헤더의 크기는 「푼 크기 − 1」이다.** 그걸 모르고 「입력을 다 쓸 때까지」 풀었더니
    66,080 이어야 할 것이 197,688 이 됐다(뒤의 패딩까지 풀었다).
  · **LZ 가 아니라 RLE 다.** 오프셋·길이 분할을 스무 가지 넘게 맞춰 보다 갈렸던 자리가
    「길이 2 매치가 `01 01` 을 내야 한다」였는데, 실은 **같은 바이트 두 번**이었다.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gmfz


def block(payload_ops, size):
    return bytes([0x4E, 0x00]) + b"\x01\x03" + struct.pack("<I", size - 1) + payload_ops


class TestGmfz(unittest.TestCase):
    def test_literal_run(self):
        # 0x82 = 리터럴 3개
        out, short = gmfz.decompress(block(b"\x82\x11\x22\x33", 3))
        self.assertEqual(out, b"\x11\x22\x33")
        self.assertEqual(short, 0)

    def test_repeat_run(self):
        # 0x02 = 다음 바이트 3번
        out, _ = gmfz.decompress(block(b"\x02\xab", 3))
        self.assertEqual(out, b"\xab\xab\xab")

    def test_tim_prefix(self):
        """실측 스트림 앞부분 — TIM 헤더가 정확히 나와야 한다."""
        # `..\\MAP\\B_000.TI3` 의 실제 스트림 앞 19바이트
        comp = bytes.fromhex("8010020080090200810c02030082e001000101")
        out, _ = gmfz.decompress(block(comp, 20))
        self.assertEqual(out[:12], bytes.fromhex("10000000090000000c020000"))

    def test_size_is_minus_one(self):
        """🔴 헤더 값 그대로 믿으면 한 바이트 짧다."""
        kind, size = gmfz.parse_header(block(b"", 100))
        self.assertEqual(size, 100)

    def test_stops_at_declared_size(self):
        """선언 크기에서 **멈춘다** — 뒤에 패딩이 남아 있어도 안 푼다."""
        comp = b"\x7f\xaa" * 8  # 매번 128바이트
        out, _ = gmfz.decompress(block(comp, 200))
        self.assertEqual(len(out), 200)

    def test_short_is_reported(self):
        """모자라면 0 으로 채우되 **조용히 넘어가지 않는다**."""
        out, short = gmfz.decompress(block(b"\x02\xab", 100))
        self.assertEqual(len(out), 100)
        self.assertEqual(short, 97)

    def test_roundtrip(self):
        import random

        rnd = random.Random(1234)
        for _ in range(20):
            data = bytearray()
            while len(data) < 3000:
                if rnd.random() < 0.5:
                    data += bytes([rnd.randrange(256)]) * rnd.randrange(1, 200)
                else:
                    data += bytes(rnd.randrange(256) for _ in range(rnd.randrange(1, 300)))
            data = bytes(data)
            back, short = gmfz.decompress(gmfz.wrap(data))
            self.assertEqual(back, data)
            self.assertEqual(short, 0)

    def test_not_a_block(self):
        self.assertIsNone(gmfz.parse_header(b"\x00" * 16))
        with self.assertRaises(gmfz.GmfzError):
            gmfz.decompress(b"\x00" * 16)


if __name__ == "__main__":
    unittest.main()
