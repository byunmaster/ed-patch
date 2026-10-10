"""전투 배너 세로 가운데 패치 회귀 — 원본 없이 돈다(가짜 바이트)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import patch_ui_center as P


def fake():
    b = bytearray(0x40000)
    b[P.TEXT_Y - P.BASE : P.TEXT_Y - P.BASE + 2] = P.TEXT_Y_ORIG
    b[P.BORDER_Y - P.BASE : P.BORDER_Y - P.BASE + 2] = P.BORDER_Y_ORIG
    b[P.DIGIT_BR - P.BASE : P.DIGIT_BR - P.BASE + 2] = P.DIGIT_BR_ORIG
    for lit in P.LIST_LITS:
        b[lit - P.BASE : lit - P.BASE + 4] = P.DRAW.to_bytes(4, "big")
    b[P.BANNER_LIT - P.BASE : P.BANNER_LIT - P.BASE + 4] = P.DRAW.to_bytes(4, "big")
    for lit in P.WAIT_LITS:
        b[lit - P.BASE : lit - P.BASE + 4] = P.WAIT.to_bytes(4, "big")
    return bytes(b)


class UiCenter(unittest.TestCase):
    def test_moves_the_banner_text_up_and_wraps_the_list_draws(self):
        old = fake()
        new = P.patch(old)
        diff = {i for i in range(len(old)) if old[i] != new[i]}
        self.assertIn(P.TEXT_Y - P.BASE + 1, diff)
        for lit in P.LIST_LITS:  # 목록 그리기 호출은 원본 그대로 — 껍데기를 달면 모든 목록 마지막 줄이 잘린다(10-05)
            self.assertEqual(new[lit - P.BASE : lit - P.BASE + 4], P.DRAW.to_bytes(4, "big"))
        # 배너 글자 호출은 이름 변환 껍데기로 돈다 — 쥬리오의 본 → 내려앉은 코드 쌍이 표에 있다
        self.assertEqual(
            new[P.BANNER_LIT - P.BASE : P.BANNER_LIT - P.BASE + 4], P.WRAP2.to_bytes(4, "big")
        )
        table, chars = P._person_pairs()
        self.assertIn("쥬", chars)
        self.assertIn(table[:4], P.wrap2_code())
        # add #imm,r1 — 부호 있는 imm8: −116 → −117 (한 줄 위)
        self.assertEqual(int.from_bytes(P.TEXT_Y_ORIG[1:], "big") - 256, -116)
        self.assertEqual(int.from_bytes(P.TEXT_Y_NEW[1:], "big") - 256, -117)

    def test_digit_branch_becomes_unconditional_halfwidth(self):
        new = P.patch(fake())
        self.assertEqual(new[P.DIGIT_BR - P.BASE : P.DIGIT_BR - P.BASE + 2], P.DIGIT_BR_NEW)
        # bra disp12: 0x06041D7E + 4 + 2×0x0C = 0x06041D9A (반각 경로 — 원래 `bt/s` 의 목표와 같다)
        self.assertEqual(P.DIGIT_BR + 4 + 2 * (int.from_bytes(P.DIGIT_BR_NEW, "big") & 0xFFF), 0x06041D9A)
        self.assertEqual(P.DIGIT_BR + 4 + 2 * P.DIGIT_BR_ORIG[1], 0x06041D9A)

    def test_wait_routine_goes_through_the_cursor_wrapper(self):
        new = P.patch(fake())
        for lit in P.WAIT_LITS:  # `▼` 대기 루틴 호출 둘이 껍데기로 돈다
            self.assertEqual(new[lit - P.BASE : lit - P.BASE + 4], P.WRAP3.to_bytes(4, "big"))
        code = P.wrap3_code()
        self.assertEqual(new[P.WRAP3 - P.BASE : P.WRAP3 - P.BASE + len(code)], code)
        self.assertLessEqual(P.WRAP3 + len(code), P.WRAP2)  # 이웃(WRAP2)을 안 덮는다
        self.assertIn(P.WAIT.to_bytes(4, "big"), code)  # 원래 대기 루틴으로 점프한다
        self.assertIn(P.WINS.to_bytes(4, "big"), code)

    def test_refuses_a_different_build(self):
        bad = bytearray(fake())
        bad[P.TEXT_Y - P.BASE : P.TEXT_Y - P.BASE + 2] = b"\x00\x00"
        with self.assertRaises(AssertionError):
            P.patch(bytes(bad))
        bad = bytearray(fake())
        bad[P.BORDER_Y - P.BASE : P.BORDER_Y - P.BASE + 2] = b"\x00\x00"
        with self.assertRaises(AssertionError):
            P.patch(bytes(bad))


if __name__ == "__main__":
    unittest.main()
