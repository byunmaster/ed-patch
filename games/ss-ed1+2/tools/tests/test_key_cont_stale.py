import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_key_cont_stale as K


def w(s):
    return float(len(s))


KC = {"ED1": {"b": 4.0}, "ED2": {}, "chains": {"ED1": [["a", "b"]], "ED2": []}}
KR = {"a": "가나다라%c"}


class Stale(unittest.TestCase):
    def test_fresh(self):
        bad, seen, _ = K.stale(KC, KR, w)
        self.assertEqual((bad, seen), ([], 1))

    def test_positive_control_stale_table(self):
        kc = {**KC, "ED1": {"b": 7.0}}
        bad, _, _ = K.stale(kc, KR, w)
        self.assertEqual([x[1] for x in bad], ["b"])

    def test_text_changed_makes_table_stale(self):
        bad, _, _ = K.stale(KC, {"a": "가나다%c"}, w)
        self.assertEqual(len(bad), 1)

    def test_single_line_adds_own_cursor(self):
        kc = {"ED1": {"a": 2.0, "b": 6.0}, "ED2": {}, "chains": {"ED1": [["a", "b"]], "ED2": []}}
        bad, _, _ = K.stale(kc, KR, w)
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
