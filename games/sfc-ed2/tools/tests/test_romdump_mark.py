"""romdump 표시 — 일본어 글자 없는 행 표식(롬 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import romdump


class NoJpMark(unittest.TestCase):
    def test_flag_added_only_for_text_without_kana(self):
        self.assertEqual(romdump.nojp("OFF  ", ""), "일본어 글자 없음")
        self.assertEqual(romdump.nojp("OFF  ", "칸"), "칸·일본어 글자 없음")
        self.assertEqual(romdump.nojp("オフ", "칸"), "칸")
        self.assertEqual(romdump.nojp("　↵", "칸"), "칸")  # 빈 칸은 표식 없음

    def test_walk_end_bounds_fixed_cell(self):
        dec = romdump.Dec(b"\x4f\x4e\x20\x20\x4f\x46\x46\x20", False)
        self.assertEqual(dec.walk(0, end=4), "ON  ")
        self.assertEqual(dec.walk(4, end=7), "OFF")


if __name__ == "__main__":
    unittest.main()
