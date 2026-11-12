"""장 끝 띠 다시 쓰기의 회귀 — 칸 목록·타일 배정·줄 배치(가짜 데이터, 원본·글꼴 없이 돈다).

밟은 함정(10-24): ① 쌍 반복 토큰을 몰라 시트가 밀려 풀렸다(`test_gmfz`) ② 두 상태가 같은 타일 번호를 나눠 써서 한쪽 줄을 고치면 다른 쪽이 깨졌다 —
상태마다 새 타일을 받는다(`test_apply_state_allocates_distinct_tiles`) ③ 줄이 칸 영역(`x_lo..x_hi`) 밖이면 화면에서 잘린다(`test_build_line_rejects_overflow`).
"""

import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chapter_end as C

TR = 255


def fake_anm(n_words, base=4):
    """헤더 첫 워드 = 타일 표 시작 + 4(바이트) — base 워드 번호 (w0-4)/2."""
    w0 = base * 2 + 4
    d = bytearray(n_words * 2)
    struct.pack_into("<H", d, 0, w0)
    return d


class TestChapterEnd(unittest.TestCase):
    def test_strip_cells_extends_over_zero_words(self):
        anm = fake_anm(60)
        base = 4
        strips = [{"lo": 10, "hi": 14, "x0": 32}]
        cells = C.strip_cells(strips, anm, base, claimed={10, 12, 14})
        xs = dict(cells)
        self.assertEqual(xs[10], 32)
        self.assertEqual(xs[14], 32 + 16 * 2)
        self.assertEqual(xs[16], 32 + 16 * 3)  # 0 워드라 한 칸 더
        self.assertEqual(xs[8], 32 - 16)

    def test_strip_cells_does_not_take_claimed_words(self):
        anm = fake_anm(60)
        cells = C.strip_cells([{"lo": 10, "hi": 14, "x0": 32}], anm, 4, claimed={10, 12, 14, 16})
        self.assertNotIn(16, dict(cells))

    def test_apply_state_allocates_distinct_tiles(self):
        """같은 내용 반쪽은 한 타일을 나눠 쓰고, 다른 내용은 다른 타일을 받는다 — 빈 반쪽은 0.

        워드 = (윗 타일 << 8) | 아랫 타일, 같은 열(원판 램 실측).
        """
        pix = np.full((64, 64), TR, np.uint8)
        anm = fake_anm(40)
        K = np.full((48, 320), TR, np.uint8)
        K[8:30, 0:16] = 7  # 칸 0: 위·아래 모두 잉크
        K[8:30, 16:32] = 7  # 칸 1: 같은 내용
        K[8:12, 32:48] = 9  # 칸 2: 위 반쪽만
        pool = list(range(1, 16))
        cache = {}
        used = C.apply_state(pix, anm, 4, [(10, 0), (12, 16), (14, 32), (16, 48)], K, 200, pool, TR, cache)
        w = lambda i: struct.unpack_from("<H", anm, (4 + i) * 2)[0]
        self.assertEqual(w(10), w(12))  # 같은 내용 → 같은 타일 쌍
        self.assertNotEqual(w(14), w(10))
        self.assertEqual(w(14) & 0xFF, 0)  # 위 반쪽만 → 아랫 타일(낮은 바이트) 0
        self.assertNotEqual(w(14) >> 8, 0)
        self.assertEqual(w(16), 0)  # 잉크 없음 → 워드 0
        self.assertEqual(len(used), len(set(used)))

    def test_apply_state_pool_exhausted(self):
        pix = np.full((32, 32), TR, np.uint8)
        anm = fake_anm(40)
        K = np.full((48, 320), TR, np.uint8)
        K[8:30, 0:16] = 7
        with self.assertRaises(C.PlanError):
            C.apply_state(pix, anm, 4, [(10, 0)], K, 200, [1], TR, {})

    def test_build_line_rejects_overflow(self):
        quotes = {"「": (np.zeros((4, 4), np.uint8), np.ones((4, 4), bool), 202), "」": (np.zeros((4, 4), np.uint8), np.ones((4, 4), bool), 216)}

        class F:
            def glyph(self, ch):
                return {"enc": ord(ch), "dw": 24, "w": 8, "h": 8, "xo": 0, "yo": 0, "rows": [0xFF] * 8, "bits": 8}

        with self.assertRaises(C.PlanError):
            C.build_line(F(), [("text", "가나다라마바사아자차카타")], quotes, 1, 2, TR, 213, 0, 100)


if __name__ == "__main__":
    unittest.main()
