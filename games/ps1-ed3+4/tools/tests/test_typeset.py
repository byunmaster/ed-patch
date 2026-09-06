"""조판 계약 — 원본 없이 도는 회귀.

상수가 원본을 담나는 `typeset.py --check` 가 게이트에서 본다(원본이 필요하다).
여기서는 **예산을 어떻게 잡나**를 박는다 — 그게 「창 밖으로 나가나」를 정한다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import typeset


class TestTypeset(unittest.TestCase):
    def test_limits_are_per_disc(self):
        """🔴 ED3 30칸 · ED4 35칸 — 한 값으로 묶으면 한쪽이 창 밖으로 나가거나 좁아진다."""
        self.assertNotEqual(typeset.LIMITS["ed3"], typeset.LIMITS["ed4"])
        for lim in typeset.LIMITS.values():
            self.assertGreaterEqual(lim["width"], 24)
            self.assertGreaterEqual(lim["lines"], 1)

    def test_budget_follows_the_original_not_the_cap(self):
        """🔴 예산은 **그 조각의 원문이 쓴 만큼**이다.

        상한(30/35)을 그대로 쓰면 좁은 창에서 글자가 밖으로 나간다 — 창은 자리마다 다르고,
        원문이 그 창에서 몇 칸을 썼는지가 우리가 아는 가장 정확한 증거다.
        """
        self.assertEqual(typeset.budget("ed3", "あいうえお"), (5, 1))

    def test_floor_lifts_the_width_but_never_the_lines(self):
        """🔴 폭은 **창**이 정한다 — `floor`(그 멤버의 원문 최대)를 바닥으로 깐다.

        조각별 예산은 허수였다: 같은 화자가 연달아 말하는 창이 4·19·15·21칸으로 널뛴다.
        인게임 실측(2026-09-07)으로 그 창이 약 24칸인데 멤버 최대가 23칸이었다.
        ⚠ 줄 수는 안 올린다 — **조각 하나 = 줄 하나**다(0x01 은 쉼표다).
        """
        self.assertEqual(typeset.budget("ed3", "あいうえお", 23), (23, 1))
        self.assertEqual(typeset.budget("ed3", "あいうえお", 0), (5, 1))

    def test_budget_is_capped(self):
        long = "あ" * 99
        w, n = typeset.budget("ed3", long)
        self.assertEqual(w, typeset.LIMITS["ed3"]["width"])

    def test_wrap_respects_the_budget(self):
        jp = "あいうえおかきくけこ"  # 10칸 1줄
        out = typeset.wrap("아주 긴 우리 문안이 여기에 들어간다", "ed3", jp=jp)
        for line in out.split("\n"):
            self.assertLessEqual(len(line), 10, out)

    def test_violations_reports_overflow(self):
        self.assertEqual(typeset.violations("짧다", "ed3", jp="あいうえお"), [])
        bad = typeset.violations("아주아주아주 긴 줄", "ed3", jp="あい")
        self.assertTrue(bad)

    def test_wrap_is_deterministic(self):
        """빌드는 결정적이어야 한다 — 같은 입력이면 같은 줄바꿈."""
        jp = "あいうえおかきくけこさしすせそ"
        a = typeset.wrap("우리 문안을 여러 번 조판해도 같은 결과가 나와야 한다", "ed3", jp=jp)
        b = typeset.wrap("우리 문안을 여러 번 조판해도 같은 결과가 나와야 한다", "ed3", jp=jp)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
