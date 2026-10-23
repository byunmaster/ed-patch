import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_pua


class TestPua(unittest.TestCase):
    def _game(self, kr, key="1"):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "script", "ed3"))
        with open(os.path.join(d, "script", "ed3", "X.json"), "w", encoding="utf-8") as f:
            json.dump({"lines": {key: {"jp": "x", "kr": kr}}}, f, ensure_ascii=False)
        return d

    def test_pua_in_text_fails(self):
        total, bad = check_pua.scan(self._game("안녕"), {})
        self.assertEqual((total, len(bad)), (1, 1))

    def test_clean_text_passes(self):
        self.assertEqual(check_pua.scan(self._game("안녕"), {})[1], [])

    def test_allowlist_must_match_exactly(self):
        g = self._game("시템", "k")
        self.assertEqual(check_pua.scan(g, {"script/ed3/X.json": {"k": "시템"}})[1], [])
        self.assertEqual(len(check_pua.scan(g, {"script/ed3/X.json": {"k": "다른"}})[1]), 1)

    def test_own_game_is_clean(self):
        self.assertEqual(check_pua.scan()[1], [])


if __name__ == "__main__":
    unittest.main()
