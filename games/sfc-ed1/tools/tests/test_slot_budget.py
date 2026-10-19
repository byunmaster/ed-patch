"""슬롯 한도 상수 — 쪽 칸 + 고정 칸 예산이 슬롯 수를 넘으면 빌드가 선다(원문 인용 없음)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text  # noqa: E402,F401,I001
import hook  # noqa: E402


class SlotBudget(unittest.TestCase):
    def test_enough(self):
        self.assertEqual(hook.slot_budget_problems(150), [])
        self.assertEqual(hook.slot_budget_problems(hook.PAGE_CELLS + hook.PIN_BUDGET), [])

    def test_short(self):
        self.assertTrue(hook.slot_budget_problems(hook.PAGE_CELLS + hook.PIN_BUDGET - 1))
        self.assertTrue(hook.slot_budget_problems(80))


if __name__ == "__main__":
    unittest.main()
