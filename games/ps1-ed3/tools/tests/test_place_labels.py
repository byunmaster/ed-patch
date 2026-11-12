"""지명 라벨 한글화 회귀 — 슬롯 배정·가운데 맞춤·빈 칸 워드·칸 초과 거부 (가짜 AM3·시트, 글꼴은 레포 안 shared/fonts).

밟은 함정(10-24): 한글이 일본어보다 짧아 남는 칸을 워드 0 으로 두면 검은 칸이 뜬다 → 투명으로 비운 슬롯의 워드를 쓴다.
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chapter_end
import place_labels as PL

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
FONT = chapter_end.Bdf(os.path.join(ROOT, "shared", "fonts", "Galmuri14.bdf"))


class TestPlaceLabels(unittest.TestCase):
    def setUp(self):
        self.saved = PL.LABELS
        # 라벨 둘: 4칸·3칸, 타일 1·2·3·4 / 3·5·6 (3 은 공유 — 워드는 서로 다른 별칭)
        self.w1 = [0x8001, 0x8002, 0x8003, 0x8004]
        self.w2 = [0x8103, 0x8105, 0x8106]
        PL.LABELS = {
            "T": {
                "labels": [("ラグーナ", self.w1, [1, 2, 3, 4]), ("ニーリ", self.w2, [3, 5, 6])],
                "white": 4,
                "outline": 104,
            }
        }
        self.w = np.zeros(400, "<u2")
        self.w[10:14] = self.w1
        self.w[20:23] = self.w2
        self.w[30:34] = self.w1  # AM3 안의 둘째 출현도 같이 고친다
        self.pix = np.full((64, 112), 7, np.uint8)

    def tearDown(self):
        PL.LABELS = self.saved

    def tile(self, t):
        r, c = divmod(t, 16)
        return self.pix[r * 16 : r * 16 + 16, c * 16 : c * 16 + 16]

    def test_own_cells_first_and_conflict(self):
        out, rep = PL.plan_map("T", self.w.tobytes(), self.pix, FONT)
        w = np.frombuffer(out, "<u2")
        self.assertEqual(rep["labels"], {"ラグーナ": "라그나", "ニーリ": "닐리"})
        # 라그나: 제 칸 워드 그대로(바탕 보존) — 앞 3칸 글자, 4번째 칸은 빈 칸(타일 4 투명)
        self.assertEqual(list(w[10:14]), self.w1)
        self.assertEqual(list(w[30:34]), self.w1)  # 둘째 출현도
        self.assertTrue((self.tile(4) == 255).all())
        # 닐리: 첫 칸 타일 3 은 나(라그나)가 쓰니 충돌 → 오프셋 1(타일 5·6)로 피한다. 빈 칸(타일 3, 남의 글자가 참)은 자유 타일(4)의 워드로
        self.assertEqual((int(w[20]), int(w[21]), int(w[22])), (0x8004, 0x8105, 0x8106))
        self.assertGreater(int((self.tile(3) != 255).sum()), 20)  # 나
        self.assertGreater(int((self.tile(5) != 255).sum()), 20)  # 닐
        self.assertEqual(rep["conflicts"], 0)
        self.assertEqual(rep["blank_moved"], 1)

    def test_missing_sequence_rejected(self):
        self.w[10] = 0
        self.w[30] = 0
        with self.assertRaises(SystemExit):
            PL.plan_map("T", self.w.tobytes(), self.pix, FONT)

    def test_real_config_is_consistent(self):
        """실제 `LABELS` — 칸 수 일치 · 정본에 지명이 있다 · 한글이 칸에 들어간다(원본 없이 도는 정적 검사)."""
        PL.LABELS = self.saved
        for name, cfg in PL.LABELS.items():
            for jp, words, tiles in cfg["labels"]:
                self.assertEqual(len(words), len(tiles), f"{name} {jp}")
                kr = PL.korean(jp)
                known = [t for t in tiles if t is not None]
                self.assertLessEqual(len(kr), len(known), f"{name} {jp} → {kr}")
                self.assertEqual(len(set(words)), len(words), f"{name} {jp}: 워드가 겹친다")

    def test_too_long_rejected(self):
        PL.LABELS["T"]["labels"][1] = ("ニーリ", [0x8103], [3])  # 닐리 2자 > 1칸
        with self.assertRaises(SystemExit):
            PL.plan_map("T", self.w.tobytes(), self.pix, FONT)

    def test_glyph_tile_shape(self):
        t = PL.glyph_tile(FONT, "가", 4, 104)
        self.assertEqual(t.shape, (16, 16))
        self.assertGreater(int((t == 4).sum()), 20)
        self.assertGreater(int((t == 104).sum()), 20)
        self.assertGreater(int((t == 255).sum()), 20)


if __name__ == "__main__":
    unittest.main()
