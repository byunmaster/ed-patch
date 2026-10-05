"""조판 검사기 자체의 회귀 — 창 줄넘김 모형과 「글 소실 없음」 불변식(2026-09-27, 밤에 글자 단위로 되돌림).

PS1 이 어절 단위 줄넘김을 고치다 특정 폭에서 꼬리 글을 잃었다(「ＨＰ를 112 / 빼앗았다!!」). 폭만 보는 검사는 못 잡는다 —
불변식이 그걸 잡는지, 그리고 우리 모형(다음 글자가 안 들어갈 때만 넘김)이 실측과 같은지 못 박는다.
🔴 마스터 최종 확정(기종 공통, 2026-09-27 밤) — 로그성 메시지는 **글자 단위**로 접는다(낱말 가운데서
갈리는 것도 허용). 대신 ① 고아 부호(.!?)가 혼자 줄 첫머리로 못 가고(앞줄 끝에 매단다) ② 줄이 공백으로
시작하지 않는다(넘친 공백은 버린다) 이 둘만 막는다.
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
        # 실측: 210px 딱 맞는 줄은 한 줄(「게일은 세리오스에게 레스1을 외웠다」).
        line = "게일은 세리오스에게 레스１을 외웠다"
        self.assertEqual(cl.width(line), 210)
        self.assertEqual(cl.wrap(line, cl.LIMIT), [line])

    def test_orphan_punct_hangs_at_line_end(self):
        # 고아 부호 금지 — 넘쳐도 줄을 안 바꾸고 앞줄 끝에 매단다(마침표·느낌표·물음표 · 「!!」·「!?」 연쇄도)
        line = "게일은 세리오스에게 레스１을 외웠다"
        self.assertEqual(cl.wrap(line + ".", cl.LIMIT), [line + "."])
        self.assertEqual(cl.wrap(line + "!!", cl.LIMIT), [line + "!!"])
        self.assertEqual(cl.wrap(line + "!?", cl.LIMIT), [line + "!?"])

    def test_space_at_edge_is_dropped(self):
        # 넘친 글자가 공백이면 줄만 바꾼다 — 새 줄이 공백으로 시작하지 않는다(렌더러 패치의 공백 갈래)
        line = "게일은 세리오스에게 레스１을 외웠다 끝."
        self.assertEqual(cl.wrap(line, cl.LIMIT), ["게일은 세리오스에게 레스１을 외웠다", "끝."])

    def test_mid_word_break_is_allowed(self):
        # 글자 단위 — 낱말 가운데서 갈려도 검사기는 위반으로 안 센다(마스터 판정 예시: 「사용했 / 다.」)
        word = "가" * 20
        self.assertEqual([len(x) for x in cl.wrap(word, cl.LIMIT)], [17, 3])

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
