"""엔진 패치(공백 8px)의 계약 — 원본 없이 도는 회귀.

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
        words, labels = engine_patch.hooks("ed3", 0xE5, 8)
        p = engine_patch.PATCH["ed3"]
        self.assertLessEqual(4 * len(words), p["table_off"])  # 표를 침범하지 않는다
        # 틀 루틴은 본 훅 뒤에 — `lhu v1,0x14(fp)` 로 시작한다(원래 그 자리의 명령)
        k = (labels["framew"] - p["dead"]) // 4
        self.assertEqual(words[k], p["frame_edge_orig"][0])
        # 막대 루틴 둘은 같은 꼬리(`sh v1,0x2e(fp)`)로 나간다
        self.assertEqual(words[(labels["bar_out"] - p["dead"]) // 4 + 1], p["frame_bar_orig"][1])
        # 본 훅의 끝은 폰트 베이스 복원 — `lui a1,0x800a` · `jr ra` · `addiu a1,a1,-0x1e90`
        self.assertEqual(words[k - 3], 0x3C05800A)
        self.assertEqual(words[k - 2], 0x03E00008)
        self.assertEqual(words[k - 1], 0x24A5E170)

    def _run_hook(self, cols):
        """🔴 글리프 x 의 기준은 **틀 왼쪽 스프라이트**다(핸들 x 아님, 2026-10-05).

        창 이동은 핸들 x 를 먼저 바꾸고 스프라이트는 op 6 이 첫 칸 현재 x 기준 델타로 옮긴다.
        훅이 핸들 x 로 첫 칸을 미리 옮기면 델타 0 → 틀만 제자리 → 팝업 글자가 테두리를 밟는다.
        미니 MIPS 해석기로 훅을 실제로 돌려, 핸들 x 와 틀 x 가 달라도 칸 x = 틀 x + 12 + Σ폭인지 본다.
        """
        import struct

        p = engine_patch.PATCH["ed3"]
        base = p["dead"]
        words, _ = engine_patch.hooks("ed3", 0xE5, 8)
        mem = {}

        def w16(a, v):
            mem[a] = v & 0xFF
            mem[a + 1] = (v >> 8) & 0xFF

        def r8(a):
            return mem.get(a, 0)

        def r16(a):
            return r8(a) | (r8(a + 1) << 8)

        h = p["handles"] + 22 * 2  # 두 번째 핸들 — 열 24(대사창) · 행 2, 스프라이트 시작 96, slotbase 0x5a
        w16(h, 0x8000)
        w16(h + 2, (-144) & 0xFFFF)  # 핸들 x 는 -144
        w16(h + 6, cols)
        w16(h + 8, 2)
        w16(h + 0xA, 96)
        w16(h + 0xE, 0x5A)
        frame = p["prims"] + (96 + cols * 2) * 20  # 틀 첫 스프라이트
        w16(frame + 8, (-128) & 0xFFFF)  # 틀은 핸들보다 16px 오른쪽에 있다(이동 중 어긋난 상태)
        slotw = base + p["table_off"]
        for k in range(6):  # 앞선 칸 폭은 이미 표에 있다(타자기 순)
            mem[slotw + 0x5A + k] = 12

        regs = [0] * 32
        R = engine_patch._R
        regs[R["a2"]] = 0x100  # 코드(공백 아님)
        fp = 0x801F0000
        regs[R["fp"]] = fp
        w16(fp + 0x10, 0x5A + 1 + 4)  # 칸 색인 + 1 — 두 번째 줄 둘째 칸(k = 4)
        regs[R["ra"]] = 0xDEAD0000
        pc, hi, lo, steps = base, 0, 0, 0
        code = {base + 4 * i: wd for i, wd in enumerate(words)}

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
            elif op in (9, 0xD, 0xC, 0xF, 0xA):
                a = regs[rs]
                if op == 9:
                    regs[rt] = (a + sx16(imm)) & 0xFFFFFFFF
                elif op == 0xD:
                    regs[rt] = a | imm
                elif op == 0xC:
                    regs[rt] = a & imm
                elif op == 0xF:
                    regs[rt] = imm << 16
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
            res = step(code[pc], pc)
            slot = step(code[pc + 4], pc + 4) if res is not None else None  # 지연 슬롯
            if res is None:
                pc += 4
            elif isinstance(res, tuple):
                pc = res[1] if res[0] == "br" else pc + 8
            else:
                pc = res
        sprite = p["prims"] + (96 + 4) * 20  # k = 4
        return sx16(r16(sprite + 8)), sx16(r16(sprite + 0x5000 + 8))

    def test_cell_x_follows_frame_not_handle(self):
        """🔴 대사창(열 24)의 글리프 x 기준은 **틀 왼쪽 스프라이트**다(핸들 x 아님, 2026-10-05).

        창 이동은 핸들 x 를 먼저 바꾸고 스프라이트는 op 6 이 첫 칸 현재 x 기준 델타로 옮긴다.
        훅이 핸들 x 로 첫 칸을 미리 옮기면 델타 0 → 틀만 제자리 → 팝업 글자가 테두리를 밟는다.
        """
        want = -128 + 12 + 4 * 12  # 틀 x + 12 + 앞선 네 칸(12)
        self.assertEqual(self._run_hook(engine_patch.COLS), (want, want))

    def test_ui_windows_keep_original_grid(self):
        """🔴 열 24 가 아닌 창(목록·패널·팝업)은 칸 폭 표를 안 본다 — 틀 + 12 + 열 × 12 (원판 격자).

        페이지를 넘겨 다시 그릴 때 칸 폭 표와 스프라이트 x 가 어긋나 「마」가 「ㅁ」으로 덮였다.
        앞선 칸 폭이 표에서 8 이어도(공백 흔적) 영향이 없어야 한다.
        """
        want14 = -128 + 12 + 4 * 12  # k=4 → 열 4
        want3 = -128 + 12 + 1 * 12  # 열 3 짜리는 k=4 → 열 1
        self.assertEqual(self._run_hook(14), (want14, want14))
        self.assertEqual(self._run_hook(3), (want3, want3))

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
