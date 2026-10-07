"""엔진 패치(공백 6px)의 계약 — 원본 없이 도는 회귀.

손 인코딩은 디스어셈블이 멀쩡해 보여도 틀린다(로드 지연 · 지연 슬롯). 여기서 조립·검산이
매번 돌고, 사전조건(원본 워드·sha1)이 안 맞으면 **쓰지 않고 선다**는 것을 박는다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine_patch
import typeset


class TestEnginePatch(unittest.TestCase):
    def test_hooks_assemble_and_verify(self):
        words, labels = engine_patch.hooks("ed3", 0xE5, 6, with_frame=True)
        p = engine_patch.PATCH["ed3"]
        # (틀 보정 코드까지 넣은 변형이라 길다 — 실제 훅은 `test_real_hook_fits_the_dead_function`)
        # 틀 루틴은 본 훅 뒤에 — `lhu v1,0x14(fp)` 로 시작한다(원래 그 자리의 명령)
        k = (labels["framew"] - p["dead"]) // 4
        self.assertEqual(words[k], p["frame_edge_orig"][0])
        # 막대 루틴 둘은 같은 꼬리(`sh v1,0x2e(fp)`)로 나간다
        self.assertEqual(words[(labels["bar_out"] - p["dead"]) // 4 + 1], p["frame_bar_orig"][1])
        # 본 훅의 끝은 폰트 베이스 복원 — `lui a1,0x800a` · `jr ra` · `addiu a1,a1,-0x1e90`
        self.assertEqual(words[k - 3], 0x3C05800A)
        self.assertEqual(words[k - 2], 0x03E00008)
        self.assertEqual(words[k - 1], 0x24A5E170)

    def _run_hook(self, cols, code=0x100, col=4, x_here=None, rows=4, stale=False):
        """🔴 칸 x 는 **앞 칸 x + 앞 칸 폭**으로 이어진다 — 글자를 찍을 때 훅이 **다음 칸**의 x·폭을 정한다(2026-10-07).

        예전엔 찍는 칸 하나의 x 만 `틀.x+12+Σ앞선폭` 으로 썼고, 안 찍힌 칸은 원래 격자 자리에 남아 줄 끝에 (절약한 폭)만큼
        배경 틈이 났다(대사창 배경이 뚫려 보임). 미니 MIPS 해석기로 훅을 돌려 이 칸이 찍힌 뒤의 스프라이트를 돌려준다:
        {"x": 이 칸 x, "w": 이 칸 폭, "nx": 다음 칸 x, "nw": 다음 칸 폭, "n2x": 그다음 칸 x, "b1": 버퍼 1 이 같은가}.
        """
        p = engine_patch.PATCH["ed3"]
        base = p["dead"]
        words, _ = engine_patch.hooks("ed3", 0xE5, 6, (0x150, 0x151))
        mem = {}

        def w16(a, v):
            mem[a] = v & 0xFF
            mem[a + 1] = (v >> 8) & 0xFF

        def r8(a):
            return mem.get(a, 0)

        def r16(a):
            return r8(a) | (r8(a + 1) << 8)

        h = p["handles"] + 22 * 2  # 두 번째 핸들 — 열 · 행 4 · 스프라이트 시작 96 · slotbase 0x5a
        w16(h, 0x8000)
        w16(h + 2, (-144) & 0xFFFF)
        w16(h + 6, cols)
        w16(h + 8, rows)
        w16(h + 0xA, 96)
        w16(h + 0xE, 0x5A)
        for j in range(cols):  # 격자 원래 자리 — 12px 간격, 폭 12 (행 첫 칸 = 첫 줄 첫 스프라이트)
            for buf in (0, 0x5000):
                sp = p["prims"] + (96 + j) * 20 + buf
                w16(sp + 8, (-144 + 12 * j) & 0xFFFF)
                w16(sp + 16, 12)
                w16(sp + 12, (12 * (j % 21)) | (0x1A << 8))  # u v — 텍스처 한 줄에 타일 21개(u 0~240)
        if x_here is not None:  # 이 칸이 앞 글자들 때문에 이미 당겨져 있다
            for buf in (0, 0x5000):
                w16(p["prims"] + (96 + col) * 20 + buf + 8, x_here & 0xFFFF)
                w16(p["prims"] + (96 + col) * 20 + buf + 16, 30)  # 앞 글자가 넓혀 놨던 폭
        if stale:  # 앞선 짧은 대사가 남긴 압축 자리 — 첫 칸(엔진이 새로 쓴다) 빼고 전부 -6px 당겨져 있다
            for j in range(1, cols * rows):
                for buf in (0, 0x5000):
                    w16(p["prims"] + (96 + j) * 20 + buf + 8, (-144 + 12 * (j % cols) - 6) & 0xFFFF)
                    w16(p["prims"] + (96 + j) * 20 + buf + 16, 30)
        regs = [0] * 32
        R = engine_patch._R
        regs[R["a2"]] = code  # 코드(기본: 공백도 부호도 아님)
        fp = 0x801F0000
        regs[R["fp"]] = fp
        w16(fp + 0x10, 0x5A + 1 + col)  # 칸 색인 + 1 — 첫 줄 col 번째 칸(k = col)
        regs[R["ra"]] = 0xDEAD0000
        pc, hi, lo, steps = base, 0, 0, 0
        prog = {base + 4 * i: wd for i, wd in enumerate(words)}

        def sx16(v):
            return v - 0x10000 if v & 0x8000 else v

        def step(wd, pc):
            nonlocal hi, lo
            op, rs, rt, imm = wd >> 26, (wd >> 21) & 31, (wd >> 16) & 31, wd & 0xFFFF
            rd, sa, fn = (wd >> 11) & 31, (wd >> 6) & 31, wd & 63
            nxt = None
            if op == 0:
                if fn == 0:
                    regs[rd] = (regs[rt] << sa) & 0xFFFFFFFF
                elif fn == 8:
                    nxt = regs[rs]
                elif fn == 0x10:
                    regs[rd] = hi
                elif fn == 0x12:
                    regs[rd] = lo
                elif fn == 0x18:
                    lo = (regs[rs] * regs[rt]) & 0xFFFFFFFF
                    hi = 0
                elif fn == 0x1A:
                    a, b = regs[rs], regs[rt]
                    a = a - (1 << 32) if a & 0x80000000 else a
                    b = b - (1 << 32) if b & 0x80000000 else b
                    q = int(a / b)
                    lo, hi = q & 0xFFFFFFFF, (a - q * b) & 0xFFFFFFFF
                elif fn in (0x21, 0x23, 0x24, 0x25, 0x2A):
                    a, b = regs[rs], regs[rt]
                    sa_ = a - (1 << 32) if a & 0x80000000 else a
                    sb_ = b - (1 << 32) if b & 0x80000000 else b
                    regs[rd] = {
                        0x21: (a + b) & 0xFFFFFFFF,
                        0x23: (a - b) & 0xFFFFFFFF,
                        0x24: a & b,
                        0x25: a | b,
                        0x2A: int(sa_ < sb_),
                    }[fn]
                else:
                    raise AssertionError(f"해석기 미지원 R {fn:#x}")
            elif op in (4, 5, 1):
                a, b = regs[rs], regs[rt]
                sa_ = a - (1 << 32) if a & 0x80000000 else a
                take = (a == b) if op == 4 else (a != b) if op == 5 else (sa_ < 0 if rt == 0 else sa_ >= 0)
                nxt = ("br", pc + 4 + (sx16(imm) << 2)) if take else ("no", 0)
            elif op == 2:
                nxt = (wd & 0x3FFFFFF) << 2 | (pc & 0xF0000000)
            elif op in (9, 0xD, 0xC, 0xF, 0xA, 0xB):
                a = regs[rs]
                if op == 9:
                    regs[rt] = (a + sx16(imm)) & 0xFFFFFFFF
                elif op == 0xD:
                    regs[rt] = a | imm
                elif op == 0xC:
                    regs[rt] = a & imm
                elif op == 0xF:
                    regs[rt] = imm << 16
                elif op == 0xB:  # sltiu — 즉치는 부호 확장 뒤 부호 없이 비교
                    regs[rt] = int(a < (sx16(imm) & 0xFFFFFFFF))
                else:
                    sa_ = a - (1 << 32) if a & 0x80000000 else a
                    regs[rt] = int(sa_ < sx16(imm))
            elif op in (0x20, 0x21, 0x24, 0x25):
                a = (regs[rs] + sx16(imm)) & 0xFFFFFFFF
                if op in (0x21, 0x25):
                    v = r16(a)
                    regs[rt] = (sx16(v) if op == 0x21 else v) & 0xFFFFFFFF
                else:
                    regs[rt] = r8(a)
            elif op in (0x28, 0x29):
                a = (regs[rs] + sx16(imm)) & 0xFFFFFFFF
                if op == 0x28:
                    mem[a] = regs[rt] & 0xFF
                else:
                    w16(a, regs[rt])
            else:
                raise AssertionError(f"해석기 미지원 op {op:#x}")
            regs[0] = 0
            return nxt

        while pc != 0xDEAD0000:
            steps += 1
            self.assertLess(steps, 5000, "무한루프")
            res = step(prog[pc], pc)
            slot = step(prog[pc + 4], pc + 4) if res is not None else None  # 지연 슬롯
            if res is None:
                pc += 4
            elif isinstance(res, tuple):
                pc = res[1] if res[0] == "br" else pc + 8
            else:
                pc = res
        def sp(j, off, buf=0):
            return sx16(r16(p["prims"] + (96 + j) * 20 + buf + off))

        b1 = all(sp(j, 8) == sp(j, 8, 0x5000) and sp(j, 16) == sp(j, 16, 0x5000) for j in range(cols))
        return {
            "x": sp(col, 8),
            "w": sp(col, 16),
            "nx": sp(col + 1, 8),
            "nw": sp(col + 1, 16),
            "n2x": sp(col + 2, 8),
            "n2w": sp(col + 2, 16),
            "last_end": sp(cols - 1, 8) + sp(cols - 1, 16),
            "b1": b1,
            "all": [(sp(j, 8), sp(j, 16)) for j in range(cols * rows)],
        }

    def test_real_hook_fits_the_dead_function(self):
        """실제로 넣는 훅(틀 보정 없음)은 죽은 함수 자리(1092B, sha1 사전조건) 안에 든다."""
        p = engine_patch.PATCH["ed3"]
        words, _ = engine_patch.hooks("ed3", 0xE5, 6, (0x150, 0x151))
        self.assertLessEqual(4 * len(words), p["dead_len"])

    def test_next_cell_follows_this_cell(self):
        """🔴 12px 글자: 다음 칸 x = 이 칸 x + 12 → 원래 자리 그대로, 폭 12 (틈 없음)."""
        r = self._run_hook(engine_patch.COLS, code=0x100, col=4)
        self.assertEqual((r["x"], r["w"]), (-144 + 48, 12))
        self.assertEqual((r["nx"], r["nw"]), (-144 + 60, 12))
        self.assertTrue(r["b1"], "스프라이트 두 벌이 다르다")

    def test_half_width_cell_pulls_next_and_widens_it(self):
        """🔴 6px 칸(공백·부호)은 뒤 칸들을 6px 당기고 **틈을 첫 안 찍힌 칸의 폭(12+6)에 얹어** 그다음 칸(원래 자리)부터 잇는다."""
        for code in (0xE5, 1, 2, 4, 5, 0x150, 0x151):
            r = self._run_hook(engine_patch.COLS, code=code, col=4)
            self.assertEqual(r["nx"], -144 + 48 + 6, hex(code))
            self.assertEqual(r["nw"], 18, hex(code))
            # 다음 칸이 끝나는 자리 = 그다음 칸의 원래 자리 → 배경 틈이 없다
            self.assertEqual(r["nx"] + r["nw"], r["n2x"], hex(code))
            self.assertEqual((r["n2x"], r["n2w"]), (-144 + 12 * 6, 12), hex(code))
            self.assertEqual(r["last_end"], -144 + 12 * engine_patch.COLS, "맨 끝이 격자 오른쪽 끝에 닿아야 한다")
            self.assertTrue(r["b1"])

    def test_gap_stays_closed_with_accumulated_savings(self):
        """누적: 이 칸이 이미 −18px 당겨져 있고 6px 칸이면 → 다음 칸은 −24 에서 시작하고 폭 12+24 로 원래 자리를 잇는다."""
        r = self._run_hook(engine_patch.COLS, code=0xE5, col=4, x_here=-144 + 48 - 18)
        self.assertEqual(r["x"], -144 + 48 - 18)
        self.assertEqual(r["w"], 12)  # 앞 글자가 넓혀 놨던 폭을 이 칸은 12 로 되돌린다
        self.assertEqual(r["nx"], -144 + 48 - 18 + 6)
        self.assertEqual(r["nx"] + r["nw"], -144 + 12 * 6)  # 그다음 칸(col 6)의 원래 자리
        self.assertEqual(r["nw"], 12 + 24)

    def test_widening_never_reads_past_the_texture_row(self):
        """🔴 텍스처 한 줄은 타일 21개(u 0~240) — u+폭 이 252 를 넘으면 다른 그림이 배경에 비친다(색 점, 2026-10-07).
        u=240 인 칸(한 줄의 마지막)은 늘리지 않고, 몫은 다음 칸(u=0)으로 넘어간다."""
        r = self._run_hook(engine_patch.COLS, code=0xE5, col=19)  # 다음 칸 = col 20 → u 240
        self.assertEqual(r["nw"], 12)
        self.assertEqual(r["n2w"], 18)  # col 21 → u 0 이 6px 몫을 받는다
        self.assertEqual(r["last_end"], -144 + 12 * engine_patch.COLS)

    def test_widening_never_reads_tiles_the_window_does_not_have(self):
        """🔴 창의 타일은 칸 수(열×행)만큼뿐 — 그 뒤 텍스처는 쓰레기라 색 점이 비친다(마지막 줄이 12칸뿐인 창, 2026-10-07).
        한 줄짜리 창(24칸)에서 마지막 칸(타일이 뒤에 없다)은 늘리지 않는다."""
        r = self._run_hook(engine_patch.COLS, code=0xE5, col=20, rows=1)  # 다음 칸 = 21(뒤에 칸 2개 — 하나는 ▼ 타일)
        self.assertEqual(r["nw"], 12 + 6)  # ▼ 를 뺀 타일 한 개 몫(12)까지는 읽어도 된다 — 6px 몫은 들어간다
        r = self._run_hook(engine_patch.COLS, code=0xE5, col=21, rows=1)  # 다음 칸 = 22(뒤에 ▼ 타일뿐)
        self.assertEqual(r["nw"], 12, "▼ 타일을 읽으면 회색 화살표 타일이 비친다")
        r = self._run_hook(engine_patch.COLS, code=0xE5, col=22, rows=1)  # 다음 칸 = 마지막 칸(▼ 자리)
        self.assertEqual((r["nx"], r["nw"]), (-144 + 12 * 23, 12), "마지막 칸은 안 건드린다")

    def test_first_cell_restores_the_stale_grid(self):
        """🔴 줄 첫 칸(col 0)을 찍을 때 **뒤 칸 전부(행 포함)를 원래 격자로** 되돌린다 — 짧은 대사가 남긴 압축 자리가
        빈 줄 끝에 밝은 조각(구멍)으로 남는 걸 막는다. 마지막 칸(▼ 자리)은 안 건드린다(2026-10-07)."""
        n = engine_patch.COLS * 4
        r = self._run_hook(engine_patch.COLS, code=0x100, col=0, stale=True)
        for j in range(1, n - 1):
            self.assertEqual(r["all"][j], (-144 + 12 * (j % engine_patch.COLS), 12), j)
        self.assertEqual(r["all"][n - 1], (-144 + 12 * (engine_patch.COLS - 1) - 6, 30), "마지막 칸은 그대로")

    def test_last_column_has_no_next_cell(self):
        r = self._run_hook(engine_patch.COLS, code=0xE5, col=engine_patch.COLS - 1)
        self.assertEqual(r["w"], 12)

    def test_space_and_punctuation_are_half_width(self):
        """🔴 공백과 부호(`,` 1 · `.` 2 · `?` 4 · `!` 5)·괄호는 6px, 그 밖의 코드는 12px 다(마스터 2026-10-07 반각)."""
        for code, want in ((0xE5, 6), (1, 6), (2, 6), (4, 6), (5, 6), (3, 12), (0, 12), (6, 12), (0x100, 12), (0x150, 6), (0x151, 6), (0x152, 12)):
            r = self._run_hook(engine_patch.COLS, code=code, col=4)
            self.assertEqual(r["nx"] - r["x"], want, hex(code))

    def test_ui_windows_are_left_alone(self):
        """🔴 열 24 가 아닌 창(목록·패널·팝업)은 **엔진이 놓은 자리 그대로** — 훅이 아무것도 안 쓴다(원판)."""
        for cols in (14, 4):
            r = self._run_hook(cols, code=0xE5, col=2)
            self.assertEqual(r["nx"], -144 + 36, cols)
            self.assertEqual(r["nw"], 12, cols)

    def test_frame_stays_24_columns(self):
        """격자는 32칸이지만 틀은 24칸 — 유저 실측: 틀이 화면 오른쪽을 뚫었다."""
        self.assertEqual(engine_patch.FRAME_COLS, 24)
        self.assertEqual(engine_patch.asm("lhu v1, 0x14(fp)", 0)[0][0], 0x97C30014)
        self.assertEqual(engine_patch.asm("addiu v1, v0, 0xc\nsh v1, 0x2e(fp)", 0)[0], [0x2443000C, 0xA7C3002E])

    def test_cols_matches_typeset(self):
        """격자 열 수는 조판 상한과 같은 값이어야 한다 — 어긋나면 조판은 통과하고 화면이 잘린다."""
        self.assertEqual(engine_patch.COLS, typeset.COLS["ed3"])

    def test_verify_catches_load_delay(self):
        words, _ = engine_patch.asm("lw t0, 0(a0)\naddiu t1, t0, 1\njr ra\nnop", 0x80010000)
        with self.assertRaises(AssertionError):
            engine_patch.verify(words, 0x80010000)

    def test_verify_catches_branch_in_delay_slot(self):
        words, _ = engine_patch.asm("jr ra\nj 0x80010000\nnop", 0x80010000)
        with self.assertRaises(AssertionError):
            engine_patch.verify(words, 0x80010000)

    def test_asm_encodings(self):
        """디스어셈블로 읽은 원본 워드를 그대로 낸다 — 인코더가 틀리면 여기서 선다."""
        cases = {
            "lui a1, 0x800a": 0x3C05800A,
            "addiu a1, a1, -0x1e90": 0x24A5E170,
            "lw v0, 0xc(fp)": 0x8FC2000C,
            "addiu a2, zero, 0x18": 0x24060018,
            "sh v1, 8(v0)": 0xA4430008,
            "div zero, t4, t3": 0x018B001A,
            "jr ra": 0x03E00008,
        }
        for src, want in cases.items():
            self.assertEqual(engine_patch.asm(src, 0)[0][0], want, src)

    def test_apply_refuses_foreign_exe(self):
        """사전조건 — 원본이 아니면 한 바이트도 안 쓴다."""
        exe = bytearray(0xAF000)
        with self.assertRaises(SystemExit):
            engine_patch.apply(exe, "ed3", {" ": 0xE5})
        self.assertEqual(exe, bytearray(0xAF000))

    def test_no_patch_for_ed4_yet(self):
        self.assertIsNone(engine_patch.apply(bytearray(16), "ed4", {" ": 1}))


if __name__ == "__main__":
    unittest.main()
