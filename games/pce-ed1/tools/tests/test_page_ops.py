"""쪽 옵코드 중복 대조(`check_page_ops`) — 계산 규칙 단위 시험."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_page_ops as C


class PageOps(unittest.TestCase):
    def test_dup_pages(self):
        self.assertEqual(C.dup_pages([-1, 5, 5]), 1)
        self.assertEqual(C.dup_pages([-1, 5, -1, 5]), 0)
        self.assertEqual(C.dup_pages([5, 3, 5]), 2)

    def test_ctrl_runs_skips_glyph_second_byte(self):
        # 글리프 코드 `F0 05` 의 둘째 바이트 05 는 제어가 아니다
        self.assertEqual(C.ctrl_runs(bytes([0xF0, 0x05, 0x05, 0x06])), [-1, 5, 6])

    def test_page_before_end(self):
        self.assertEqual(C.page_before_end([-1, 5, 6]), 1)
        self.assertEqual(C.page_before_end([-1, 6]), 0)


class HeaderNl(unittest.TestCase):
    def _msg(self, start, end, terminated=False):
        import messages as M

        m = M.Message.__new__(M.Message)
        m.start, m.end, m.terminated = start, end, terminated
        return m

    def test_header_detect(self):
        import translate as T

        self.assertTrue(T.is_header_start(bytes([0x09, 0x03, 0x01, 0xF0, 0x10])))
        self.assertTrue(T.is_header_start(bytes([0x1F, 0xF0, 0x10, 0x04, 0x01, 0xF0, 0x11])))
        self.assertFalse(T.is_header_start(bytes([0x09, 0x03, 0xF0, 0x10])))  # 줄바꿈 없는 인라인 이름
        self.assertFalse(T.is_header_start(bytes([0x1F, 0xF0, 0x10, 0x04, 0xF0, 0x11])))

    def test_pass_adds_newline_only_for_open_text(self):
        import translate as T

        glyph = bytes([0xF0, 0x10])
        head = bytes([0x09, 0x00, 0x01]) + glyph
        a, b, c = self._msg(0, 10), self._msg(10, 20), self._msg(20, 30)
        out = T.header_nl_pass([(a, glyph + b"!"), (b, head + bytes([0x05])), (c, head)])
        self.assertEqual(out[0][1][-1], 0x01)  # 열린 글 → 개행
        self.assertEqual(out[1][1][-1], 0x05)  # 쪽 옵코드로 끝나면 그대로
        out = T.header_nl_pass([(a, glyph + bytes([0x01])), (b, head)])
        self.assertEqual(out[0][1], glyph + bytes([0x01]))  # 이미 개행


if __name__ == "__main__":
    unittest.main()
