"""명사×조사 받침 판정(`check_josa_nouns.wrong`) — 원본·정본 파일 없이 판정 함수만 본다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_josa_nouns as c


class Wrong(unittest.TestCase):
    def test_vowel_noun(self):
        self.assertTrue(c.wrong("슬러그", "이"))  # 슬러그이 → 슬러그가
        self.assertFalse(c.wrong("슬러그", "가"))
        self.assertTrue(c.wrong("슬러그", "을"))
        self.assertTrue(c.wrong("슬러그", "으로"))

    def test_consonant_noun(self):
        self.assertTrue(c.wrong("검", "가"))
        self.assertFalse(c.wrong("검", "이"))
        self.assertTrue(c.wrong("검", "를"))
        self.assertFalse(c.wrong("검", "으로"))

    def test_rieul(self):
        self.assertFalse(c.wrong("칼", "로"))  # ㄹ 받침은 「로」
        self.assertTrue(c.wrong("칼", "으로"))


if __name__ == "__main__":
    unittest.main()
