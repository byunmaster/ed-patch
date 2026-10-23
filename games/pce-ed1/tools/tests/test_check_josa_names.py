"""정본 이름 뒤 조사 받침 대조 — 합성 문안."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_josa_names as C

NAMES = ["슬러그", "바질", "세리오스"]


class Josa(unittest.TestCase):
    def test_받침_틀린_조사를_잡는다(self):
        self.assertEqual(C.violations("슬러그이 나타났다", NAMES), [("슬러그", "이")])
        self.assertEqual(C.violations("바질를 쓰러뜨렸다", NAMES), [("바질", "를")])
        self.assertEqual(C.violations("세리오스이 말했다", NAMES), [("세리오스", "이")])

    def test_맞는_조사는_통과(self):
        self.assertEqual(C.violations("슬러그가 나타났다. 바질을 쓰러뜨렸다. 세리오스는", NAMES), [])

    def test_병기와_이어지는_글자는_안_친다(self):
        self.assertEqual(C.violations("슬러그이/가", NAMES), [])
        self.assertEqual(C.violations("바질이야기", NAMES), [])
        self.assertEqual(C.violations("새바질이 왔다", NAMES), [])  # 어절 머리가 아니다


if __name__ == "__main__":
    unittest.main()
