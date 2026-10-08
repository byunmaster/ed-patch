"""「자기 표 0」 검사 — 합성 입력으로 잡는 꼴과 예외를 박는다(원본 불필요)."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_own_tables as C


class TestOwnTables(unittest.TestCase):
    def _run(self, files):
        old = C.ROOT
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "tools"))
            for rel, body in files.items():
                with open(os.path.join(d, rel), "w", encoding="utf-8") as f:
                    f.write(body)
            C.ROOT = d
            try:
                return C.py_hits() + C.json_hits()
            finally:
                C.ROOT = old

    def test_py_dict_and_tuple_are_caught(self):
        self.assertTrue(self._run({"tools/a.py": 'X = {"ジュリオ": "쥬리오"}\n'}))
        self.assertTrue(self._run({"tools/a.py": 'X = [("短剣", "단검")]\n'}))

    def test_json_table_is_caught_but_key_only_list_is_not(self):
        self.assertTrue(self._run({"t.json": json.dumps({"a": {"ジュリオ": "쥬리오"}}, ensure_ascii=False)}))
        self.assertTrue(self._run({"t.json": json.dumps({"ジュリオ": {"kr": "쥬리오"}}, ensure_ascii=False)}))
        self.assertFalse(self._run({"t.json": json.dumps({"place": ["ジュリオ"]}, ensure_ascii=False)}))

    def test_comments_and_korean_only_are_ignored(self):
        self.assertFalse(self._run({"tools/a.py": '# "ジュリオ": "쥬리오"\nX = ["쥬리오"]\n'}))


if __name__ == "__main__":
    unittest.main()
