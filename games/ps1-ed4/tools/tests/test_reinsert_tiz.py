"""재삽입 규칙·TIZ 실험 인코더 회귀 — **원본 없이 돈다**."""

import random
import unittest
from types import MappingProxyType

import _path  # noqa: F401
import reinsert
import tiz_fit

from shared.ps1 import tiz


class TestReinsert(unittest.TestCase):
    T = MappingProxyType({"가": 1900, "나": 1901, " ": 610})

    def test_같은_크기는_모자라면_공백으로_채운다(self):
        got = reinsert.codes_for("가나", self.T, same_size_as=[1, 2, 3, 4])
        self.assertEqual(got, [1900, 1901, 610, 610])

    def test_같은_크기가_넘치면_실패(self):
        with self.assertRaises(ValueError):
            reinsert.codes_for("가나가", self.T, same_size_as=[1, 2])

    def test_길이_변경은_자유(self):
        self.assertEqual(len(reinsert.codes_for("가나가나가나", self.T)), 6)


class TestTizEncoder(unittest.TestCase):
    def roundtrip(self, raw):
        for enc in (tiz_fit.encode_plain, tiz_fit.encode_dict):
            self.assertEqual(tiz.decompress(enc(raw)), raw, enc.__name__)

    def test_구조가_있는_데이터(self):
        self.roundtrip(b"\x00" * 300 + b"ab" * 70 + bytes(range(60)) + b"\x07" * 5 + b"xyz")

    def test_사전이_먹는_반복(self):
        self.roundtrip((b"\x10\x32\x54\x76\x98\xba" + bytes(3)) * 40)

    def test_랜덤(self):
        rng = random.Random(3)
        self.roundtrip(bytes(rng.randrange(256) for _ in range(500)))

    def test_리터럴만은_늘_원_크기를_키운다(self):
        """리터럴만으로 담으면 머리 134B 와 op 바이트 때문에 푼 크기보다 커진다 — 압축기가 필요하다."""
        self.assertGreater(tiz_fit.literal_only_size(1000), 1000)


if __name__ == "__main__":
    unittest.main()
