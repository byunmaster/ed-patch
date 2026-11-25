"""전각 숫자 `０`~`９`(KANJI12)는 원판 그대로다 — 번역 글꼴(갈무리)로 갈아 끼우지 않는다(규칙 1-8 · 마스터 10-27)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_font as BF
import font as F


class DigitsOriginal(unittest.TestCase):
    def test_fullwidth_digit_slots_untouched(self):
        base, _ = F.load(1)
        out, _missing = BF.build(1)
        for idx in BF.digit_slots():
            self.assertEqual(
                out[idx * F.STRIDE : (idx + 1) * F.STRIDE],
                base[idx * F.STRIDE : (idx + 1) * F.STRIDE],
            )


if __name__ == "__main__":
    unittest.main()
