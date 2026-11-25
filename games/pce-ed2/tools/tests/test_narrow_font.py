"""반각 글꼴 표 교체(`narrow_font`) — 도안 모양·슬롯 대조."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import layout
import narrow_font as nf


class Table(unittest.TestCase):
    def test_glyph_shapes(self):
        for ch, rows in nf.GLYPHS.items():
            self.assertEqual(len(rows), 12, ch)
            self.assertTrue(all(len(r) == 8 and set(r) <= {".", "#"} for r in rows), ch)
            self.assertTrue(any("#" in r for r in rows), ch)
            self.assertEqual(len(nf.glyph_bytes(rows)), 12)

    def test_slots_exist_and_codes_unique(self):
        prog = layout.Prog()
        codes = list(prog.o(nf.BANK, nf.CODES_OFF, nf.N_CODES))
        for ch in nf.REPLACE:
            self.assertIn(ord(ch), codes, ch)
        for kana in nf.SLOT_KANA:
            self.assertIn(kana, codes, hex(kana))
        for code in nf.NEW.values():
            self.assertNotIn(code, codes, hex(code))  # 새 코드가 원래 목록에 없어야 슬롯 교체가 순서를 안 바꾼다
        self.assertEqual(len(set(nf.NEW.values())), len(nf.NEW))
        self.assertEqual(len(nf.NEW), len(nf.SLOT_KANA))

    def test_install_writes(self):
        prog = layout.Prog()
        codes = list(prog.o(nf.BANK, nf.CODES_OFF, nf.N_CODES))
        upper = sum(chr(c) in nf.UPPER for c in codes)
        self.assertEqual(nf.install(prog), len(nf.REPLACE) + upper + 2 * len(nf.NEW))

    def test_baseline_matches_hangul(self):
        """한글(갈무리) 잉크 행 0~10 — 전높이 도안(숫자·`!`·`?`·대문자)은 같은 행에 놓인다."""
        import font

        def band(rows):
            ys = [y for y, v in enumerate(rows) if v]
            return ys[0], ys[-1]

        hangul = band([font.glyph("가")[2 * i] << 8 | font.glyph("가")[2 * i + 1] for i in range(12)])
        for ch in nf.RAISE:
            self.assertEqual(band([int(r.replace(".", "0").replace("#", "1"), 2) for r in nf.GLYPHS[ch]]), (0, 10), ch)
        self.assertEqual(hangul, (0, 10))
        prog = layout.Prog()
        codes = list(prog.o(nf.BANK, nf.CODES_OFF, nf.N_CODES))
        for i, c in enumerate(codes):  # 원판 대문자는 1~11 → 설치가 0~10 으로
            if chr(c) in nf.UPPER:
                self.assertEqual(band(prog.o(nf.BANK, nf.GLYPH_OFF + 12 * i, 12)), (1, 11), chr(c))


if __name__ == "__main__":
    unittest.main()
