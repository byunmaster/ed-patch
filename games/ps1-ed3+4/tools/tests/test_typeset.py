"""조판 계약 — 원본 없이 도는 회귀.

상수가 원본을 담나는 `typeset.py --check` 가 게이트에서 본다(원본이 필요하다).
여기서는 **예산을 어떻게 잡나**를 박는다 — 그게 「창 밖으로 나가나」를 정한다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import script
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
        w, _n = typeset.budget("ed3", long)
        self.assertEqual(w, typeset.LIMITS["ed3"]["width"])

    def test_wrap_respects_the_budget(self):
        jp = "あいうえおかきくけこ"  # 10칸 1줄
        # 글자 수가 아니라 **폭**이다 — 공백이 2/3칸이라 열한 글자가 열 칸에 든다
        out = typeset.wrap("우리 문안 여기 든다", "ed3", jp=jp)
        self.assertLessEqual(typeset.width_cells(out, "ed3"), 10, out)
        with self.assertRaises(typeset.TypesetError):  # 안 들면 자르지 않고 운다
            typeset.wrap("아주 긴 우리 문안이 여기에 들어간다", "ed3", jp=jp)

    def test_space_is_six_px_only_where_the_engine_is_patched(self):
        """공백 6px(반 칸)는 엔진 패치가 있는 ED3 만 — ED4 는 아직 12px 그대로다."""
        self.assertAlmostEqual(typeset.cell_width(" ", "ed3"), 6 / 12)
        self.assertEqual(typeset.cell_width("가", "ed3"), 1)
        self.assertEqual(typeset.cell_width(" ", "ed4"), 1)
        self.assertAlmostEqual(typeset.width_cells("가 나", "ed3"), 2 + 6 / 12)
        for p in ",.?!()":  # 부호도 반 칸(마스터 10-07) — 엔진 훅의 부호 코드와 같은 집합이다
            self.assertAlmostEqual(typeset.cell_width(p, "ed3"), 6 / 12, msg=p)
        for p in "…～「」":  # 전각 유지(마스터 10-07)
            self.assertEqual(typeset.cell_width(p, "ed3"), 1, p)

    def test_grid_columns_cap_the_glyph_count(self):
        """폭이 예산 안이어도 격자 열(32)을 넘는 글리프 수는 화면에서 잘린다."""
        many = "가 " * 20  # 40글리프, 폭 33.3칸
        bad = typeset.violations(many.strip(), "ed3")
        self.assertTrue(any("격자" in b for b in bad), bad)

    def test_violations_reports_overflow(self):
        self.assertEqual(typeset.violations("짧다", "ed3", jp="あいうえお"), [])
        bad = typeset.violations("아주아주아주 긴 줄", "ed3", jp="あい")
        self.assertTrue(bad)

    def test_wrap_never_drops_text(self):
        """🔴 실측 사고(09-27) — 넘친 줄을 `out[:lines]` 로 버렸다. 빌드가 `floor` 를 안 줘서
        ED3 37줄 · ED4 59줄의 꼬리가 화면에서 사라졌다(`을(를) 건네받았다.` → `을(를)`)."""
        with self.assertRaises(typeset.TypesetError):
            typeset.wrap("을(를) 건네받았다.", "ed3", jp="を渡された。")
        self.assertEqual(
            typeset.wrap("을(를) 건네받았다.", "ed3", jp="を渡された。", floor=23),
            "을(를) 건네받았다.",
        )

    def test_wrap_keeps_edge_spaces_for_runtime_inserts(self):
        """조각은 엔진이 끼우는 이름·숫자와 한 줄로 붙는다 — `쥬리오는 ` 의 공백이 살아야 한다."""
        self.assertEqual(typeset.wrap("쥬리오는 ", "ed3", jp="ジュリオは", floor=23), "쥬리오는 ")
        self.assertEqual(typeset.wrap(" 맞지?", "ed3", jp="だね？", floor=23), " 맞지?")
        self.assertEqual(typeset.wrap("   ", "ed3", jp="あ", floor=23), "")

    def test_head_block_names_get_the_name_floor(self):
        """🔴 머리 블록 이름은 원문 글자 수가 아니라 `NAME_FLOOR` 칸 — 「크리스 엄마」(5.5칸)가 두 줄로 접혀 `크리스` 만 남던 사고."""
        segs = [(0, "クリスの母"), (1, "ログ"), (2, "ジュリオ。")]
        floors = script.member_floors(segs)
        self.assertEqual(floors[0], script.NAME_FLOOR)
        self.assertEqual(floors[1], script.NAME_FLOOR)
        self.assertEqual(typeset.wrap("크리스 엄마", "ed3", jp="クリスの母", floor=floors[0]), "크리스 엄마")
        with self.assertRaises(typeset.TypesetError):  # 바닥이 없으면 예전 사고가 그대로 난다
            typeset.wrap("크리스 엄마", "ed3", jp="クリスの母")

    def test_wrap_is_deterministic(self):
        """빌드는 결정적이어야 한다 — 같은 입력이면 같은 줄바꿈."""
        jp = "あいうえおかきくけこさしすせそ"
        a = typeset.wrap("우리 문안을 여러 번 조판해도 같은 결과", "ed3", jp=jp, floor=24)
        b = typeset.wrap("우리 문안을 여러 번 조판해도 같은 결과", "ed3", jp=jp, floor=24)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
