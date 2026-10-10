"""미니 MIPS I 해석기(테스트 전용) — 메모리는 dict(바이트), 분기 지연 슬롯·`jal`/`jr`·`div`/`mflo`/`mfhi` 를 안다.
`test_tile_hook.Sim` 의 해석기를 일반화한 것이다(커서 줄 훅처럼 서브루틴을 부르는 코드를 돌리려고)."""

RA_END = 0xDEAD0000


class Cpu:
    def __init__(self, prog):
        self.prog = prog  # {주소: 워드}
        self.mem = {}
        self.regs = [0] * 32

    def r8(self, a):
        return self.mem.get(a, 0)

    def r16(self, a):
        return self.r8(a) | (self.r8(a + 1) << 8)

    def r32(self, a):
        return self.r16(a) | (self.r16(a + 2) << 16)

    def w16(self, a, v):
        self.mem[a] = v & 0xFF
        self.mem[a + 1] = (v >> 8) & 0xFF

    def w32(self, a, v):
        self.w16(a, v & 0xFFFF)
        self.w16(a + 2, v >> 16)

    def run(self, pc, max_steps=200000):
        regs, mem = self.regs, self.mem
        hi = lo = 0
        steps = 0

        def sx16(v):
            return v - 0x10000 if v & 0x8000 else v

        def s32(v):
            return v - (1 << 32) if v & 0x80000000 else v

        def step(wd, pc):
            nonlocal hi, lo
            op, rs, rt, imm = wd >> 26, (wd >> 21) & 31, (wd >> 16) & 31, wd & 0xFFFF
            rd, sa, fn = (wd >> 11) & 31, (wd >> 6) & 31, wd & 63
            nxt = None
            if op == 0:
                if fn == 0:
                    regs[rd] = (regs[rt] << sa) & 0xFFFFFFFF
                elif fn == 2:
                    regs[rd] = regs[rt] >> sa
                elif fn == 8:
                    nxt = ("jr", regs[rs])
                elif fn == 0x10:
                    regs[rd] = hi
                elif fn == 0x12:
                    regs[rd] = lo
                elif fn == 0x1A:
                    a, b = s32(regs[rs]), s32(regs[rt])
                    q = int(a / b)
                    lo, hi = q & 0xFFFFFFFF, (a - q * b) & 0xFFFFFFFF
                elif fn in (0x21, 0x23, 0x24, 0x25, 0x2A, 0x2B):
                    a, b = regs[rs], regs[rt]
                    regs[rd] = {
                        0x21: (a + b) & 0xFFFFFFFF,
                        0x23: (a - b) & 0xFFFFFFFF,
                        0x24: a & b,
                        0x25: a | b,
                        0x2A: int(s32(a) < s32(b)),
                        0x2B: int(a < b),
                    }[fn]
                else:
                    raise AssertionError(f"해석기 미지원 R {fn:#x}")
            elif op in (4, 5):
                a, b = regs[rs], regs[rt]
                take = (a == b) if op == 4 else (a != b)
                nxt = ("br", pc + 4 + (sx16(imm) << 2)) if take else ("no", 0)
            elif op in (2, 3):
                if op == 3:
                    regs[31] = pc + 8
                nxt = ("j", ((wd & 0x3FFFFFF) << 2) | (pc & 0xF0000000))
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
                elif op == 0xB:
                    regs[rt] = int(a < (sx16(imm) & 0xFFFFFFFF))
                else:
                    regs[rt] = int(s32(a) < sx16(imm))
            elif op in (0x20, 0x21, 0x23, 0x24, 0x25):
                a = (regs[rs] + sx16(imm)) & 0xFFFFFFFF
                if op == 0x23:
                    regs[rt] = self.r32(a)
                elif op in (0x21, 0x25):
                    v = self.r16(a)
                    regs[rt] = (sx16(v) if op == 0x21 else v) & 0xFFFFFFFF
                elif op == 0x20:
                    v = self.r8(a)
                    regs[rt] = (v - 0x100 if v & 0x80 else v) & 0xFFFFFFFF
                else:
                    regs[rt] = self.r8(a)
            elif op in (0x28, 0x29, 0x2B):
                a = (regs[rs] + sx16(imm)) & 0xFFFFFFFF
                if op == 0x28:
                    mem[a] = regs[rt] & 0xFF
                elif op == 0x29:
                    self.w16(a, regs[rt])
                else:
                    self.w32(a, regs[rt])
            else:
                raise AssertionError(f"해석기 미지원 op {op:#x}")
            regs[0] = 0
            return nxt

        while pc != RA_END:
            steps += 1
            assert steps < max_steps, "무한루프"
            res = step(self.prog[pc], pc)
            if res is None:
                pc += 4
                continue
            kind, tgt = res
            slot = self.prog[pc + 4]
            step(slot, pc + 4)
            if kind == "no":
                pc += 8
            else:
                pc = tgt if kind != "no" else pc + 8
        return steps
