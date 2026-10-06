"""해설 가운데 정렬 — 손 배치(`narration_manual.json`)를 문안에 적용하는 규칙. 원본 없이 돈다."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import center_narration as CN


class ApplyLeads(unittest.TestCase):
    def test_손_값이_줄마다_들어간다(self):
        t = "가나\n다라마\n\n바\f사\n"
        new = CN.apply_leads(t, [2, 1, 0, 3, 0])  # 빈 줄도 한 칸
        self.assertEqual(new, "　가나\n 다라마\n\n　 바\f사\n")

    def test_줄_수가_안_맞으면_운다(self):
        with self.assertRaises(ValueError):
            CN.apply_leads("가\n나\n", [0])


if __name__ == "__main__":
    unittest.main()
