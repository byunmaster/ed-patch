"""check_color_rom 양성 대조 — 원판 색 코드 열과 한글 롬의 열이 갈리면 걸리고, 같으면 통과한다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_color_rom as C


class T(unittest.TestCase):
    def test_seq(self):
        self.assertEqual(C.seq("가\x011c나\x0104"), ["1c", "04"])
        self.assertEqual(C.seq("가나"), [])

    def test_diff_detected(self):
        self.assertNotEqual(C.seq("\x011c가"), C.seq("가"))  # 열기 누락 → 열이 다르다


if __name__ == "__main__":
    unittest.main()
