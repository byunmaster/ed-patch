import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import captions


class DigitWiden(unittest.TestCase):
    def test_digit_runs_get_wider_pitch_only(self):
        out = captions.widen_digits("<fe0e>왕자는 6살. 15살<fd80>")
        w = f"<fe{14 + 2 * captions.DIGIT_EXTRA:02x}>"
        self.assertEqual(out, f"<fe0e>왕자는 {w}6<fe0e>살. {w}15<fe0e>살<fd80>")

    def test_tag_digits_untouched(self):
        self.assertEqual(captions.widen_digits("<fd85><fe0e>안녕"), "<fd85><fe0e>안녕")


if __name__ == "__main__":
    unittest.main()
