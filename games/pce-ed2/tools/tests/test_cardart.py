"""카드 안내 화면 그림 — LZSS 왕복 · 타일 평면 왕복 · 층 데이터 모양 · 공유 타일 분리(원본 없이 돈다)."""

import json
import random
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cardart as c


class Lzss(unittest.TestCase):
    def test_왕복(self):
        rnd = random.Random(7)
        data = bytes(rnd.choice([0, 0, 0, 1, 2, 0x55, 0xFF, rnd.randrange(256)]) for _ in range(3000))
        e = c.encode(data)
        d, end = c.decode(e, 0, len(data))
        self.assertEqual(d, data)
        self.assertEqual(end, len(e))

    def test_긴_반복도_왕복(self):
        data = b"\x00" * 500 + bytes(range(40)) * 20
        self.assertEqual(c.decode(c.encode(data), 0, len(data))[0], data)


class Tiles(unittest.TestCase):
    def test_평면_왕복(self):
        rnd = random.Random(3)
        px = np.array([[rnd.randrange(16) for _ in range(8)] for _ in range(8)])
        self.assertTrue(np.array_equal(c.tile_px(c.tile_bytes(px), 0), px))


class Layers(unittest.TestCase):
    def setUp(self):
        self.art = json.loads(c.DATA.read_text(encoding="utf-8"))

    def test_층은_직사각형이고_문자가_맞다(self):
        for s in self.art["signs"]:
            self.assertEqual(len({len(r) for r in s["rows"]}), 1, s["name"])
            self.assertTrue(set("".join(s["rows"])) <= set("FK."), s["name"])
            self.assertIn("F", "".join(s["rows"]))

    def test_화면_안이다(self):
        for s in self.art["signs"]:
            self.assertTrue(0 <= s["x"] and s["x"] + len(s["rows"][0]) <= 256, s["name"])
            self.assertTrue(0 <= s["y"] and s["y"] + len(s["rows"]) <= 232, s["name"])


class Repack(unittest.TestCase):
    def _vram(self):
        v = bytearray(0x4000)
        for i in range(0x400):  # BAT: 모든 칸이 타일 0x40(빈)
            v[i * 2 : i * 2 + 2] = (0x2040).to_bytes(2, "little")
        # 칸 (0,0),(1,0) 이 같은 타일 0x50 을 쓴다
        v[0:2] = (0x2050).to_bytes(2, "little")
        v[2:4] = (0x2050).to_bytes(2, "little")
        return bytes(v)

    def test_공유_타일은_바뀐_칸만_새_타일을_받는다(self):
        scr = c.Screen(self._vram())
        scr.idx[0:8, 8:16] = 5  # 둘째 칸만 그린다
        out = scr.repack()
        b0 = int.from_bytes(out[0:2], "little")
        b1 = int.from_bytes(out[2:4], "little")
        self.assertEqual(b0 & 0xFFF, 0x50)  # 안 바뀐 칸은 그대로
        self.assertGreaterEqual(b1 & 0xFFF, c.FIRST_FREE_TILE)
        self.assertEqual(b1 >> 12, 2)  # 팔레트 유지
        self.assertTrue(np.array_equal(c.tile_px(out, b1 & 0xFFF), np.full((8, 8), 5)))

    def test_안_바뀌면_그대로다(self):
        v = self._vram()
        self.assertEqual(c.Screen(v).repack(), v)


if __name__ == "__main__":
    unittest.main()
