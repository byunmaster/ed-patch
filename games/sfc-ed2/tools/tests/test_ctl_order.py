"""제어 토큰 순서 대조 — 원문의 구간 맨 앞 제어 코드를 번역이 잃거나 순서가 어긋나면 걸린다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import check_rules


class CtlOrder(unittest.TestCase):
    def test_same_order_ignores_dictionary_tokens(self):
        a = check_rules.ctl_seq("<1e><E0:5><04>\n가나<05>다")
        self.assertEqual(a, check_rules.ctl_seq("<1e>이름<04>\n가나<05>다<E1:11>"))

    def test_dropped_leading_code_differs(self):
        self.assertNotEqual(check_rules.ctl_seq("<04>\n가나"), check_rules.ctl_seq("가나"))

    def test_swapped_order_differs(self):
        self.assertNotEqual(check_rules.ctl_seq("<1e><04><05>"), check_rules.ctl_seq("<1e><05><04>"))


if __name__ == "__main__":
    unittest.main()
