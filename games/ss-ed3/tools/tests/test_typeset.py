"""조판 계약 회귀 — **원본 없이 돈다**(계약 상수 + 순수 계산).

🔴 지키는 것: 나레이션을 대화창 자로 재지 않는 것. 대화창(17×3)으로 재면 나레이션은
   「넘친다」가 잔뜩 나오는데 **전부 오탐**이다 — 전체화면 연출이라 계약이 다르다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import typeset as T


class TestContract(unittest.TestCase):
    def test_계약_상수(self):
        """문서의 수치와 코드가 갈리면 안 된다 — `typeset.py` 머리말이 정본이다."""
        self.assertEqual((T.WIN_COLS, T.WIN_ROWS, T.SCREEN_COLS), (17, 3, 24))
        self.assertLess(T.WIN_COLS, T.SCREEN_COLS)  # 창은 화면보다 좁다

    def test_폭_계산(self):
        self.assertEqual(T.cols("ここは村"), 4)
        self.assertEqual(T.cols("ab"), 1.0)  # 반각 둘 = 전각 하나
        self.assertEqual(T.cols("あ<0D>い"), 2)  # 제어 표기는 안 센다


class TestNarration(unittest.TestCase):
    def test_전각_공백으로_들여쓰면_나레이션(self):
        t = "　　　遠い旅人のあとを追って\n　　　海をわたる船の上で"
        self.assertTrue(T.is_narration(t))

    def test_보통_대사는_아니다(self):
        self.assertFalse(T.is_narration("これは試験用の文です。\nつづきの行"))

    def test_나레이션은_넘침을_안_잰다(self):
        """🔴 8~11줄짜리 전체화면 연출을 창 계약으로 재면 전부 오탐이 된다."""
        t = "\n".join("　　　" + "あ" * 18 for _ in range(9))
        self.assertTrue(T.is_narration(t))
        self.assertEqual(T.overflows(t), [])


class TestOverflow(unittest.TestCase):
    def test_딱_맞는_페이지는_안_잡는다(self):
        t = "\n".join(["あ" * 17] * 3)
        self.assertEqual(T.overflows(t), [])

    def test_한_줄_넘치면_잡는다(self):
        t = "\n".join(["あ" * 17] * 4)
        self.assertEqual(T.overflows(t), [(0, 4)])

    def test_엔진이_접는_것을_센다(self):
        """⚠ `0D` 가 전부가 아니다 — 저자가 안 접은 줄은 엔진이 접는다(실측 566줄)."""
        self.assertEqual(T.wrapped_rows("あ" * 17), 1)
        self.assertEqual(T.wrapped_rows("あ" * 18), 2)
        self.assertEqual(T.wrapped_rows("あ" * 34), 2)
        self.assertEqual(T.wrapped_rows("あ" * 35), 3)
        # 34자 한 줄 + 17자 한 줄 = 3줄 → 딱 맞는다
        self.assertEqual(T.overflows("あ" * 34 + "\n" + "あ" * 17), [])
        self.assertEqual(T.overflows("あ" * 35 + "\n" + "あ" * 17), [(0, 4)])

    def test_페이지는_따로_센다(self):
        t = "\n".join(["あ" * 17] * 3) + "\f" + "\n".join(["あ" * 17] * 3)
        self.assertEqual(T.overflows(t), [])

    def test_빈_줄은_안_센다(self):
        self.assertEqual(T.overflows("あい\n\n\nうえ"), [])


class TestPadding(unittest.TestCase):
    """길이 보존 재삽입 — 모자란 바이트를 줄 끝 전각 공백으로 채운다."""

    def test_바이트_계산(self):
        self.assertEqual(T.body_bytes("あい"), 4)
        self.assertEqual(T.body_bytes("あい\nうえ"), 9)  # 개행 1B
        self.assertEqual(T.body_bytes("あ\f<0E>"), 4)  # 페이지 1B · <XX> 1B

    def test_예산에_정확히_맞춘다(self):
        out = T.pad_to_budget("あいうえお\nかきくけこ", 41)
        self.assertEqual(T.body_bytes(out), 41)
        self.assertTrue(out.startswith("あいうえお" + T.PAD))

    def test_마지막_줄은_안_채운다(self):
        """🔴 `▼` 가 텍스트 맨 끝에 붙는다 — 마지막 줄을 채우면 혼자 한 줄 밀린다(실측)."""
        out = T.pad_to_budget("あいうえお\nかきくけこ", 41)
        self.assertEqual(out.split(T.NL)[-1], "かきくけこ")

    def test_마지막_페이지의_마지막_줄만_뺀다(self):
        out = T.pad_to_budget("あい\nうえ\fおか\nきく", 4 + 1 + 4 + 1 + 4 + 1 + 4 + 2 * 9)
        pages = out.split(T.PAGE)
        self.assertEqual(pages[-1].split(T.NL)[-1], "きく")  # 마지막 줄만 그대로
        self.assertNotEqual(pages[0].split(T.NL)[0], "あい")  # 앞 줄들은 채워졌다

    def test_창_폭을_꽉_채우지_않는다(self):
        """🔴 `width` 칸을 꽉 채우면 엔진이 **자동으로** 줄을 넘기고, 뒤의 `0D` 가
        **빈 줄을 하나 더** 만든다 → 페이지가 늘어 **화자 줄이 스크롤로 사라진다**
        (실기 실측 2026-08-24). 그래서 한 반칸을 남긴다."""
        out = T.pad_to_budget("あ\nい", 3 + 2 * 16)
        for line in T.lines(out)[:-1]:
            self.assertLessEqual(T.cols(line), T.WIN_COLS - 0.5, repr(line))

    def test_홀수_예산은_반각_공백으로_맞춘다(self):
        """반각 공백은 0.5칸 · 1B — 전각만 쓰면 2B 눈금이라 홀수를 못 맞춘다(실측 1.8%)."""
        out = T.pad_to_budget("あいうえお\nかきくけこ", 22)
        self.assertEqual(T.body_bytes(out), 22)
        self.assertTrue(out.split(T.NL)[0].endswith(T.PAD_HALF))
        self.assertEqual(T.cols(out.split(T.NL)[0]), 5.5)

    def test_반칸_단위로_센다(self):
        """🔴 칸을 정수로 반올림하면 자리를 한 칸 더 있다고 착각한다 — 그만큼 밀려
        **다음 줄 첫 글자가 0.5칸 들여쓰기** 된다(실기에서 그 현상을 봤다)."""
        base = "あ" + T.PAD_HALF  # 1.5칸
        out = T.pad_to_budget(base + "\nい", T.body_bytes(base + "\nい") + 30)
        self.assertEqual(T.cols(out.split(T.NL)[0]), T.WIN_COLS - 0.5)

    def test_못_맞추면_None(self):
        self.assertIsNone(T.pad_to_budget("あいうえお\nかきくけこ", 10))  # 문안이 더 길다
        self.assertIsNone(T.pad_to_budget("あ\nい", 3 + 2 * 100))  # 패딩 자리가 모자란다

    def test_같으면_그대로(self):
        t = "あいうえお\nかきくけこ"
        self.assertIs(T.pad_to_budget(t, T.body_bytes(t)), t)

    def test_패딩_뒤에도_계약을_지킨다(self):
        out = T.pad_to_budget("あいうえお\nかきくけこ", 41)
        self.assertEqual(T.overflows(out), [])



class DescWindow(unittest.TestCase):
    """설명 창(9전각 × 4행) — 대사창(17×3) 과 **다른 창**이다."""

    def test_wraps_on_word_boundaries(self):
        # 일본어 원문엔 공백이 없어 손으로 끊었지만 한국어는 어절로 끊어야 읽힌다.
        # 🔴 어절 공백은 **전각**이다 — 반각(0x20)을 섞으면 화면에서 개행이 깨진다.
        S = T.DESC_SPACE
        # 「아주 평범한 단검」은 글자 8 + 전각공백 2 = **9 칸**이라 한 줄에 딱 들어간다.
        self.assertEqual(T.wrap_desc("아주 평범한 단검"), [f"아주{S}평범한{S}단검"])
        # 한 칸만 넘겨도 **어절 단위로** 접힌다 — 글자 단위로 끊으면 안 읽힌다.
        self.assertEqual(T.wrap_desc("아주 평범한 단검이다"), [f"아주{S}평범한", "단검이다"])

    def test_never_emits_a_halfwidth_space(self):
        # 🔴 실측: 반각 공백이 섞이면 `＄` 가 개행되지 않고 `$` 글자로 찍힌다.
        for s in ("아주 평범한 단검", "체력을 조금 회복하는 약", "가나 다라 마바 사아 자차"):
            self.assertNotIn(" ", T.DESC_NL.join(T.wrap_desc(s)))

    def test_long_word_is_split_not_dropped(self):
        # ⚠ 폭보다 긴 어절을 그냥 두면 줄이 통째로 사라진다.
        rs = T.wrap_desc("가나다라마바사아자차카타파하")
        self.assertEqual(rs, ["가나다라마바사아자", "차카타파하"])

    def test_overflow_reports_rows_and_width(self):
        over, n, w = T.desc_overflows("짧다")
        self.assertFalse(over)
        self.assertEqual((n, w), (1, 2.0))
        over, n, _ = T.desc_overflows(" ".join(["아홉글자짜리단어"] * 6))
        self.assertTrue(over)
        self.assertGreater(n, T.DESC_ROWS)

    def test_newline_marker_is_fullwidth(self):
        # 제어 바이트로 찾으면 못 찾는다 — `＄` 는 전각 문자다.
        self.assertEqual(len(T.DESC_NL.encode("shift_jis")), 2)

    def test_engine_wrap_is_wider_than_the_visible_window(self):
        # 🔴 실측: 엔진은 16 에서 접는데 창은 ~10 자만 보여 준다.
        #    그 사이(10~16)는 **그려지고도 안 보인다** — 검사를 통과하고 화면에서만 사라진다.
        #    조판 폭은 반드시 엔진 상한보다 좁아야 한다.
        self.assertLess(T.DESC_COLS, T.DESC_ENGINE_WRAP)


if __name__ == "__main__":
    unittest.main()
