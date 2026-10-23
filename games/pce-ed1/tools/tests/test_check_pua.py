import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_pua as C


class Pua(unittest.TestCase):
    def test_pua_걸림(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.json").write_text('{"t": "말이군"}', "utf-8")
            (Path(d) / "b.json").write_text('{"t": "\\ue003말이군"}', "utf-8")
            (Path(d) / "glyph_order.json").write_text('[""]', "utf-8")
            hits = C.scan(Path(d))
            self.assertEqual(sorted(f for f, _ in hits), ["a.json", "b.json"])

    def test_깨끗하면_없음(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.json").write_text('{"t": " 말이군"}', "utf-8")
            self.assertEqual(C.scan(Path(d)), [])


if __name__ == "__main__":
    unittest.main()
