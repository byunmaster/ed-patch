"""정본 검사가 **시스템·전투 문구를 실제로 재는가** — 돌연변이 시험(md 실측 10-08 의 짝).

🔴 어댑터가 낸 줄 끝에 엔진 종결·제어 바이트(`\\x0f \\x10 \\x00`)가 붙어 있으면 정본의 줄 전체 대조(`^…$`)에 안 걸려,
   정본 검사가 이 문구들을 하나도 못 잰 채 「어긋남 0」이 나왔다. 시스템 표의 쌍(`names_corpus._system_pairs`)에서
   정본이 재는 줄을 골라 우리 줄을 일부러 틀리게 바꾸면 **어긋남이 늘어야** 한다. 원본 없이 돈다.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "shared"))
import canon as CN
import names_corpus as N

SECTIONS = ("message", "notice", "minigame", "battle")


class CanonMeasuresSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pairs = [
            p for p in N._system_pairs() if p[0].split(":")[1] in SECTIONS and p[2] is not None
        ]
        cls.base = CN.audit(cls.pairs, "ed3")

    def test_most_lines_are_measured(self):
        measured = {h.where for h in self.base.hits}
        self.assertGreaterEqual(len(measured), len(self.pairs) * 0.85, "제어 바이트가 줄 전체 대조를 막고 있다")

    def test_wrong_line_is_caught(self):
        measured = {h.where for h in self.base.hits}
        # 종결 바이트가 붙던 줄(전투·시스템 문구) 위주로 몇 개를 틀리게 한다
        picks = [i for i, p in enumerate(self.pairs) if p[0] in measured and p[0].split(":")[1] in ("battle", "message")]
        self.assertTrue(picks)
        for i in picks[:6]:
            bad = list(self.pairs)
            bad[i] = (self.pairs[i][0], self.pairs[i][1], "틀린 문안", self.pairs[i][3])
            r = CN.audit(bad, "ed3")
            self.assertGreater(len(r.mismatches), len(self.base.mismatches), self.pairs[i][0])


if __name__ == "__main__":
    unittest.main()
