"""이름 뒤 조사 전수(`check_josa.check`) — 합성 문안으로 불일치를 잡고 낱말 오탐을 거르는지 본다. 원본 없이 돈다."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_josa as C


class JosaSweepTest(unittest.TestCase):
    def run_check(self, lines):
        C.texts = lambda disc: iter([(f"t#{i}", s) for i, s in enumerate(lines)])
        C.names = lambda disc: ["크리스", "쥬리오", "사나", "스톤 마을"]
        return C.check("ed3")

    def test_wrong_particle_is_caught(self):
        bad, _, seen = self.run_check(["쥬리오가 왔다.", "크리스이 왔다.", "스톤 마을를 지났다."])
        self.assertEqual(seen, 3)
        self.assertEqual(len(bad), 2)  # 크리스이(무받침+이) · 마을를(받침+를)

    def test_right_particle_passes(self):
        bad, _, _ = self.run_check(["쥬리오는 크리스를 불렀다.", "스톤 마을은 조용하다."])
        self.assertEqual(bad, [])

    def test_word_that_only_looks_like_name_plus_particle_is_skipped(self):
        bad, _, _ = self.run_check(["건넌 사나이. 캡틴이 있었다."])
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
