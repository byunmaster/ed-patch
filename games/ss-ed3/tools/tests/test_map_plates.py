"""맵 선택 지명판(`map_plates.py`) 회귀 — **원본 없이 돈다**(가짜 팔레트·판으로).

🔴 지키는 것: 판 읽기/쓰기가 역변환이고 · 바깥 둘레(테두리)는 안 건드리고 · 한글 획이 안쪽에만 앉고 ·
   정본에 없는 이름이면 조용히 일본어로 두지 않고 멈춘다.
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import map_plates as M


def fake():
    data = bytearray(M.IMG_AT + M.N * M.PLATE_B)
    rng = np.random.default_rng(0)
    for k in range(M.N):
        a = rng.integers(6, 16, (M.H, M.W)).astype(np.uint8)  # 바탕
        a[0], a[1], a[14], a[15] = 5, 7, 7, 4  # 둘레(바탕 6~15 밖 값도 섞는다)
        a[:, :2], a[:, 78:] = 7, 7
        a[6, 10:20] = 1  # 원문 획
        a[7, 12:18] = 2
        r = ((a[:, 0::2] << 4) | a[:, 1::2]).astype(np.uint8)
        data[M.IMG_AT + k * M.PLATE_B : M.IMG_AT + (k + 1) * M.PLATE_B] = r.tobytes()
    return bytes(data)


class Plates(unittest.TestCase):
    def test_roundtrip(self):
        d = fake()
        _, pl = M.read(d)
        self.assertEqual(M.write(d, pl), d)

    def test_layout(self):
        self.assertEqual(M.layout(2), [4, 65])
        self.assertEqual(M.layout(4)[0], 4)
        self.assertEqual(M.layout(4)[-1], 65)
        # 간격 상한 — 두 자는 가운데로 모인다
        xs = M.layout(2, 22)
        self.assertEqual(xs[1] - xs[0], 22)
        self.assertLessEqual(abs(xs[0] + xs[1] - (4 + 65)), 1)

    def test_render_keeps_border_and_clears_old_ink(self):
        d = fake()
        _, pl = M.read(d)
        a = pl[0]
        b = M.render_kr(a, "라그")
        self.assertTrue((b[:2] == a[:2]).all() and (b[14:] == a[14:]).all())
        self.assertTrue((b[:, :2] == a[:, :2]).all() and (b[:, 78:] == a[:, 78:]).all())
        # 원문 획(색인 2)이 남지 않는다 — 한글 획은 색인 1 뿐
        inner = b[2:14, 2:78]
        self.assertFalse((inner == 2).any())
        self.assertTrue((inner == 1).any())

    def test_missing_name_stops(self):
        d = fake()
        tbl = [(jp, None) for jp in M.ORDER]
        with self.assertRaises(AssertionError):
            M.patch(d, tbl)

    def test_patch_keeps_length(self):
        d = fake()
        tbl = [(jp, "가나") for jp in M.ORDER]
        new, n = M.patch(d, tbl)
        self.assertEqual((len(new), n), (len(d), M.N))


if __name__ == "__main__":
    unittest.main()
