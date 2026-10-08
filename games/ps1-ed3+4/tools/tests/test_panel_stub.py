"""월드맵 패널 가운데 정렬 스텁(`tile_hook.panel_stubs`) — 미니 MIPS 해석기로 줄 시작 x · 글자 뒤 x 전진을 잰다(원본 없이 돈다).

패널 문자열은 `0x8002` 로 끝나는 한 문자열 안의 줄들이고, 줄 시작 x = 칸 왼쪽 + 36 − 6×(그 줄 글자 수)여야 한다(0 코드는 안 센다) — 한글 글자 수가 갈려도 6px 해상도로 정확히 가운데.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine_patch as E
import tile_hook as T

FP, STR, HANDLE, RA_END = 0x801F0000, 0x80200000, 0x80210000, 0xDEAD0000


def run(words, base, entry, string, idx22=0, x0=100):
    mem = {}

    def w16(a, v):
        mem[a] = v & 0xFF
        mem[a + 1] = (v >> 8) & 0xFF

    def w32(a, v):
        w16(a, v & 0xFFFF)
        w16(a + 2, v >> 16)

    def r16(a):
        return mem.get(a, 0) | (mem.get(a + 1, 0) << 8)

    w32(FP + 0x60, STR)
    w32(FP + 0x34, HANDLE)
    w16(HANDLE + 2, x0)
    w16(FP + 0x22, idx22)
    w16(FP + 0x10, x0)
    for i, c in enumerate(string):
        w16(STR + 2 * i, c)
    prog = {base + 4 * i: w for i, w in enumerate(words)}
    R = E._R
    regs = [0] * 32
    regs[R["fp"]] = FP
    regs[R["ra"]] = RA_END
    regs[R["v0"]] = x0

    def sx(v):
        return v - 0x10000 if v & 0x8000 else v

    def step(wd):
        op, rs, rt, imm = wd >> 26, (wd >> 21) & 31, (wd >> 16) & 31, wd & 0xFFFF
        rd, sa, fn = (wd >> 11) & 31, (wd >> 6) & 31, wd & 63
        nxt = None
        if op == 0:
            if fn == 0:
                regs[rd] = (regs[rt] << sa) & 0xFFFFFFFF
            elif fn == 8:
                nxt = ("j", regs[rs])
            elif fn == 0x21:
                regs[rd] = (regs[rs] + regs[rt]) & 0xFFFFFFFF
            elif fn == 0x23:
                regs[rd] = (regs[rs] - regs[rt]) & 0xFFFFFFFF
            else:
                raise AssertionError(f"R {fn:#x}")
        elif op in (4, 5):
            take = (regs[rs] == regs[rt]) == (op == 4)
            nxt = ("j", base_pc[0] + 4 + (sx(imm) << 2)) if take else None
        elif op == 2:
            nxt = ("j", ((wd & 0x3FFFFFF) << 2) | 0x80000000)
        elif op == 9:
            regs[rt] = (regs[rs] + sx(imm)) & 0xFFFFFFFF
        elif op == 0xC:
            regs[rt] = regs[rs] & imm
        elif op in (0x21, 0x25):
            v = r16((regs[rs] + sx(imm)) & 0xFFFFFFFF)
            regs[rt] = (sx(v) if op == 0x21 else v) & 0xFFFFFFFF
        elif op == 0x23:
            a = (regs[rs] + sx(imm)) & 0xFFFFFFFF
            regs[rt] = r16(a) | (r16(a + 2) << 16)
        elif op == 0x29:
            w16((regs[rs] + sx(imm)) & 0xFFFFFFFF, regs[rt])
        else:
            raise AssertionError(f"op {op:#x}")
        regs[0] = 0
        return nxt

    base_pc = [0]
    pc = entry
    for _ in range(5000):
        if pc == RA_END:
            break
        base_pc[0] = pc
        res = step(prog[pc])
        if res is None:
            pc += 4
            continue
        base_pc[0] = pc
        step(prog[pc + 4])  # 지연 슬롯
        pc = res[1]
    else:
        raise AssertionError("무한루프")
    return r16(FP + 0x10), r16(FP + 0x24)


class TestPanelStub(unittest.TestCase):
    def setUp(self):
        self.words, self.base, self.lab = T.panel_stubs("ed3")

    def line_x(self, string, line_start_idx=0):
        entry = self.lab["stub_init"] if line_start_idx == 0 else self.lab["stub_line"]
        idx22 = 0 if line_start_idx == 0 else line_start_idx - 1  # 줄바꿈 코드의 색인(= fp+0x22), 다음 줄은 +1
        return run(self.words, self.base, entry, string, idx22)[0]

    def test_first_line_is_centered_at_six_pixel_resolution(self):
        for n in range(1, 7):
            x = self.line_x([0x100 + k for k in range(n)] + [0x8002])
            self.assertEqual(x, 100 + 36 - 6 * n, n)  # 6자 = 칸 왼쪽, 3자 = +18 (반 칸 단위)

    def test_zero_indent_codes_are_not_counted(self):
        self.assertEqual(self.line_x([0, 0, 0x100, 0x101, 0x102, 0, 0x8002]), 100 + 36 - 18)

    def test_second_line_is_measured_from_its_own_start(self):
        s = [0x100, 0x101, 0x102, 0x103, 0x104, 0x8000, 0x200, 0x8002]  # 5자 ⏎ 1자
        self.assertEqual(self.line_x(s, 0), 100 + 36 - 30)
        self.assertEqual(self.line_x(s, 6), 100 + 36 - 6)  # 줄바꿈이 색인 5 → 다음 줄은 6

    def test_advance_is_twelve_except_for_zero_codes(self):
        words, base, lab = self.words, self.base, self.lab
        x, _ = run(words, base, lab["stub_adv"], [0x100, 0x8002], idx22=0, x0=50)
        self.assertEqual(x, 62)
        x, _ = run(words, base, lab["stub_adv"], [0, 0x8002], idx22=0, x0=50)
        self.assertEqual(x, 50)

    def test_stub_and_sites_fit(self):
        p = E.PATCH["ed3"]
        self.assertLessEqual(T.PANEL_CODE_OFF + 4 * len(self.words), p["data_len"])
        self.assertGreaterEqual(T.PANEL_CODE_OFF, T.data_size(60))  # 상태·표(받침표 60개까지) 뒤


if __name__ == "__main__":
    unittest.main()
