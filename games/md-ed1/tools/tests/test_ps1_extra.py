import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_ps1_extra as c


class Helpers(unittest.TestCase):
    def test_ksents_splits_on_terminals(self):
        self.assertEqual(
            c.ksents("가나다라마 바사. 아자차카타 파하!"), ["가나다라마바사", "아자차카타파하"]
        )

    def test_ours_text_drops_speaker_and_tags(self):
        self.assertEqual(
            c.ours_text("<1e>병사<04><01>가나다.\f라마바.<00>").split(), ["가나다.", "라마바."]
        )

    def test_cov(self):
        self.assertEqual(c.cov("ABCD", "xxABCDxx"), 1.0)
        self.assertEqual(c.cov("ABCD", "zzzz"), 0.0)

    def test_jn_strips_marks(self):
        self.assertEqual(c.jn("{c}兵士{c}{n}なんだ お前たちは？"), "なんだお前たちは")


if __name__ == "__main__":
    unittest.main()
