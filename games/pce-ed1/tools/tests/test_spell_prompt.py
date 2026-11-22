"""주문 안내(「어느 주문을 …?」) 머리 — 개행 둘은 한 줄만 넘어간다(11-22). 안내는 셋째 줄(행 2)에서 시작해야 한다. 원본 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_baked_typeset as B
import font
import glyphdyn
import messages as M
import translate as T


class TestSpellPromptHead(unittest.TestCase):
    def test_start_row_model(self):
        self.assertEqual(B.start_row("\n\n어느"), 1)  # 연속 개행은 한 줄 — 11-22 실화면(루드라 현자)이 둘째 줄이던 꼴
        self.assertEqual(B.start_row("\n \n어느"), 2)  # 둘째 줄에 공백 글자를 찍으면 두 번째 개행이 먹는다
        self.assertEqual(B.start_row("어느"), 0)

    def test_compose_head_is_nl_space_nl(self):
        chars = glyphdyn.forced_chars() | (T.all_glyph_chars() & set(font._order_canon()))
        table, _ = font.build_table(chars)
        m = M.Message(0, 0, None, None, ["どの呪文を書き込むかね？", ("op", 7)])
        by = T.compose(m, {"t": " 어느 주문을 적을까?"}, table, {})
        self.assertTrue(by.startswith(bytes([T.NL]) + font.HALF_SPACE + bytes([T.NL])))
        head, pages = B.decode(by, B.inverse(table))
        self.assertEqual(B.start_row(pages[0][0]), 2)


if __name__ == "__main__":
    unittest.main()
