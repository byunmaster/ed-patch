"""동적 조사 회귀 — **원본 없이 돈다**(레포 규약).

여기 있는 `fix_buffer` 는 **기계어 루틴의 기준 구현**이다. 기계어를 고칠 때는 여기에
먼저 맞추고, 그다음 디스어셈블로 검산한다(레포 빌드 규율 「손인코딩은 디스어셈블로 검산」).
"""

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(TOOLS)), "..", "shared"))

import josa


def enc(s, codes):
    out = bytearray()
    for ch in s:
        if ch in codes:
            out += codes[ch].to_bytes(2, "big")
        else:
            out += ch.encode("cp932")
    return bytes(out)


def dec(b, codes):
    inv = {v: k for k, v in codes.items()}
    r, i = "", 0
    while i < len(b) and b[i]:
        c = b[i]
        if josa._lead(c) and i + 1 < len(b):
            r += inv.get((c << 8) | b[i + 1], "?")
            i += 2
        else:
            r += chr(c)
            i += 1
    return r


class Josa(unittest.TestCase):
    def setUp(self):
        self.codes = josa.slot_codes()
        self.table = josa.build_table(self.codes)

    def run_fix(self, s):
        """접은 결과 → `(문자열, 접은 횟수)`. ⚠ **꼬리 공백은 떼고 돌려준다** —
        접을 때마다 반각 넷이 붙는데(길이를 지키려고), 문안 비교에 잡음이라 여기서 벗긴다.
        붙었는지 자체는 `test_length_is_preserved_with_spaces` 가 따로 본다."""
        buf = bytearray(enc(s, self.codes) + b"\x00")
        n = josa.fix_buffer(buf, self.table, self.codes)
        return dec(buf, self.codes).rstrip(" "), n

    def test_length_is_preserved_with_spaces(self):
        """🔴 **줄어든 4바이트를 반각 공백으로 메운다 — NUL 이 아니다.**

        게임은 **접기 전 길이만큼** 그린다. NUL 로 채웠더니 줄어든 두 칸을 글리프 0 으로
        찍어 **화면에 흰 네모**가 남았다(2026-08-26 실기 · 원판엔 없다 · 훅을 램에서 꺼서
        사라지는 것까지 확인). 공백 넷 = 전각 두 칸이라 폭이 정확히 되돌아간다.
        """
        for s, folds in (("류난은(는) 잠에서 깼다.", 1), ("류난은(는) 소니아을(를) 보았다.", 2)):
            with self.subTest(s=s):
                raw = enc(s, self.codes) + b"\x00"
                buf = bytearray(raw)
                self.assertEqual(josa.fix_buffer(buf, self.table, self.codes), folds)
                self.assertEqual(len(buf), len(raw), "버퍼 길이가 변했다")
                t = buf.index(0)
                self.assertEqual(t, len(raw) - 1, "종단이 앞으로 당겨졌다 — 길이가 줄었다")
                self.assertEqual(
                    bytes(buf[t - 4 * folds : t]), b" " * (4 * folds), "꼬리가 공백이 아니다"
                )

    def test_table_size_and_range(self):
        """🔴 **니블 표다** — 한 바이트에 두 글자. 바이트 하나씩 쓰다 자리를 넘겼다(2026-08-27).

        ⚠ 구간은 **정본에서 유도한다** — 상수로 박았더니 새 글자 하나(`근` 0x8C5F)가
          상한을 넘겨 깨졌다. 안 고치면 그 글자만 조용히 받침 판정을 못 받는다.
        ⚠ 비트맵(1/8)은 안 쓴다 — SH-2 엔 가변 시프트가 없어 8분기가 붙는다.
        """
        lo, hi = josa.code_span()
        self.assertEqual(len(self.table), ((hi - lo) >> 1) + 1)
        self.assertTrue(set(self.table) <= {0x00, 0x01, 0x10, 0x11}, "니블이 아닌 값이 있다")
        for ch, code in self.codes.items():
            self.assertTrue(lo <= code <= hi, ch)

    def test_nibble_packing_round_trips(self):
        """🔴 **홀수·짝수 자리가 안 섞여야** 한다 — 섞이면 옆 글자의 받침을 읽는다."""
        lo, _hi = josa.code_span()
        for ch, code in self.codes.items():
            from text.josa import batchim

            self.assertEqual(
                josa.has_batchim(code, self.table),
                bool(batchim(ch)),
                f"{ch!r} 0x{code:04X} (자리 {(code - lo) & 1})",
            )

    def test_batchim_picks_the_right_particle(self):
        """받침 있으면 앞쪽(은·이·을), 없으면 뒤쪽(는·가·를)."""
        for name, want in (("류난", "은"), ("게일", "은"), ("세리오스", "는"), ("소니아", "는")):
            got, n = self.run_fix(f"{name}은(는) 잠에서 깼다.")
            self.assertEqual(n, 1, name)
            self.assertEqual(got, f"{name}{want} 잠에서 깼다.", name)

    def test_all_three_pairs(self):
        for a, b in (("은", "는"), ("이", "가"), ("을", "를")):
            got, n = self.run_fix(f"류난{a}({b}) 끝")
            self.assertEqual((got, n), (f"류난{a} 끝", 1))
            got, n = self.run_fix(f"소니아{a}({b}) 끝")
            self.assertEqual((got, n), (f"소니아{b} 끝", 1))

    def test_color_code_between_name_and_particle(self):
        """🔴 원문이 `%c이름%c은(는)…` 꼴이다 — ASCII 가 껴도 앞 음절을 잊으면 안 된다."""
        got, n = self.run_fix("%c류난%c은(는) 달아났다.")
        self.assertEqual((got, n), ("%c류난%c은 달아났다.", 1))

    def test_two_in_one_buffer(self):
        got, n = self.run_fix("류난은(는) 소니아을(를) 보았다.")
        self.assertEqual((got, n), ("류난은 소니아를 보았다.", 2))

    def test_idempotent_without_markup(self):
        """병기가 없으면 무동작 — 어느 경로에 걸어도 안전하다는 근거다."""
        for s in ("류난은 달아났다.", "회심의 일격!!", "HP 30/30"):
            got, n = self.run_fix(s)
            self.assertEqual((got, n), (s, 0))

    def test_second_pass_changes_nothing(self):
        buf = bytearray(enc("류난은(는) 달아났다.", self.codes) + b"\x00")
        self.assertEqual(josa.fix_buffer(buf, self.table, self.codes), 1)
        self.assertEqual(josa.fix_buffer(buf, self.table, self.codes), 0)

    def test_unknown_previous_falls_back_to_no_batchim(self):
        """앞 음절을 모르면 무받침 쪽 — 조용히 안 깨지는 기본값이다."""
        got, n = self.run_fix("은(는) 달아났다.")
        self.assertEqual((got, n), ("는 달아났다.", 1))

    def test_particles_are_the_expected_codes(self):
        want = {("은", "는"), ("이", "가"), ("을", "를")}
        got = {(a, b) for a, b in josa.JOSA_PAIRS}
        self.assertEqual(got, want)
        lo, hi = josa.code_span()
        for a, b in josa.pairs(self.codes):
            self.assertTrue(lo <= a <= hi)
            self.assertTrue(lo <= b <= hi)


if __name__ == "__main__":
    unittest.main(verbosity=2)
