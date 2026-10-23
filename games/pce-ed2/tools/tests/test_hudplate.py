"""HUD 라벨 도트 · 압축 인코더(`hudlz.encode`) — 원본 없이 합성 데이터로 돈다(도트 파일은 pce-ed1 정본을 읽는다)."""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hudlz
import hudplate


class Tile(unittest.TestCase):
    def test_타일_왕복(self):
        rnd = random.Random(1)
        t = bytes(rnd.randrange(256) for _ in range(32))
        self.assertEqual(hudplate.px_tile(hudplate.tile_px(t)), t)

    def test_색_번호가_평면_비트와_맞다(self):
        t = bytearray(32)
        t[0] = 0x80  # 0행 p0 의 맨 왼쪽 비트 → 색 1
        t[17] = 0x40  # 0행 p3 의 둘째 비트 → 색 8
        px = hudplate.tile_px(bytes(t))
        self.assertEqual((px[0][0], px[0][1]), (1, 8))


class Dots(unittest.TestCase):
    def test_마스터_도트는_8줄_16칸_0열_비어_있다(self):
        d = hudplate.load_dots()
        self.assertEqual((len(d), len(d[0])), (8, 16))
        self.assertFalse(any(r[0] for r in d))

    def test_도트_모양을_그대로_칠한다(self):
        d = hudplate.load_dots()
        zero = bytes(64)  # 원본 타일 대신 빈 판
        # 잉크색 계산이 터지지 않게 글자색 타일을 하나 심는다
        t = bytearray(64)
        t[2 * 1 + 1] = 0xFF  # p1 비트 → 색 2 (바탕 1 이 아닌 색)
        a, b = hudplate.label_tiles(bytes(t), d)
        L, R = hudplate.tile_px(a), hudplate.tile_px(b)
        got = [(L[r] + R[r]) for r in range(8)]
        ink = max(set(x for row in got for x in row if x not in (0, hudplate.BG)), default=None)
        for r in range(8):
            for x in range(1, 16):
                self.assertEqual(got[r][x] != hudplate.BG, bool(d[r][x]), (r, x))
        self.assertIsNotNone(ink)
        self.assertEqual(zero, bytes(64))


class Encode(unittest.TestCase):
    def test_왕복(self):
        rnd = random.Random(7)
        data = bytes(rnd.choice((0, 0, 0, 0xFF, 0x42, rnd.randrange(256))) for _ in range(3000))
        enc = hudlz.encode(data)
        back, end = hudlz.decode(enc + bytes(8), 0, len(data))
        self.assertEqual(back, data)
        self.assertEqual(end, len(enc))
        self.assertLess(len(enc), len(data))

    def test_앞쪽_0_채움을_원천으로_쓴다(self):
        data = bytes(40)
        enc = hudlz.encode(data)
        self.assertLess(len(enc), 20)
        self.assertEqual(hudlz.decode(enc + bytes(8), 0, 40)[0], data)


if __name__ == "__main__":
    unittest.main()
