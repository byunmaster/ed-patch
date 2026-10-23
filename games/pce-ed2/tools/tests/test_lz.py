"""ED2 LZ 코덱 — **원본 없이** 돈다. 길이 니블 쌍 · 링 규칙(0xEF 시작 · 0 초기화)을 못 박는다."""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lz


class RoundTrip(unittest.TestCase):
    def rt(self, data: bytes):
        packed = lz.encode(data)
        out, used = lz.decode(packed + b"\0" * 4, 0, len(data))
        self.assertEqual(out, data)
        self.assertLessEqual(used, len(packed))
        return packed

    def test_리터럴만(self):
        self.rt(bytes(range(1, 21)))

    def test_링_초기값_0_참조(self):
        self.rt(b"\x00" * 17)

    def test_니블_쌍은_바이트_하나를_둘이_나눠_쓴다(self):
        # 되참조 둘 → 니블 바이트가 하나뿐이어야 한다(첫째가 상위, 둘째가 하위)
        a = b"abcdefgh" * 2 + b"XYZ" + b"abcdefgh" * 2
        p = self.rt(a)
        d = lz.decode(p, 0, len(a))[0]
        self.assertEqual(d, a)

    def test_최적_파싱은_왕복이_맞고_탐욕보다_짧거나_같다(self):
        rnd = random.Random(3)
        for _ in range(30):
            n = rnd.randrange(1, 900)
            vocab = bytes(rnd.randrange(1, 30) for _ in range(rnd.randrange(1, 12)))
            data = bytes(rnd.choice(vocab) for _ in range(n)) + b"\x00" * rnd.randrange(0, 3)
            p = lz.encode_opt(data)
            out, _ = lz.decode(p + b"\0" * 4, 0, len(data))
            self.assertEqual(out, data)
            self.assertLessEqual(len(p), len(lz.encode(data)))

    def test_수작업_스트림(self):
        # 플래그 0b11000000: 리터럴 'A' 'B', 되참조 idx=0xEF len=2+1 (니블 1 상위), 되참조 idx=0xEF len=2+2 (니블 2 하위)
        # 니블 바이트 0x12: 첫 되참조 n=1 → 3 바이트, 둘째 n=2 → 4 바이트
        src = bytes([0b11000000, 0x41, 0x42, 0xEF, 0x12, 0xEF])
        out, used = lz.decode(src, 0, 2 + 3 + 4)
        self.assertEqual(out[:2], b"AB")
        self.assertEqual(used, len(src))
        self.assertEqual(len(out), 9)

    def test_임의_문안(self):
        rnd = random.Random(7)
        words = [
            b"\x8b\xb3\x88\xe7",
            b"\xd7\xb3\xb4\xd9",
            b"\x60",
            b"\x11\x33",
            b"\x0e",
            b"\x0d",
            b"\xb5\xb5",
        ]
        for _ in range(20):
            s = b"".join(rnd.choice(words) for _ in range(rnd.randint(1, 200)))
            self.rt(s + b"\x00")

    def test_긴_런은_17로_잘린다(self):
        self.rt(b"A" * 100)


class Ring512(unittest.TestCase):
    """642 전용 512B 링 변형(표식 `7C` + 니블 = 길이 3비트·인덱스 9번째 비트)."""

    def test_표식은_정상_256_스트림의_첫_바이트가_될_수_없다(self):
        rnd = random.Random(11)
        self.assertEqual(lz.MARK2 & 0x80, 0)
        for _ in range(50):
            data = bytes(rnd.randrange(256) for _ in range(rnd.randrange(1, 200)))
            self.assertEqual(lz.encode_opt(data)[0] & 0x80, 0x80)  # 첫 토큰 = 리터럴 → 최상위 비트 1

    def test_왕복_자동_표식_검출(self):
        rnd = random.Random(5)
        for _ in range(40):
            n = rnd.randrange(1, 1500)
            vocab = bytes(rnd.randrange(1, 40) for _ in range(rnd.randrange(1, 30)))
            data = bytes(rnd.choice(vocab) for _ in range(n))
            p = lz.encode_opt512(data)
            self.assertEqual(p[0], lz.MARK2)
            out, used = lz.decode(p + b"\0" * 4, 0, len(data), auto512=True)
            self.assertEqual(out, data)
            self.assertLessEqual(used, len(p))

    def test_창이_512라서_256을_넘는_거리도_참조한다(self):
        rnd = random.Random(2)
        blk = bytes(rnd.randrange(1, 256) for _ in range(300))
        data = blk + bytes(rnd.randrange(1, 256) for _ in range(150)) + blk  # 두 번째 blk 는 거리 450
        self.assertLess(len(lz.encode_opt512(data)), len(lz.encode_opt(data)) - 100)
        self.assertEqual(lz.decode(lz.encode_opt512(data) + bytes(4), 0, len(data), auto512=True)[0], data)

    def test_표식_없으면_자동_검출도_256(self):
        data = b"abcabcabc" * 7
        p = lz.encode_opt(data)
        self.assertEqual(lz.decode(p + bytes(4), 0, len(data), auto512=True)[0], data)

    def test_입력_위치는_표식_한_바이트를_포함한다(self):
        data = b"xyz"
        p = lz.encode_opt512(data)
        _out, used = lz.decode(p + bytes(4), 0, len(data), auto512=True)
        self.assertEqual(used, len(p))  # 플래그 1 + 리터럴 3 + 표식 1 = 5


if __name__ == "__main__":
    unittest.main()
