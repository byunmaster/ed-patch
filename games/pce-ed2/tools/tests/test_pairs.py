"""원판·한글 짝 표 디코더 — 쪽 넘김·이름 자리·조사 토큰·빈 줄 판정(원본 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pairs


class _Glyphs:  # 한글 글리프 읽기 대역 — 리드 F0 의 트레일 값 그대로 글자 하나로
    def glyph(self, lead, trail, local):
        return "가"


class PairsTest(unittest.TestCase):
    def test_page_break_and_newline(self):
        self.assertEqual(pairs.decode(b"\x0d\x13", None, None), "↵⏎")

    def test_name_slots_are_name(self):
        self.assertEqual(pairs.decode(b"\x1a\x1b\x07", None, None), "{name}{name}{name}")
        self.assertEqual(pairs.decode(b"\x13\x89", None, None, True), "{name}")  # 본 프로그램 문자열의 `13 nn`

    def test_controls_are_expanded(self):
        self.assertEqual(pairs.decode(b"\x1c\x59", None, None), "{1C 59}")

    def test_ko_line_reads_ascii_and_josa(self):
        s = pairs.decode(b"\xf0\x24A\x60\xf9\x24", _Glyphs(), [])
        self.assertEqual(s, "가A {josa}")

    def test_jp_line_stays_jp(self):
        # 한글 리드가 없는 줄은 원판 글자로 — 단일 바이트 0x21 은 전각 ！
        self.assertEqual(pairs.decode(b"\x21", _Glyphs(), []), "！")

    def test_ko_lead_hidden_behind_ctrl_arg_is_found(self):
        # `13 89 F9 24` — 89 는 인자라 SJIS 리드로 읽어 뒤의 F9 를 삼키면 안 된다
        self.assertTrue(pairs._is_ko(b"\x13\x89\xf9\x24", True))

    def test_blank(self):
        self.assertTrue(pairs.blank("{0C}↵⏎　"))
        self.assertTrue(pairs.blank("{name}"))
        self.assertFalse(pairs.blank("{name}{josa}"))
        self.assertFalse(pairs.blank("가"))


if __name__ == "__main__":
    unittest.main()
