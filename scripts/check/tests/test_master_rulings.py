"""공용 판정기 `master_rulings.check` — 판정 꼴마다 통과·위반이 갈리는지(음성 시험 포함)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import master_rulings as M

CORPUS = [
    ("A#1", "script", "로그가 목수 일 하다가\f"),
    ("A#2", "script", "폐하!"),
    ("B#1", "script", "허나 그것은"),
    ("UI#1", "ui", "그대로 두기"),
]


def run(rule):
    return M.check([dict(id="t", 판정="시험", **rule)], CORPUS)[0]


class T(unittest.TestCase):
    def test_forbid(self):
        self.assertEqual(run({"forbid": ["로그 씨"]}), [])
        self.assertEqual(len(run({"forbid": ["로그가"]})), 1)

    def test_forbid_re_scope_except(self):
        self.assertEqual(len(run({"forbid_re": ["그대(?!로)"]})), 0)
        self.assertEqual(len(run({"forbid_re": ["그대"]})), 1)
        self.assertEqual(run({"forbid_re": ["그대"], "scope": "script"}), [])
        self.assertEqual(run({"forbid": ["허나"], "except_blocks": ["B#1"]}), [])
        self.assertEqual(run({"forbid_regex": ["허나"], "allow_blocks": ["B#1"]}), [])

    def test_allow_only(self):
        self.assertEqual(run({"allow_only": {"has": "허나", "blocks": ["B#1"]}}), [])
        self.assertEqual(len(run({"allow_only": {"has": "허나", "blocks": []}})), 1)

    def test_require(self):
        self.assertEqual(run({"require": [{"block": "A#2", "has": "폐하"}]}), [])
        self.assertEqual(run({"require": [{"block": "A#1", "is": "로그가 목수 일 하다가"}]}), [])
        self.assertEqual(len(run({"require": [{"block": "A#2", "has": "루돌프"}]})), 1)
        self.assertEqual(len(run({"require": [{"block": "없음", "has": "x"}]})), 1)
        self.assertEqual(run({"lacks": [{"block": "A#2", "lacks": "옵"}]}), [])
        self.assertEqual(len(run({"require": [{"block": "B#1", "lacks": "허나"}]})), 1)


if __name__ == "__main__":
    unittest.main()
