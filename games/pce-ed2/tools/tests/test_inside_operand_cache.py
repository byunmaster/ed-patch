"""`systext._inside_operand` 캐시 — 바이트 값이 키다(11-06 결정성 위반: `id(d)` 키는 해제된 bytes 의 id 재사용으로 다른 뱅크 경계를 읽었다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import systext


def _bank(seed: int) -> bytes:
    # JSR 대상 둘(경계 후보) 사이에 LDA abs 가 낀 가짜 뱅크 — 뱅크마다 경계가 다르다
    b = bytearray(0x200)
    for i, t in enumerate((0x10 + seed, 0x40 + seed, 0x80 + seed)):
        b[0x20 * i : 0x20 * i + 3] = bytes([0x20, t, 0x60])
    return bytes(b)


class Cache(unittest.TestCase):
    def test_value_keyed(self):
        a, b = _bank(0), _bank(7)
        want_a = systext._boundaries(a)
        want_b = systext._boundaries(b)
        self.assertNotEqual(want_a, want_b)
        systext._BOUND.clear()
        systext._inside_operand(a, 5)
        systext._inside_operand(b, 5)
        self.assertEqual(systext._BOUND.get(b), want_b)  # 같은 키 충돌이면 b 가 a 의 경계를 받는다
        systext._inside_operand(bytes(bytearray(a)), 5)  # 같은 값의 다른 객체 — 같은 경계
        self.assertEqual(systext._BOUND.get(a), want_a)


if __name__ == "__main__":
    unittest.main()
