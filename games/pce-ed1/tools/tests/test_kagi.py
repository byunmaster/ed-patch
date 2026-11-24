"""「」 반각 글리프(원판 BIOS 도안, 11-06 — 앞서는 마스터 도안 D판 10-26) — 고정 칸 · 도안 비트 · 8px 전진 · 반각 표 비트. 원본 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import font
import hook
import typeset as T

DOT = {  # 마스터 확정 도안(11-25 kagi_master_1125.txt 32×12 를 8열씩) — 글리프는 이 바이트 그대로
    "「": ["#####...", "#.......", "#.......", "#.......", "#.......", "#.......", "#.......", "........", "........", "........", "........", "........"],
    "」": ["........", "........", "........", "........", "....#...", "....#...", "....#...", "....#...", "....#...", "....#...", "#####...", "........"],
    "『": ["######..", "#....#..", "#.####..", "#.#.....", "#.#.....", "#.#.....", "#.#.....", "###.....", "........", "........", "........", "........"],
    "』": ["........", "........", "........", "...###..", "...#.#..", "...#.#..", "...#.#..", "...#.#..", "####.#..", "#....#..", "######..", "........"],
}


class Kagi(unittest.TestCase):
    def test_glyph_bits_match_the_dots(self):
        for ch, rows in DOT.items():
            g = font.unpack(font.pack(font.glyph(ch)))
            got = ["".join("#" if int.from_bytes(g[2 * r : 2 * r + 2], "big") & (0x8000 >> c) else "." for c in range(8)) for r in range(12)]
            self.assertEqual(got, rows, ch)
            self.assertTrue(all(not int.from_bytes(g[2 * r : 2 * r + 2], "big") & 0x00FF for r in range(12)), "8열 밖 잉크")

    def test_fixed_slots_are_outside_the_dynamic_copy_and_the_debug_code(self):
        self.assertGreaterEqual(font.KAGI_SLOT0, font.DYN_RESERVE_FROM)
        self.assertEqual(font.KAGI_SLOT0 + len(font.KAGI), font.DYN_SLOTS)

    def test_table_has_kagi_and_half_bits_are_set(self):
        t, bank = font.build_table("가")
        bm = hook.half_tables()
        for k, ch in enumerate(font.KAGI):
            n = font.DYN0 + font.KAGI_SLOT0 + k
            self.assertEqual(t[ch], font.code_of(n))
            lead, tr = divmod(n, font.PER_LEAD)
            self.assertTrue(bm[12 + lead * 28 + tr // 8] & (0x80 >> (tr % 8)), ch)
            at = font.glyph_at(n)
            self.assertEqual(bank[at : at + font.PACKED_BYTES], font.pack(font.glyph(ch)))

    def test_ligatures_not_baked(self):
        # 11-22: 합자(‼ ⁉)는 11-06 부터 안 쓰여(`font.ligate` 가 원문 그대로) 정본 순서에서 뺐다 — 죽은 글리프를 굽지 않는다
        canon = font._order_canon()
        for ch in font.LIGATURES.values():
            self.assertNotIn(ch, canon, ch)

    def test_exclaim_is_pce2_shape_shifted_left_two(self):
        g = font.glyph("‼")
        got = ["".join("#" if int.from_bytes(g[2 * r : 2 * r + 2], "big") & (0x8000 >> c) else "." for c in range(12)) for r in range(12)]
        self.assertEqual(got[0], "." * 12)
        self.assertEqual(got[1], "##...##.....")
        self.assertEqual(got[8], "." * 12)
        self.assertEqual(got[11], "." * 12)
        self.assertEqual(got[9], got[1])
        self.assertEqual(sum(r.count("#") for r in got), 9 * 4)

    def test_advance_is_8px(self):
        self.assertEqual(T.px("「가」"), 8 + 12 + 8)
        self.assertEqual(T.adv("「"), 8)
        self.assertAlmostEqual(T.cell("」"), 2 / 3)

    def test_encode_uses_the_glyph_code(self):
        t, _ = font.build_table("가")
        self.assertEqual(font.encode("「가」", t), t["「"] + t["가"] + t["」"])


if __name__ == "__main__":
    unittest.main()
