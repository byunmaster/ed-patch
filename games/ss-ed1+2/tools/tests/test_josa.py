"""동적 조사 회귀 — **원본 없이 돈다**(레포 규약).

여기 있는 `fix_buffer` 는 **기계어 루틴의 기준 구현**이다. 기계어를 고칠 때는 여기에
먼저 맞추고, 그다음 디스어셈블로 검산한다(레포 빌드 규율 「손인코딩은 디스어셈블로 검산」).
"""

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

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
        buf = bytearray(enc(s, self.codes) + b"\x00")
        n = josa.fix_buffer(buf, self.table, self.codes)
        return dec(buf, self.codes), n

    def test_table_size_and_range(self):
        """🔴 **바이트 표다** — SH-2 엔 가변 시프트가 없어 비트맵을 못 읽는다."""
        self.assertEqual(len(self.table), josa.CODE_HI - josa.CODE_LO + 1)
        self.assertEqual(len(self.table), 958)
        self.assertTrue(set(self.table) <= {0, 1})
        for ch, code in self.codes.items():
            self.assertTrue(josa.CODE_LO <= code <= josa.CODE_HI, ch)

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
        for a, b in josa.pairs(self.codes):
            self.assertTrue(josa.CODE_LO <= a <= josa.CODE_HI)
            self.assertTrue(josa.CODE_LO <= b <= josa.CODE_HI)


if __name__ == "__main__":
    unittest.main(verbosity=2)
