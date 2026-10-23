"""coverage_scan — 짧은 문장 합성 데이터가 걸리고, 기준선 밖 새 런이 실패로 잡히는지."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coverage_scan as C


def sj(s: str) -> bytes:
    return s.encode("cp932")


class Scan(unittest.TestCase):
    def test_짧은_문장도_잡는다(self):
        buf = b"\x00\x00" + sj("が現れた") + b"\x00" + sj("ありがとう")  # 4자·5자 — 길이 12 기준이면 새던 꼴
        found = [s for _o, s in C.runs(buf, C.MIN_CHARS)]
        self.assertIn("が現れた", found)
        self.assertIn("ありがとう", found)

    def test_세_글자는_잡음으로_본다(self):
        self.assertEqual(list(C.runs(sj("ありが"), C.MIN_CHARS)), [])

    def test_알려진_구간_앞에_붙은_일본어도_새_런이다(self):
        # 「알려진 자리와 겹치기만 하면 통과」가 아니다 — 런 단위로 (rel, 오프셋)이 기준선에 있어야 한다
        base = {"runs": [[300, 0x40, "x"]]}
        rows = [(300, 0x40, "ありがとう", True), (300, 0x10, "メタルスチームが現れた", True)]
        self.assertEqual(C.check(rows, base), [rows[1]])

    def test_기준선_안이면_통과(self):
        self.assertEqual(C.check([(1, 2, "ありがとう", False)], {"runs": [[1, 2, "x"]]}), [])


if __name__ == "__main__":
    unittest.main()
