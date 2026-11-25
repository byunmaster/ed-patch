import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_orig_structure as K


def run(jp, kr, site="scn:/BIN/X.BIN#1"):
    return {k: v for k, v in K.check([(site, jp, kr, "dialog")]).items() if v}


class OrigStructure(unittest.TestCase):
    def test_hangul_before_var(self):
        self.assertIn("변수 앞뒤", run("a", "열쇠%s를 얻었다"))

    def test_josa_after_var_ok(self):
        self.assertEqual(run("a", "%s를 얻었다. %d개"), {})

    def test_noun_after_var(self):
        self.assertIn("변수 앞뒤", run("a", "%s입구로"))

    def test_page_count(self):
        self.assertIn("쪽 수", run("a%cb%c", "가나%c"))

    def test_end_newline(self):
        self.assertIn("끝 개행", run("a\n", "가"))


if __name__ == "__main__":
    unittest.main()
