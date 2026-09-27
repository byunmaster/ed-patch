"""조판 검사기 자체의 회귀 — 창 줄넘김 모형과 「글 소실 없음」 불변식(2026-09-27).

PS1 이 어절 단위 줄넘김을 고치다 특정 폭에서 꼬리 글을 잃었다(「ＨＰ를 112 / 빼앗았다!!」). 폭만 보는 검사는 못 잡는다 —
불변식이 그걸 잡는지, 그리고 우리 모형(다음 글자가 안 들어갈 때만 넘김)이 실측과 같은지 못 박는다.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_layout as cl


class Layout(unittest.TestCase):
    def test_lost_tail_is_caught(self):
        self.assertEqual(cl.lost("ＨＰ를 112 빼앗았다!!", "ＨＰ를 112"), "빼앗았다!!")

    def test_wrap_keeps_every_glyph(self):
        for n in range(1, 60):
            s = "가나 다." * n
            self.assertIsNone(cl.lost(s, "\n".join(cl.wrap(s, cl.LIMIT))))

    def test_exact_fit_does_not_wrap(self):
        # 실측: 210px 딱 맞는 줄은 한 줄(「게일은 세리오스에게 레스1을 외웠다」), 온점을 더하면 온점만 넘어간다
        line = "게일은 세리오스에게 레스１을 외웠다"
        self.assertEqual(cl.width(line), 210)
        self.assertEqual(cl.wrap(line, cl.LIMIT), [line])
        self.assertEqual(cl.wrap(line + ".", cl.LIMIT), [line, "."])

    def test_battle_window_measured(self):
        # 실측(09-27 시험 롬, r5-typeset-battle-288px.png): 반각 숫자 60자 → 48자에서 넘어갔다
        digits = "0123456789" * 6
        self.assertEqual(cl.BATTLE_LIMIT, 288)
        self.assertEqual([len(x) for x in cl.wrap(digits, cl.BATTLE_LIMIT)], [48, 12])

    def test_halfwidth_kana_is_half(self):
        # 원판 폭 — 반각 가나(「ﾎﾟｲﾝﾄ」)는 6px, 전각 가나는 12px
        self.assertEqual(cl.width_jp("ﾎﾟｲﾝﾄ"), 30)
        self.assertEqual(cl.width_jp("ポイント"), 48)


if __name__ == "__main__":
    unittest.main()
