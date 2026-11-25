"""마을 HUD 전용 지명 표(마스터 11-09 「최대한 가운데」) — 한 열 민 합성 글자와 새 오프셋 표 계약."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import captions
import hangul
import places


class TownShift(unittest.TestCase):
    def test_glyph_shifted_one_column(self):
        places.ensure_town_glyphs()
        for ch in places._town_syllables():
            base = hangul.glyph_fill(ch)
            moved = hangul.CUSTOM_GLYPHS[places.town_pua(ch)]
            self.assertFalse(any(r[0] for r in base), ch)  # 0열 잉크가 없어야 한 열 밀어도 안 잘린다
            self.assertEqual([r[1:] + [0] for r in base], moved, ch)

    def test_spans_hold_table_and_strings(self):
        (a_lo, a_hi), (b_lo, _b_hi) = places.TOWN_SPANS["ending-a"], places.TOWN_SPANS["ending-b"]
        self.assertGreater(a_hi - a_lo, 2 + 2 * 65)  # 개수 워드 + 65 워드 표가 첫 영역에 든다
        self.assertEqual(places.TOWN_SPANS, captions.TOWN_CARVE)  # 자막 지우기와 같은 영역
        self.assertTrue(a_hi <= b_lo)


if __name__ == "__main__":
    unittest.main()
