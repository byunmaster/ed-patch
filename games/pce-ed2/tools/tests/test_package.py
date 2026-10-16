"""패키지 머리표 · 메시지 표 · 덩이 분할 — **원본 없이** 돈다(합성 패키지)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lz
import package


def build(texts: list[bytes], table_at: int = 0x100) -> tuple[bytes, list[bytes]]:
    """머리표 + 메시지 표 + 덩이들 + 채움(마지막 표 항목이 가리키는 끝 표시)으로 된 패키지."""
    n = len(texts)
    body_at = table_at + 2 * (n + 1)
    packed = [lz.encode(t) for t in texts]
    starts, p = [], body_at
    for c in packed:
        starts.append(p)
        p += len(c)
    starts.append(p)  # 끝 표시
    pkg = bytearray(0x4000)
    pkg[0:9] = bytes([0x4C, 0x15, 0x60] * 3)
    pkg[12:15] = bytes([0, table_at & 255, 0x40 | (table_at >> 8)])  # 항목 4 → 뱅크 +2 ($40 = 2<<5)
    # 뱅크 오프셋을 쓰지 않는 단순형: 항목 4 의 상대 뱅크 = 0, hi 윗 3비트 = 0
    pkg[12:15] = bytes([0, table_at & 255, table_at >> 8])
    for i, s in enumerate(starts):
        pkg[table_at + 2 * i] = s & 255
        pkg[table_at + 2 * i + 1] = s >> 8
    for s, c in zip(starts, packed, strict=False):
        pkg[s : s + len(c)] = c
    pkg[starts[-1] : starts[-1] + 2048] = b"\xff" * 2048
    return bytes(pkg), packed


class Pkg(unittest.TestCase):
    def test_표와_덩이_경계(self):
        texts = [b"\x16abc\x00\x16def\x00" * 5, b"hello world\x00" * 9, b"\x00"]
        pkg, _ = build(texts)
        T, _tab = package.msg_table(pkg)
        self.assertEqual(T, 0x100)
        ch = package.chunks(pkg)
        self.assertEqual(len(ch), len(texts) + 1)  # 끝 표시 포함
        for (a, b), t in zip(ch, texts, strict=False):
            d, pos = package.decode_chunk(pkg, a, b)
            self.assertEqual(pos, b)
            self.assertEqual(d[: len(t)], t)

    def test_포인터_부호화(self):
        # hi 윗 3비트 = 뱅크 가산 · 아래 5비트 = 뱅크 안 주소
        b = bytes([1, 0x34, 0x52]) + bytes(3)
        self.assertEqual(package.ptr(b, 0), (1, (1 + 2) * 8192 + 0x1234))


if __name__ == "__main__":
    unittest.main()
