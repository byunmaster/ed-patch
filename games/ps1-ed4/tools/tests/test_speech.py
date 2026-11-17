import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_speech as c


class SpeechGate(unittest.TestCase):
    def test_gudae(self):
        self.assertTrue(c.gudae("그대가 왔군."))
        self.assertFalse(c.gudae("그대로 둬."))

    def test_honorific_in_banmal(self):
        self.assertTrue(c.honorific_in_banmal("자네… 모르시나?"))
        self.assertFalse(c.honorific_in_banmal("그렇게 하세요."))

    def test_len_drop(self):
        self.assertTrue(c.len_drop("これはとても長い日本語の文章です。", "응."))
        self.assertFalse(c.len_drop("・・・・・・・・・・・・。", "…"))


if __name__ == "__main__":
    unittest.main()
