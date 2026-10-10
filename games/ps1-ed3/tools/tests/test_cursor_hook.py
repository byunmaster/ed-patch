"""커서 줄 반각 훅(`cursor_hook`)을 해석기로 돌려 **파이썬 모델(`tilecomp`)과 타일 단위로 대조**한다 — 원본 없이 돈다."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cursor_hook as C
import engine_patch
import tile_hook
import tilecomp
from mips_cpu import RA_END, Cpu
from test_tile_hook import HALF, glyph_bytes, model_line

FP = 0x801F0000
WIN = 0x801D6498 + 22 * 3


def make(codes, cols, rows=4, y=-36, half=HALF):
    p = engine_patch.PATCH["ed3"]
    w1, w2, site, lab = C.build("ed3")
    prog = {C.R1 + 4 * i: w for i, w in enumerate(w1)}
    prog.update({C.R2 + 4 * i: w for i, w in enumerate(w2)})
    cpu = Cpu(prog)
    for c in set(codes) | set(half):
        for i, b in enumerate(glyph_bytes(c)):
            cpu.mem[C.FONT + c * 18 + i] = b
    S = p["data"]
    for i, h in enumerate(half):
        cpu.w16(S + tile_hook.OFF_HALF + 2 * i, h)
    cpu.w16(WIN + 6, cols)
    cpu.w16(WIN + 8, rows)
    cpu.w16(WIN + 4, y & 0xFFFF)
    cpu.w32(FP + 0x78, WIN)
    for i in range(cols):
        cpu.w16(FP + 0x28 + 2 * i, codes[i] if i < len(codes) else 0)
    R = engine_patch._R
    cpu.regs[R["fp"]] = FP
    cpu.regs[R["sp"]] = FP - 0x100
    cpu.regs[R["ra"]] = RA_END
    return cpu, S


class TestCursorHook(unittest.TestCase):
    def run_hook(self, codes, cols, **kw):
        cpu, S = make(codes, cols, **kw)
        cpu.run(C.R1)
        atb, v0 = C.buf_layout("ed3")
        arr = [cpu.r16(FP + 0x28 + 2 * i) for i in range(cols)]
        tiles = [bytes(cpu.r8(atb + 18 * t + i) for i in range(18)) for t in range(cols)]
        return arr, tiles, v0

    def check(self, codes, cols, **kw):
        arr, tiles, v0 = self.run_hook(codes, cols, **kw)
        self.assertEqual(arr, [(v0 + i) & 0xFFFF for i in range(cols)], "코드 배열이 가상 코드로")
        want = model_line(codes)
        for t in range(cols):
            exp = want.get(t, [0] * 12)
            self.assertEqual(tilecomp.unpack(tiles[t]), exp, f"타일 {t}")

    def test_full_width_only(self):
        self.check([0x100, 0x101, 0x102, 0x103], 6)

    def test_leading_half(self):
        self.check([0x0F0, 0x100, 0x101, 0x102, 0x103, 0x104], 6)

    def test_three_leading_halves(self):
        self.check([0x0F0, 0x0F1, 0x0F0, 0x100, 0x101, 0x102, 0x103], 8, rows=2, y=-24)

    def test_inner_half(self):
        self.check([0x100, 0x101, 0x102, 0x0F0, 0x103, 0x104], 6)

    def test_trailing_blank_cells(self):
        self.check([0x100, 0x0F0, 0x101], 6)

    def test_allow_lists_agree(self):
        """커서 줄 허용 창(`PROTO_WINDOWS`)은 대사 줄 훅 허용 목록(`MSG_WINDOWS`)의 부분집합 — 두 경로가 어긋나면 커서가 움직일 때 글자가 움직인다."""
        self.assertTrue(set(C.PROTO_WINDOWS) <= {(c, r) for c, r, _ in tile_hook.MSG_WINDOWS})
        self.assertIn((6, 4), C.PROTO_WINDOWS)

    def test_other_windows_untouched(self):
        for cols, rows, y in ((13, 4, -36), (6, 5, -36), (7, 4, -36), (9, 2, 30), (4, 2, -24)):
            cpu, S = make([0x100, 0x101, 0x102], cols, rows=rows, y=y)
            before = [cpu.r16(FP + 0x28 + 2 * i) for i in range(cols)]
            cpu.run(C.R1)
            after = [cpu.r16(FP + 0x28 + 2 * i) for i in range(cols)]
            self.assertEqual(before, after, f"{cols}x{rows} y{y} 는 그대로")


if __name__ == "__main__":
    unittest.main()
