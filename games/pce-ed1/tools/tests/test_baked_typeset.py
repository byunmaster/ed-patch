"""조판 전수 게이트(`check_baked_typeset`)의 검출기 — 축마다 일부러 틀린 쪽이 걸리고 정상 쪽은 안 걸린다(양성·음성 대조). 원본 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_baked_typeset as B
import font
import glyphdyn
import translate as T


class TestDetectors(unittest.TestCase):
    def test_positive_control_all_axes(self):
        self.assertEqual(B.positive_control(), [])

    def test_end_to_end_with_real_glyph_table(self):
        chars = glyphdyn.forced_chars() | (T.all_glyph_chars() & set(font._order_canon()))
        table, _ = font.build_table(chars)
        self.assertEqual(B.end_to_end_control(table), [])

    def test_clean_page_passes(self):
        self.assertEqual(B.page_axes("왕자님, 안녕하세요.\n3.5배 늘었다!?", cap=4), set())

    def test_header_newline_not_a_body_line(self):
        chars = glyphdyn.forced_chars() | (T.all_glyph_chars() & set(font._order_canon()))
        table, _ = font.build_table(chars)
        inv = B.inverse(table)
        by = b"\x1f" + table["왕"] + table["자"] + b"\x04\x01" + table["안"] + table["녕"] + b"\x00"
        head, pages = B.decode(by, inv)
        self.assertEqual((head, pages[0][0]), ("왕자", "안녕"))  # 이름 줄 뒤 개행은 본문 줄이 아니다


if __name__ == "__main__":
    unittest.main()
