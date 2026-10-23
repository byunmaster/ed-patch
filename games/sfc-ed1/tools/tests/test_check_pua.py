"""check_pua — PUA 문자가 섞인 번역문을 잡는다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_pua as C


class Scan(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(C.scan({"a": {"kr": "{D9} 말이군."}}), [])

    def test_pua_in_nested(self):
        r = C.scan({"a": {"kr": "약초말이군"}, "b": ["정상"]})
        self.assertEqual(r, [("/a/kr", "U+E003")])

    def test_range_edges(self):
        self.assertTrue(C.scan({"x": ""}) and C.scan({"x": ""}))
        self.assertEqual(C.scan({"x": "\udfff"[:0] + ""[:0] + "가"}), [])

    def test_live_textmap_clean(self):
        self.assertEqual(C.main(), 0)


if __name__ == "__main__":
    unittest.main()
