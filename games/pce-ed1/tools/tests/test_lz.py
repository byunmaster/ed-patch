"""LZ 코덱 — **원본 없이** 돈다. 디코더 규칙(링 절대 인덱스 · 0xEF 시작 · 0 초기화)을 못 박는다."""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lz


class RoundTrip(unittest.TestCase):
    def rt(self, data: bytes):
        packed = lz.encode(data)
        out, used = lz.decode(packed, len(data))
        self.assertEqual(out, data)
        self.assertEqual(used, len(packed))
        return packed

    def test_리터럴만(self):
        self.rt(bytes(range(20)))

    def test_반복은_되참조로_줄어든다(self):
        p = self.rt(b"\x1f" + "セリオス".encode("cp932") + b"\x04" + b"abcabcabcabc" * 8)
        self.assertLess(len(p), 40)

    def test_링_초기값_0_참조(self):
        # 아직 안 쓴 링 자리는 0 — 0 런은 되참조 한 번(2B)으로 줄어야 한다
        p = self.rt(b"\x00" * 17)
        self.assertLessEqual(len(p), 1 + 1 + 1 + 1)  # 헤더 + 플래그 + 인덱스 (+여유)

    def test_임의_문안(self):
        rnd = random.Random(7)
        words = ["おはよう", "王子さま", "ライアス", "\x01", "\x05", "。", "セリオス"]
        for _ in range(20):
            s = "".join(rnd.choice(words) for _ in range(rnd.randint(1, 200)))
            self.rt(s.encode("cp932") + b"\x00")

    def test_긴_런은_17로_잘린다(self):
        self.rt(b"A" * 100)

    def test_헤더는_0만_안다(self):
        with self.assertRaises(ValueError):
            lz.decode(b"\x01\x80A", 1)


if __name__ == "__main__":
    unittest.main()
