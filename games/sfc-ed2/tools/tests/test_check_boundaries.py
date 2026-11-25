"""경계 점검의 양성 대조 — 일부러 만든 결함 세 부류를 실제로 잡는가(검사기 자신의 커버리지)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_boundaries as cb


def row(addr, jp, kr, mark=""):
    return f"{addr}\t{jp}\t{kr}\t{mark}"


class T(unittest.TestCase):
    def test_clean(self):
        n, bad = cb.scan(
            [row("C00000", "あ⏎い↵", "가.⏎나.↵"), row("C00001", "あ", "{0b}{은/는} 간다")]
        )
        self.assertEqual(bad, [])
        self.assertEqual(n[0], 2)

    def test_insert_without_space(self):
        _, bad = cb.scan([row("C00002", "あ", "보물상자 안에는{0e}이 있다")])
        self.assertTrue(bad and bad[0].startswith("①"))

    def test_page_break_lost(self):
        _, bad = cb.scan([row("C00003", "あ⏎い", "가. 나.")])
        self.assertTrue(bad and bad[0].startswith("②"))

    def test_tail_newline_lost(self):
        _, bad = cb.scan([row("C00004", "あ↵", "가.")])
        self.assertTrue(bad and bad[0].startswith("③"))

    def test_skip_rows(self):
        _, bad = cb.scan(
            [row("C00005", "あ⏎い", "ア가", ""), row("C00006", "あ⏎い", "가", "그래픽·표 데이터")]
        )
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
