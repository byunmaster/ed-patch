"""자기 표 0 검사기가 사전꼴을 실제로 잡는가 — 검사기 자신의 커버리지."""

import ast
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_own_tables as C


class OwnTables(unittest.TestCase):
    def test_json_dict_flagged(self):
        self.assertTrue(C.json_tables({"呪文": "주문"}))
        self.assertTrue(C.json_tables({"a": {"呪文": {"ours": "주문"}}}))

    def test_json_sentence_corpus_ok(self):
        self.assertFalse(C.json_tables({"02e0b8": {"jp": "ab12", "ours": "안녕"}}))
        self.assertFalse(C.json_tables({"呪文": ["=ui:呪文", 1]}))  # 원문뿐인 칸 배치

    def test_py_dict_and_tuples_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.py"
            p.write_text('T = {"呪文": "주문"}\nL = [("呪文", "주문"), ("武器", "무기"), ("戦う", "공격")]\n', encoding="utf-8")
            found, _ = C.py_tables(p, "x.py")
            self.assertEqual(len(found), 2)

    def test_pending_exempt_and_counted(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "dict_names.py"
            p.write_text('PENDING = {"ui:削除": "삭제"}\n', encoding="utf-8")
            found, n = C.py_tables(p, "dict_names.py")
            self.assertEqual((found, n), ([], 1))


if __name__ == "__main__":
    unittest.main()
