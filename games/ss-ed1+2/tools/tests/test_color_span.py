import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_color_span as K

ORIG = b"%c\x83\x41\x83\x42%c\x82\xa0\x82\xa0%c"
ARGS = [2, 1, 8]


class ColorSpan(unittest.TestCase):
    def test_same(self):
        self.assertEqual(K.compare(ORIG, b"%c\x88\xaa\x88\xab%c\x88\xac%c", ARGS), {})

    def test_missing_pair(self):
        self.assertIn("누락", K.compare(ORIG, b"\x88\xaa\x88\xab\x88\xac%c", ARGS))

    def test_empty_span(self):
        self.assertIn("빈 범위", K.compare(ORIG, b"%c%c\x88\xac%c", ARGS))

    def test_split_span(self):
        self.assertIn("범위 쪼개짐", K.compare(ORIG, b"%c\x88\xaa\n\x88\xab%c\x88\xac%c", ARGS))

    def test_bleed(self):
        # 마지막 `%c` 가 켜기로 끝나는 블록 — 빌드가 그 뒤에 글을 붙이면 색이 번진다
        o = b"\x83\x41%c\x83\x42%c"
        self.assertIn("안 닫힘", K.compare(o, b"\x88\xaa%c\x88\xab%c\x88\xac", [1, 2]))
        self.assertEqual(K.compare(o, b"\x88\xaa%c\x88\xab%c", [1, 2]), {})


if __name__ == "__main__":
    unittest.main()
