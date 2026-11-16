"""「」 반각 글리프(원판 BIOS 도안, 11-06 — 앞서는 마스터 도안 D판 10-26) — 고정 칸 · 도안 비트 · 8px 전진 · 반각 표 비트. 원본 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import font
import hook
import typeset as T

DOT = {  # 원판 BIOS 도안(11-06) 12×12 의 0~7열 — 낫표는 원판 칸 자리 그대로(8px 전진)
    "「": ["........", "...####.", "...#....", "...#....", "...#....", "...#....", "...#....", "...#....", "...#....", "........", "........", "........"],
    "」": ["........", "........", "........", "......#.", "......#.", "......#.", "......#.", "......#.", "......#.", "......#.", "...####.", "........"],
    "『": ["...#####", "...#...#", "...#.###", "...#.#..", "...#.#..", "...#.#..", "...#.#..", "...#.#..", "...#.#..", "...#.#..", "...###..", "........"],
    "』": [".....###", ".....#.#", ".....#.#", ".....#.#", ".....#.#", ".....#.#", ".....#.#", ".....#.#", "...###.#", "...#...#", "...#####", "........"],  # 11-15 원판 도안 1px 올림(행 1~11 → 0~10, `『` 와 같은 높이)
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

    def test_ligatures_advance_8px_too(self):
        bm = hook.half_tables()
        canon = font._order_canon()
        for ch in font.LIGATURES.values():
            lead, tr = divmod(canon.index(ch), font.PER_LEAD)
            self.assertTrue(bm[12 + lead * 28 + tr // 8] & (0x80 >> (tr % 8)), ch)

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
