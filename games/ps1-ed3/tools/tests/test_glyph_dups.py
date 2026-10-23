import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_glyph_dups as G
import font


class T(unittest.TestCase):
    def test_same_bitmap_pair_found(self):
        orig = font.read_glyph
        glyphs = {0: np.eye(12, dtype=np.uint8), 1: np.eye(12, dtype=np.uint8), 2: np.zeros((12, 12), np.uint8)}
        font.read_glyph = lambda exe, c, disc="ed3": glyphs[c]
        gc = font.glyph_count
        font.glyph_count = lambda exe, disc="ed3": 3
        try:
            self.assertEqual(G.dup_groups(b""), [[0, 1]])
        finally:
            font.read_glyph, font.glyph_count = orig, gc
