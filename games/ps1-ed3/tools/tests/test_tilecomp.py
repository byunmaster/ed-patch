"""안 B 모델(타일 합성) — 줄 전체를 픽셀 위치에 그린 것과 타일 단위 합성이 같은가 + 18B 패킹 왕복."""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tilecomp as T

W = 12 * 40  # 줄 폭(비트) — 24칸보다 넉넉히


def naive_tiles(glyphs):
    """[(글리프 12행, adv)] → 줄 전체를 한 번에 그린 뒤 12px 씩 자른 타일(12행씩)."""
    line = [0] * 12
    pos = 0
    for rows, adv in glyphs:
        if adv:
            for r in range(12):
                line[r] |= rows[r] << (W - pos - 12)
        pos += adv
    ntiles = (pos + 11) // 12 + 1
    return [[(line[r] >> (W - 12 * (t + 1))) & 0xFFF for r in range(12)] for t in range(ntiles)]


class TestTileComp(unittest.TestCase):
    def test_pack_roundtrip(self):
        rng = random.Random(1)
        for _ in range(50):
            rows = [rng.randrange(4096) for _ in range(12)]
            self.assertEqual(T.unpack(T.pack(rows)), rows)
        b = bytes(range(18))
        self.assertEqual(T.pack(T.unpack(b)), b)

    def test_composition_matches_a_line_drawn_at_pixel_positions(self):
        """🔴 반각(6px)·전각(12px) 섞인 줄을 타일 단위로 합성한 결과가, 줄 전체를 픽셀 위치에 그린 뒤 자른 것과 같다."""
        rng = random.Random(7)
        for trial in range(200):
            glyphs = []
            for _ in range(rng.randrange(1, 23)):
                adv = rng.choice((6, 12, 12))
                rows = [rng.randrange(4096) for _ in range(12)]
                if adv == 6:  # 6px 글자는 잉크가 왼쪽 6열 안(엔진 폰트 규약)
                    rows = [r & 0xFC0 for r in rows]
                glyphs.append((rows, adv))
            line = T.Line()
            tiles = {}
            for rows, adv in glyphs:
                for t, tile in line.put(rows, adv):
                    tiles[t] = tile  # 마지막으로 쓴 것이 화면에 남는다
            want = naive_tiles(glyphs)
            for t, tile in tiles.items():
                self.assertEqual(tile, want[t], (trial, t))
            # 글자가 닿은 타일은 전부 한 번은 써졌다(빈 타일은 안 써도 배경)
            for t, w in enumerate(want):
                if any(w):
                    self.assertIn(t, tiles, (trial, t))

    def test_zero_advance_draws_nothing_and_keeps_position(self):
        line = T.Line()
        line.put([0xFFF] * 12, 12)
        pos = line.pos
        out = line.put([0xFFF] * 12, 0)
        self.assertEqual(line.pos, pos)
        self.assertEqual(out[0][0], pos // 12)

    def test_half_width_pair_shares_a_tile(self):
        """공백(6px) 다음 글자는 같은 타일의 오른쪽 절반에 들어간다 — 칸이 하나 절약된다."""
        line = T.Line()
        line.put([0] * 12, 6)  # 공백
        out = line.put([0xFFF] * 12, 12)
        self.assertEqual([t for t, _ in out], [0, 1])
        self.assertEqual(out[0][1], [0x03F] * 12)  # 왼쪽 타일의 오른쪽 절반
        self.assertEqual(out[1][1], [0xFC0] * 12)  # 넘친 왼쪽 6열 → 다음 타일 왼쪽


if __name__ == "__main__":
    unittest.main()
