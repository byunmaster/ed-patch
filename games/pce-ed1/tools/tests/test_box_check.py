"""희소 카탈로그(`sparse_catalog_and_map`)·`box_check` — 원본 없이 돈다(합성 자료)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import boxpack as bp
import numpy as np


def _tile(seed: int) -> bytes:
    """서로 다른 32B 타일(패딩 없이 결정적)."""
    return bytes((seed * 7 + i * 13) & 0xFF for i in range(32))


class SparseCatalog(unittest.TestCase):
    def setUp(self):
        self.orig = [_tile(i) for i in range(20)]  # 합성 「원본 20장」

    def test_예약_자리는_그대로(self):
        """예약 색인은 새 캔버스가 뭘 원하든 원본 픽셀을 지킨다."""
        reserved = {2, 5, 7}
        cv = np.zeros((8, 8 * 3), np.uint8)  # 1행 3칸, 다 다른 내용
        for c in range(3):
            cv[:, c * 8 : (c + 1) * 8] = bp.tile_px(self.orig[2] if c == 0 else _tile(100 + c))
        catalog, _m, index = bp.sparse_catalog_and_map(cv, self.orig, reserved, 3, 1, max_total=20)
        self.assertEqual(catalog[2], self.orig[2])
        self.assertIn(2, index.values())

    def test_예약_밖_원본_자리를_새_내용으로_재사용(self):
        """예약 안 된 원본 색인(예: 3)은 새 내용으로 갈아 끼울 수 있다 — 번호는 유지."""
        reserved = {0, 1}  # 2,3,... 은 비예약(msg2 가 안 쓴다고 가정)
        new_tile = _tile(999)
        cv = np.zeros((8, 8), np.uint8)
        cv[:, :] = bp.tile_px(new_tile)
        catalog, _m, index = bp.sparse_catalog_and_map(cv, self.orig, reserved, 1, 1, max_total=20)
        self.assertEqual(index[new_tile], 2)  # 제일 낮은 비예약 자리(2)를 받는다
        self.assertEqual(catalog[2], new_tile)
        self.assertEqual(catalog[0], self.orig[0])  # 예약은 안 건드림
        self.assertEqual(catalog[1], self.orig[1])

    def test_예산_초과는_죽는다(self):
        reserved = set(range(19))  # 19장 예약, 자유 자리 딱 1개(19)
        cv = np.zeros((8, 8 * 2), np.uint8)
        cv[:, 0:8] = bp.tile_px(_tile(500))
        cv[:, 8:16] = bp.tile_px(_tile(501))  # 서로 다른 새 타일 2개 — 자유 자리 1개뿐이라 넘친다
        with self.assertRaises(AssertionError):
            bp.sparse_catalog_and_map(cv, self.orig, reserved, 2, 1, max_total=20)

    def test_사이_빈칸은_원본으로_채워진다(self):
        """예약 색인이 커서(예:15) 그 앞의 비예약 자리(예:3)가 안 쓰였으면, 그 자리는
        아무도 안 읽지만 순차 블릿이라 채워는 져야 한다(원본 픽셀로 채움, 무해)."""
        reserved = {0, 15}
        cv = np.zeros((8, 8), np.uint8)
        cv[:, :] = bp.tile_px(self.orig[0])  # 예약 0 과 같은 내용 → 새 자리 안 씀
        catalog, _m, _index = bp.sparse_catalog_and_map(cv, self.orig, reserved, 1, 1, max_total=20)
        self.assertEqual(len(catalog), 16)  # 0..15
        for i in range(1, 15):  # 비예약이라 안 쓰인 자리들 — 원본으로 채워짐
            self.assertEqual(catalog[i], self.orig[i])


class ReservedIndices(unittest.TestCase):
    def test_참조된_색인만_뽑는다(self):
        orig = [_tile(i) for i in range(10)]
        words = [0x47B3, 0x47B7, 0x47B3]  # 0x7B0 기준 색인 3·7 (3 중복)
        self.assertEqual(bp.reserved_indices(orig, words), {3, 7})

    def test_범위_밖은_버린다(self):
        orig = [_tile(i) for i in range(5)]
        words = [0x47B0, 0x4800]  # 0·80 — 80 은 orig 범위(5) 밖이라 버림
        self.assertEqual(bp.reserved_indices(orig, words), {0})


if __name__ == "__main__":
    unittest.main()
