"""읽을거리 줄 나눔 회귀 — **원본 없이 돈다**(순수 문자열 계산).

🔴 `split_to` 의 목적함수는 셋이다 — **낱말 갈림**(무겁다) · **부호 고아** · **짧은 줄**.
   낱말 갈림만 세던 때는, 문안을 줄여 여유가 생기면 DP 가 남는 자리를 아무 데나 흘려
   `．` 만 홀로 선 줄과 두 글자짜리 줄이 나왔다(2026-09-03 인게임 실측).
   ⚠ 그래서 **미관 벌점이 낱말 갈림보다 싸야** 한다 — 비싸지면 갈림을 늘려 가며 모양을
     맞추게 된다. 이 테스트가 그 순서를 못 박는다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import book as B


class Split(unittest.TestCase):
    def test_no_orphan_punctuation(self):
        #   `．` 이 다음 줄 첫 글자로 밀리면 안 된다 — 앞 줄에 붙는 게 읽힌다
        text = B.tidy_spaces(B.to_fullwidth("가나다라마 바사아자차. 카타파하 거너더러."))
        rows, ok = B.split_to(text, [20, 20, 20])
        self.assertTrue(ok)
        for r in rows:
            if r:
                self.assertNotIn(r[0], B.PUNCT, f"부호가 줄 머리에 섰다: {rows}")

    def test_no_half_empty_line(self):
        #   마지막이 아닌 줄이 칸의 절반도 못 채우면 안 된다
        text = B.tidy_spaces(B.to_fullwidth("가나다라 마바사아 자차카타 파하거너"))
        rows, ok = B.split_to(text, [24, 24, 24])
        self.assertTrue(ok)
        used = [B._nb(r) for r in rows if r]
        for w in used[:-1]:
            self.assertGreaterEqual(w * 2, 24, f"줄이 절반도 안 찼다: {rows}")

    def test_word_cut_still_wins(self):
        #   🔴 미관 때문에 낱말을 가르지 않는다 — 갈림 0 이 되는 배분이 있으면 그걸 고른다
        text = B.tidy_spaces(B.to_fullwidth("가나다라마바 사아자차카타"))
        rows, ok = B.split_to(text, [12, 12])
        self.assertTrue(ok)
        self.assertEqual(B.word_cuts(text, rows), 0, rows)


if __name__ == "__main__":
    unittest.main()
