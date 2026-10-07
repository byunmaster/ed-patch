"""사전 대조(④) — 원문의 정본 이름이 우리 줄에 정본 표기로 있는가. 원본 없이 돈다(합성 줄)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_glossary as G

TBL = {
    "鉄巨人": {"강철 거인"},
    "ロー": {"로우"},
    "セリオス": {"세리오스"},
    "ハイアギール": {"하이아길"},
    "アギール": {"아길"},
}


class Glossary(unittest.TestCase):
    def miss(self, jp, kr):
        return G.missing([("t", jp, kr)], TBL)

    def test_variant_spelling_fails(self):
        # PS1 이 정본과 다르게 쓴 이름(「철거인」)이 따라 들어오면 잡는다
        self.assertTrue(self.miss("鉄巨人が現れた。", "철거인이 나타났다."))
        self.assertFalse(self.miss("鉄巨人が現れた。", "강철 거인이 나타났다."))

    def test_spacing_ignored(self):
        self.assertFalse(self.miss("鉄巨人が現れた。", "강철거인이 나타났다."))

    def test_katakana_word_boundary(self):
        self.assertFalse(self.miss("キャリオンクローラー", "캐리온크롤러"))
        self.assertTrue(self.miss("ローが現れた。", "누가 나타났다."))

    def test_longest_name_first(self):
        self.assertFalse(self.miss("ハイ＝アギールも一緒だ", "하이아길도 함께다"))

    def test_stutter_dots(self):
        self.assertFalse(self.miss("セ・リ・オ・ス・・・", "세·리·오·스…"))


if __name__ == "__main__":
    unittest.main()
