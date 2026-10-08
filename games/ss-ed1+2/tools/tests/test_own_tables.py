"""`check_own_tables` 회귀 — 표를 잡고, 표가 아닌 것은 안 잡는다. **원본 없이 돈다.**"""

import ast
import os
import sys
import tempfile
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import check_own_tables as C


def _py(src):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(src)
    try:
        return C.py_tables(f.name)
    finally:
        os.unlink(f.name)


class TestOwnTables(unittest.TestCase):
    def test_JP_열쇠_dict_는_표다(self):
        self.assertTrue(_py('T = {"ナイフ": "칼", "毒": "독"}\n'))

    def test_JP_KR_짝_셋은_표다(self):
        self.assertTrue(_py('T = [("毒", "독"), ("黙", "묵"), ("呪", "주")]\n'))

    def test_짝_둘은_표가_아니다(self):
        self.assertFalse(_py('T = [("毒", "독"), ("黙", "묵")]\n'))

    def test_KR_열쇠나_자리_표는_표가_아니다(self):
        self.assertFalse(_py('T = {"독": 1}\nS = [(0x10, 0x20, "毒"), (1, 2, "黙"), (3, 4, "呪")]\n'))

    def test_이_게임_폴더는_자기_표가_0이다(self):
        self.assertEqual(C.scan(), [])


if __name__ == "__main__":
    unittest.main()
