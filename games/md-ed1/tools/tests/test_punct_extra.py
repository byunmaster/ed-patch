"""check_text.extra_punct 양성·음성 대조 (마스터 11-13 문장부호 전수)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import check_text as ct


class Punct(unittest.TestCase):
    def test_positive(self):
        for bad in ("뭐야⁉", "뭐야‼", "뭐야~", "그래・・・", "그래･･･", "그래… … 그래", "뭐?.", "뭐!."):
            self.assertTrue(ct.extra_punct(bad), bad)


    def test_negative(self):
        for ok in ("뭐야!?", "그래…", "그래…\x0c…", "그래…<03>… 그래", "꼬꼬댁～～!?", "………………", "아니… 그게"):
            self.assertFalse(ct.extra_punct(ok), ok)


if __name__ == "__main__":
    unittest.main()
