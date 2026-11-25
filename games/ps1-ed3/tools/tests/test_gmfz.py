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

    def test_pair_repeat_run(self):
        """`op & 0x40` = 두 바이트를 (op & 0x3F)+1 번 — 장 끝 띠 시트 `C_203` 에서 발견(10-24).
        이 토큰을 모르면 그 뒤가 통째로 밀려 「짧게 풀림·줄 밀림」이 된다(전 멤버 106개가 그랬다)."""
        out, short = gmfz.decompress(block(b"\x41\x48\x0e", 4))  # 48 0e 48 0e
        self.assertEqual(out, b"\x48\x0e\x48\x0e")
        self.assertEqual(short, 0)
        out, _ = gmfz.decompress(block(b"\x40\x01\x02\x80\x03", 3))  # 01 02 | 리터럴 03
        self.assertEqual(out, b"\x01\x02\x03")

    def test_real_stream_around_pair_run(self):
        """`C_203.TI3` 실측 조각 — `84 1b ff 01 10 41` 뒤 `41 48 0e 80 1b 01 0e 01 48` 이 `48 0e 48 0e 1b 0e 0e 48 48` 로 풀린다."""
        comp = bytes.fromhex("841bff011041" "41480e" "801b" "010e" "0148")
        out, _ = gmfz.decompress(block(comp, 5 + 4 + 1 + 2 + 2))
        self.assertEqual(out[-9:], bytes([0x48, 0x0E, 0x48, 0x0E, 0x1B, 0x0E, 0x0E, 0x48, 0x48]))

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

    def test_compress_caps_literal_and_run_at_64(self):
        """원본 1,814멤버는 리터럴·런이 64 를 넘지 않는다 — 128 리터럴은 게임이 못 풀어 맵이 검게 떴다(10-24)."""
        import random

        rng = random.Random(1)
        data = bytes(rng.randrange(256) for _ in range(1000)) + b"\x07" * 300
        comp = gmfz.wrap(data)[8:]
        i = 0
        while i < len(comp):
            op = comp[i]
            i += 1
            if op & 0x80:
                self.assertLess(op & 0x7F, 64)
                i += (op & 0x7F) + 1
            elif op & 0x40:
                i += 2  # 쌍 반복(횟수 6비트라 늘 ≤ 64)
            else:
                self.assertLess(op, 64)
                i += 1

    def test_compress_to_exact_length(self):
        """멤버 길이에 스트림을 정확히 맞춘다 — 꼬리 0 채움은 게임이 반복 런으로 읽는다(10-24 맵 검정)."""
        import random

        rng = random.Random(2)
        data = bytes(rng.randrange(4) for _ in range(3000))
        base = len(gmfz.wrap(data))
        for extra in (0, 1, 7, 50, 400):
            blob = gmfz.wrap_to(data, base + extra)
            self.assertEqual(len(blob), base + extra)
            back, short = gmfz.decompress(blob)
            self.assertEqual((back, short), (data, 0))
        with self.assertRaises(gmfz.GmfzError):
            gmfz.wrap_to(data, base - 1)

    def test_pair_runs_roundtrip_and_compress(self):
        """16비트 자료(맵 워드)는 쌍 반복으로 작게 압축되고 되풀면 같다."""
        data = (b"\x06\x1a" * 200 + b"\x86\x93" * 3 + bytes(range(40)) + b"\x42\x1e" * 70) * 3
        blob = gmfz.wrap(data)
        self.assertLess(len(blob), len(data) // 8)
        self.assertEqual(gmfz.decompress(blob), (data, 0))
        for extra in (0, 1, 2, 3, 9):
            self.assertEqual(gmfz.decompress(gmfz.wrap_to(data, len(blob) + extra)), (data, 0))

    def test_not_a_block(self):
        self.assertIsNone(gmfz.parse_header(b"\x00" * 16))
        with self.assertRaises(gmfz.GmfzError):
            gmfz.decompress(b"\x00" * 16)


if __name__ == "__main__":
    unittest.main()
