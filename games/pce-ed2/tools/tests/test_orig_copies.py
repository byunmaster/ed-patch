"""원판 사본 잔존 검사 — 합성 바이트로 걸리는 꼴과 안 걸리는 꼴을 못 박는다(원본 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_orig_copies as c

TEXT = bytes(range(0x30, 0x30 + 80))  # 서로 다른 바이트 80 — 압축 블록처럼 보이는 덩이


def img(*placements: tuple[int, bytes], size: int = 4096) -> bytearray:
    b = bytearray(b"\xff" * size)
    for at, data in placements:
        b[at : at + len(data)] = data
    return b


class Copies(unittest.TestCase):
    def test_고친_덩이의_사본이_남으면_걸린다(self):
        orig = img((100, TEXT), (2000, TEXT))
        prod = img((100, b"\xaa" * 80), (2000, TEXT))  # 100 만 고치고 2000 의 사본은 그대로
        _ch, found = c.find_copies(bytes(orig), bytes(prod))
        self.assertEqual(sorted(found), [2000])

    def test_사본도_같이_고쳤으면_안_걸린다(self):
        orig = img((100, TEXT), (2000, TEXT))
        prod = img((100, b"\xaa" * 80), (2000, b"\xaa" * 80))
        _ch, found = c.find_copies(bytes(orig), bytes(prod))
        self.assertEqual(found, {})

    def test_채움_무늬는_앵커가_못_된다(self):
        orig = img((100, b"\x00" * 80), (2000, b"\x00" * 80))
        prod = img((100, b"\xaa" * 80), (2000, b"\x00" * 80))
        _ch, found = c.find_copies(bytes(orig), bytes(prod))
        self.assertEqual(found, {})

    def test_짧은_덩이는_글자_쌍이_있을_때만_문안으로_센다(self):
        pal = bytes(range(1, 40))  # 39B, SJIS 쌍 아님
        sjis = ("あいうえおかきくけこ".encode("cp932")) + b"\x00"  # 21B
        orig = img((100, pal), (300, sjis))
        prod = img((100, b"\xaa" * len(pal)), (300, b"\xaa" * len(sjis)))
        ch = c.chunks(bytes(orig), bytes(prod))
        self.assertEqual([s for s, _ in ch], [300])


if __name__ == "__main__":
    unittest.main()
