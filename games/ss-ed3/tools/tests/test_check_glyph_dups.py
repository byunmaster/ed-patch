import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_glyph_dups as G


class DupGroups(unittest.TestCase):
    def test_comma_equals_period_is_caught(self):
        self.assertEqual(G.dup_groups({",": b"\x01" * 12, ".": b"\x01" * 12, ":": b"\x02" * 12}), [[",", "."]])

    def test_blank_glyphs_are_ignored(self):
        self.assertEqual(G.dup_groups({"a": b"\x00" * 12, "b": b"\x00" * 12}), [])

    def test_distinct_is_clean(self):
        self.assertEqual(G.dup_groups({",": b"\x03" * 12, ".": b"\x01" * 12}), [])


if __name__ == "__main__":
    unittest.main()
