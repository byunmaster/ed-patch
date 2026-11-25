"""주문 안내(「어느 주문을 …?」) 머리 — 개행 둘은 한 줄만 넘어간다(11-22). 안내는 마지막(넷째) 줄(행 3)에서 시작해야 한다(11-23 마스터 — 주문 7개 목록이 셋째 줄까지 덮는다). 원본 없이 돈다."""

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
        self.assertEqual(B.start_row("\n \n \n어느"), 3)
        self.assertEqual(B.start_row("어느"), 0)

    def test_compose_head_is_nl_space_nl_space_nl(self):
        chars = glyphdyn.forced_chars() | (T.all_glyph_chars() & set(font._order_canon()))
        table, _ = font.build_table(chars)
        m = M.Message(0, 0, None, None, ["どの呪文を書き込むかね？", ("op", 7)])
        by = T.compose(m, {"t": " 어느 주문을 적을까?"}, table, {})
        self.assertTrue(by.startswith(bytes([T.NL]) + font.HALF_SPACE + bytes([T.NL]) + font.HALF_SPACE + bytes([T.NL])))
        head, pages = B.decode(by, B.inverse(table))
        self.assertEqual(B.start_row(pages[0][0]), 3)

    def test_lead_px_never_splits_prompt(self):
        """앞 메시지가 쓴 폭(이음 갈래)이 얼마든 안내는 머리 뒤 한 줄 — 11-22 밤 회귀(앞 폭 100·112px 에서 「어느 / 주문을 …」)."""
        chars = glyphdyn.forced_chars() | (T.all_glyph_chars() & set(font._order_canon()))
        table, _ = font.build_table(chars)
        m = M.Message(0, 0, None, None, ["どの呪文を書き込むかね？", ("op", 7)])
        base = T.compose(m, {"t": " 어느 주문을 적을까?"}, table, {})
        for lead in (0, 100, 112, 136, 140):
            by = T.compose(m, {"t": " 어느 주문을 적을까?"}, table, {}, lead_px=lead)
            self.assertEqual(by, base, lead)
        _head, pages = B.decode(base, B.inverse(table))
        self.assertNotIn("\n", pages[0][0].lstrip("\n "))


if __name__ == "__main__":
    unittest.main()
