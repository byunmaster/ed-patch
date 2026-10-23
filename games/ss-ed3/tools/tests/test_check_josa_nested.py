"""고유명사 조사 검사가 중첩된 값(음성·무비 자막)까지 보는가 — 10-18."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_josa as J


class Nested(unittest.TestCase):
    def _scan(self, doc):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            json.dump(doc, open(p, "w", encoding="utf-8"), ensure_ascii=False)
            return J.scan([p])

    def test_top_level_string(self):
        self.assertEqual(len(self._scan({"1": "쥬리오은 간다"})), 1)

    def test_inside_list_of_lists(self):
        """movie.json 꼴 `[[시작, 끝, 문안]]` — 최상위 문자열만 보던 때는 샜다."""
        self.assertEqual(len(self._scan({"M01": [[1.0, 2.0, "쥬리오을 부른다"]]})), 1)

    def test_correct_josa_passes(self):
        self.assertEqual(self._scan({"M01": [[1.0, 2.0, "쥬리오는 간다"]]}), [])

    def test_new_axes(self):
        self.assertEqual(len(self._scan({"1": "쥬리오이랑 같이"})), 1)  # 쥬리오는 받침 없음 → 「랑」


if __name__ == "__main__":
    unittest.main()
