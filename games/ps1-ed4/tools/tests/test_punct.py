import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_punct as c


class PunctGate(unittest.TestCase):
    def test_forms(self):
        self.assertTrue(c.forms("좋아～."))
        self.assertTrue(c.forms("그래… …"))
        self.assertTrue(c.forms("왜?…"))
        self.assertFalse(c.forms("뭐야?!"))
        self.assertFalse(c.forms("자～, 가자."))

    def test_ellipsis(self):
        self.assertEqual(c.expected_runs("・・・・・・"), [2])
        self.assertTrue(c.ellipsis_mismatch("・・・・・・あ", "…응"))
        self.assertFalse(c.ellipsis_mismatch("あ・・・", "응…"))

    def test_lost(self):
        self.assertEqual(c.lost("大丈夫か！", "괜찮아"), ["!"])
        self.assertTrue(c.period_lost("行くぞ。", "간다"))
        self.assertFalse(c.period_lost("行くぞ。", "간다!"))
        self.assertTrue(c.tilde_extra("そう", "그래～"))


if __name__ == "__main__":
    unittest.main()
