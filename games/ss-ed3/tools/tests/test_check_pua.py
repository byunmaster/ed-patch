"""`check_pua.py` — 문안 PUA 게이트. 원본 없이 돈다."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_pua as P


class Pua(unittest.TestCase):
    def test_plain_text_clean(self):
        self.assertEqual(P.pua_in("안녕하세요… 「좋아」\n\f"), [])

    def test_range_edges(self):
        self.assertEqual(P.pua_in("ab"), ["", "", ""])
        self.assertEqual(P.pua_in("\udfff豈"), [])

    def test_scan_catches_raw_and_escaped(self):
        with tempfile.TemporaryDirectory() as d:
            raw = os.path.join(d, "raw.json")
            esc = os.path.join(d, "esc.json")
            ok = os.path.join(d, "ok.json")
            with open(raw, "w", encoding="utf-8") as f:
                json.dump({"1": "가나"}, f, ensure_ascii=False)
            with open(esc, "w", encoding="utf-8") as f:
                f.write('{"1": "다\\ue124라", "_k": ["x"]}')
            with open(ok, "w", encoding="utf-8") as f:
                json.dump({"1": "정상"}, f, ensure_ascii=False)
            bad = P.scan([raw, esc, ok])
            self.assertEqual(len(bad), 2)

    def test_scan_checks_keys_and_nested(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "n.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"a": [{"b": "c"}]}, f, ensure_ascii=False)
            self.assertEqual(len(P.scan([p])), 2)


if __name__ == "__main__":
    unittest.main()
