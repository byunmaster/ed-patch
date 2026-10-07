"""check_josa_agreement 가 **진짜로 어긋난 것을 잡는가** — 0 이 나오는 검사기가 눈먼 게 아님을 증명한다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_josa_agreement as c


class Agreement(unittest.TestCase):
    def test_agrees(self):
        self.assertTrue(c.agrees("류난", "은"))  # ㄴ 받침
        self.assertFalse(c.agrees("류난", "는"))
        self.assertTrue(c.agrees("세리오스", "는"))  # 무받침
        self.assertFalse(c.agrees("세리오스", "을"))
        self.assertTrue(c.agrees("슬러그", "와"))  # 그 = 무받침
        self.assertTrue(c.agrees("류난", "과"))
        self.assertTrue(c.agrees("류난", "으로"))
        self.assertTrue(c.agrees("세리오스", "로"))
        self.assertFalse(c.agrees("세리오스", "으로"))

    def test_rieul(self):
        self.assertTrue(c.agrees("횃불", "로"))  # ㄹ 받침 → 로
        self.assertFalse(c.agrees("횃불", "으로"))
        self.assertTrue(c.agrees("횃불", "을"))  # 일반 조사에선 받침 있음

    def test_scan_catches(self):
        n, errs = c.scan_lines([("t:1", "류난는 도망쳤다."), ("t:2", "류난은 도망쳤다.")])
        self.assertEqual(n, 2)
        self.assertEqual(len(errs), 1)
        self.assertIn("류난는", errs[0])


if __name__ == "__main__":
    unittest.main()
