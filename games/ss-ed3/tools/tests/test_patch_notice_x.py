"""안내 화면 줄별 정중앙 패치 회귀 — 원본 없이 돈다(가짜 바이트)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import patch_notice_x as P

H = bytes.fromhex("9eb59fb4")  # 한글 글리프 코드 2개(2바이트 × 2 = 24px)


def fake(strings, imms):
    """`strings` = {주소: 바이트}, `imms` = {즉값 주소: x} — 문자열 뒤는 0 으로 채워 칸을 둔다."""
    b = bytearray(0x60000)
    for a, v in strings.items():
        o = a - P.BASE
        b[o : o + len(v)] = v
    for a, x in imms.items():
        o = a - P.BASE
        b[o] = 0xE4
        b[o + 1] = x & 0xFF
    return b


class Width(unittest.TestCase):
    def test_hangul_is_12px_and_ascii_is_6px(self):
        self.assertEqual(P.width(H), 24)
        self.assertEqual(P.width(b"RAM"), 18)
        self.assertEqual(P.width(H + b" " + H), 24 + 6 + 24)

    def test_trailing_period_comma_and_ellipsis_are_excluded(self):
        self.assertEqual(P.width(H + b"."), 24)
        self.assertEqual(P.width(H + b","), 24)
        self.assertEqual(P.width(H + b"\x81\x63"), 24)  # `…`
        self.assertEqual(P.width(H + b"\x81\x63" + H), 12 * 5)  # 가운데 `…` 는 센다
        self.assertEqual(P.width(H + b"?"), 24 + 6)  # `?` `!` 는 센다(안내 문구 규칙 2-8)

    def test_percent_d_counts_as_one_digit(self):
        self.assertEqual(P.width(b"%d " + H), 6 + 6 + 24)


class Ideal(unittest.TestCase):
    def test_box_is_centered_on_165_and_half_pixel_goes_left(self):
        # 글자 시작 프레임 x = 즉값 + 앞 공백×6 + 14, 화면 정중앙 = 165
        self.assertEqual(P.ideal(54) + P.ORIGIN + 54 / 2, 165)
        self.assertEqual(P.ideal(150) + P.ORIGIN + 150 / 2, 165)
        self.assertEqual(P.ideal(55), 165 - 14 - 28)  # 27.5 → 내림(왼쪽)


class Plan(unittest.TestCase):
    def test_single_string_keeps_its_lead_and_moves_only_the_immediate(self):
        s = b" " * 14 + H * 3 + b"\x00\x00\x00\x00"  # 앞 공백 14 · 폭 72px
        data = fake({0x06045000: s}, {0x06045100: 24})
        P.SITES, old = ((0x06045100, (0x06045000,)),), P.SITES
        try:
            (p,) = P.plan(data)
            self.assertEqual(p["x_old"], 24)
            self.assertEqual(p["x_new"] + 14 * 6 + P.ORIGIN + 72 / 2, 165)
            self.assertEqual(p["strings"][0]["lead_old"], p["strings"][0]["lead_new"])
            new = P.patch(data)
            self.assertEqual(new[0x06045101 - P.BASE], p["x_new"] & 0xFF)
            self.assertEqual(
                bytes(new[0x06045000 - P.BASE : 0x06045000 - P.BASE + len(s)]), s
            )  # 문자열은 그대로
        finally:
            P.SITES = old

    def test_variants_share_one_immediate_and_the_lead_absorbs_the_difference(self):
        a = b" " * 3 + H * 2 + b"\x00\x00\x00\x00\x00\x00\x00\x00"  # 폭 48px
        c = b" " * 3 + H * 4 + b"\x00\x00\x00\x00\x00\x00\x00\x00"  # 폭 96px
        data = fake({0x06045000: a, 0x06045040: c}, {0x06045100: 24})
        P.SITES, old = ((0x06045100, (0x06045000, 0x06045040)),), P.SITES
        try:
            (p,) = P.plan(data)
            starts = [
                p["x_new"] + s["lead_new"] * 6 + P.ORIGIN + w / 2
                for s, w in zip(p["strings"], (48, 96), strict=True)
            ]
            self.assertEqual(starts, [165, 165])
            self.assertEqual(p["errors"], [])
        finally:
            P.SITES = old

    def test_odd_byte_difference_leaves_a_three_pixel_error(self):
        a = b" " * 3 + H * 2 + b"\x00\x00\x00\x00\x00\x00\x00\x00"  # 48px
        c = b" " * 3 + H * 2 + b"R" + b"\x00\x00\x00\x00\x00\x00\x00\x00"  # 54px — 1바이트 많다
        data = fake({0x06045000: a, 0x06045040: c}, {0x06045100: 24})
        P.SITES, old = ((0x06045100, (0x06045000, 0x06045040)),), P.SITES
        try:
            (p,) = P.plan(data)
            self.assertEqual(len(p["errors"]), 1)
            self.assertEqual(abs(p["errors"][0][1]), 3)
        finally:
            P.SITES = old

    def test_composite_line_adds_the_inserted_string_and_two_digits(self):
        fmt = b" " * 2 + H + b" %2d%s\x00\x00\x00\x00\x00\x00"
        arg = b" " + H * 2 + b"\x00\x00\x00\x00"
        data = fake({0x06045000: fmt, 0x06045040: arg}, {0x06045100: 24})
        P.SITES, old = ((0x06045100, ((0x06045000, (0x06045040,)),)),), P.SITES
        try:
            (p,) = P.plan(data)
            # 형식 본문: H(24) + 공백 6 + `00` 12 + 끼우는 문자열(공백 6 + H*2 48)
            self.assertEqual(p["parsed"][0]["width"], 24 + 6 + 12 + 6 + 48)
        finally:
            P.SITES = old

    def test_a_site_that_is_not_a_mov_immediate_stops_the_build(self):
        data = fake({0x06045000: b"  " + H + b"\x00\x00"}, {})
        P.SITES, old = ((0x06045100, (0x06045000,)),), P.SITES
        try:
            with self.assertRaises(AssertionError):
                P.plan(data)
        finally:
            P.SITES = old


if __name__ == "__main__":
    unittest.main()
