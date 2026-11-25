import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_orig_copies as X

KANA = "あいうえおかきくけこ".encode("cp932")  # 히라가나 10자(20B) — 가짜 문안


class OrigCopies(unittest.TestCase):
    def test_changed_kana_run_is_a_segment_but_unchanged_one_is_not(self):
        old = b"\x00" * 8 + KANA + b"\x00" * 8 + KANA
        new = bytearray(old)
        new[8:28] = b"\x41" * 20  # 첫 덩이만 번역으로 바뀜
        segs = X.segments(old, bytes(new))
        self.assertIn(KANA, segs)  # 바뀐 자리의 원판 글
        self.assertEqual(len([s for s in segs if s == KANA]), 1)
        self.assertEqual(X.segments(old, old), set())  # 그대로면 덩이 아님

    def test_graphics_that_decode_as_kanji_are_not_text(self):
        junk = bytes([0x88, 0x9F, 0x89, 0x40] * 6)  # 한자로 디코드되지만 가나가 없다
        self.assertEqual(X.segments(junk + b"\x00" * 8, b"\x00" * 32), set())

    def test_search_finds_a_surviving_copy_and_ignores_fill(self):
        stream = np.frombuffer(b"\x00" * 4096 + b"zz" + KANA + b"\xff" * 4096, dtype=np.uint8)
        hits = X.search(stream, {KANA, b"\x00" * 24})
        self.assertEqual(hits, {KANA: [4098]})

    def test_search_misses_when_no_copy(self):
        stream = np.frombuffer(b"\x00" * 4096, dtype=np.uint8)
        self.assertEqual(X.search(stream, {KANA}), {})


if __name__ == "__main__":
    unittest.main()
