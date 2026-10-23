"""인사 「これは」 직역 검사 — 걸려야 할 것 · 안 걸려야 할 것(가짜 문장)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from check_greeting import hits


def _n(jp, kr):
    return len(list(hits([("x", jp, kr, "dialog")])))


class GreetingTest(unittest.TestCase):
    def test_doubled_greeting(self):
        self.assertEqual(_n("これはこれは、ようこそ。", "이거 이거, 어서 오세요."), 1)

    def test_greeting_with_title(self):
        self.assertEqual(_n("これは テスト王子さま。", "〔병사〕↵이거 테스트 왕자님."), 1)
        self.assertEqual(_n("これは テストさま。", "앗, 이거 테스트님."), 1)

    def test_title_variants(self):
        self.assertEqual(
            _n("これは {テスト}さま よくおいで。", "이거 {테스트} 아가씨, 잘 오셨네."), 1
        )
        self.assertEqual(_n("これは テスト姫。", "이거 테스트 공주."), 1)

    def test_rule_4_10(self):
        # 사람을 맞는 감탄사 전반(마스터 10-24) — 고맙다·실례·이름 토큰·국왕
        self.assertEqual(_n("これはどうも ありがとう。", "이거 정말 감사합니다."), 1)
        self.assertEqual(_n("これは 失礼しました。", "이거 실례했습니다."), 1)
        self.assertEqual(_n("これは{テストおうじ}。", "이거, {D0:2B}."), 1)
        self.assertEqual(_n("これは どうも テストさま。", "이거 국왕 폐하."), 1)
        self.assertEqual(_n("これはどうも ありがとう。", "정말 감사합니다."), 0)
        self.assertEqual(_n("これは 失礼しました。", "아, 실례했습니다."), 0)

    def test_fixed_greeting_passes(self):
        self.assertEqual(_n("これはこれは、ようこそ。", "아니, 이게 누구십니까. 어서 오세요."), 0)
        self.assertEqual(_n("これは テスト王子さま。", "이런, 테스트 왕자님."), 0)

    def test_demonstrative_passes(self):
        # 정말 「이것은」 — 원문이 인사 꼴이 아니다
        self.assertEqual(_n("これは難しいのう。", "이거 어렵구먼."), 0)
        self.assertEqual(_n("こりゃ ボロボロだな。", "이거 참 너덜너덜하군."), 0)

    def test_untranslated_skipped(self):
        self.assertEqual(_n("これはこれは。", None), 0)


if __name__ == "__main__":
    unittest.main()
