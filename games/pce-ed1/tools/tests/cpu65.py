"""HuC6280 부분집합 시뮬레이터 — `asm65` 가 내는 명령만. 비모달 자막 렌더러(`gwin_rt` 안 B)를 파이썬 참조 구현과 바이트로 대조하려고 돌린다.
메모리는 평평한 64KB, MPR 은 `TAM` 때 뱅크 이미지를 창에 복사하는 식으로 흉내 낸다. VDC 는 포트 $0000~$0003(선택·데이터)과 ST0/ST1/ST2 를 받아 VRAM(32K 단어)에 쓴다."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asm65

DEC = {v: k for k, v in asm65.OPC.items()}
DEC.update({0x82: ("CLX", "imp"), 0x62: ("CLA", "imp"), 0xC2: ("CLY", "imp"), 0x22: ("SAX", "imp"), 0xEA: ("NOP", "imp")})  # 어셈블러 표엔 없지만 원판 루틴(곱셈 `$5962` 등)을 그대로 돌릴 때 만난다


class CPU:
    def __init__(self, mem: bytearray, banks: dict[int, bytes] | None = None):
        self.m = mem
        self.banks = banks or {}
        self.mpr = [0] * 8
        self.a = self.x = self.y = 0
        self.c = self.z = self.n = self.i = 0
        self.sp = 0xFF
        self.pc = 0
        self.vram = [0] * 0x8000
        self.sel = 0
        self.mawr = self.marr = 0
        self.vlo = 0
        self.steps = 0

    # ── 메모리 ──
    def rd(self, a: int) -> int:
        a &= 0xFFFF
        if a in (0x0002, 0x0003) and self.sel == 2:  # VRR 읽기 — 상위를 읽으면 MARR 가 는다(훑기의 TAI 가 이 길로 BAT 행을 읽는다)
            w = self.vram[self.marr & 0x7FFF]
            if a == 0x0002:
                return w & 0xFF
            self.marr += 1
            return w >> 8
        return self.m[a]

    def wr(self, a: int, v: int):
        a &= 0xFFFF
        v &= 0xFF
        if a == 0x0000:  # 레지스터 선택(`ST0` 과 같은 일 — `STA $0000`)
            self.sel = v
            return
        if a == 0x0002 or a == 0x0003:
            if self.sel == 2:
                if a == 0x0002:
                    self.vlo = v
                else:
                    self.vram[self.mawr & 0x7FFF] = self.vlo | v << 8
                    self.mawr += 1
            elif a == 0x0002:
                self.vlo = v
            else:
                val = self.vlo | v << 8
                if self.sel == 0:
                    self.mawr = val
                elif self.sel == 1:
                    self.marr = val
            return
        self.m[a] = v

    def push(self, v):
        self.m[0x2100 + self.sp] = v & 0xFF
        self.sp = (self.sp - 1) & 0xFF

    def pull(self):
        self.sp = (self.sp + 1) & 0xFF
        return self.m[0x2100 + self.sp]

    def nz(self, v):
        v &= 0xFF
        self.z, self.n = int(v == 0), v >> 7
        return v

    def fetch(self):
        v = self.m[self.pc]
        self.pc += 1
        return v

    def fetch2(self):
        v = self.m[self.pc] | self.m[self.pc + 1] << 8
        self.pc += 2
        return v

    def ea(self, mode):
        if mode == "zp":
            return self.fetch()
        if mode == "abs":
            return self.fetch2()
        if mode == "absx":
            return (self.fetch2() + self.x) & 0xFFFF
        if mode == "absy":
            return (self.fetch2() + self.y) & 0xFFFF
        if mode == "izpy":
            zp = self.fetch()
            return ((self.m[zp] | self.m[zp + 1] << 8) + self.y) & 0xFFFF
        if mode == "izp":
            zp = self.fetch()
            return self.m[zp] | self.m[zp + 1] << 8
        raise KeyError(mode)

    def val(self, mode):
        if mode == "imm":
            return self.fetch()
        return self.rd(self.ea(mode))

    def adc(self, v, sub=False):
        if sub:
            r = self.a - v - (1 - self.c)
            self.c = int(r >= 0)
        else:
            r = self.a + v + self.c
            self.c = int(r > 0xFF)
        self.a = self.nz(r)

    def cmp(self, r, v):
        self.c = int(r >= v)
        self.nz(r - v)

    def run(self, entry: int, ret: int = 0xFFFF, limit: int = 3_000_000) -> int:
        """`JSR entry` 를 흉내 내고 그 RTS 까지 돈다. 돌린 명령 수를 돌려준다."""
        self.push((ret - 1) >> 8)
        self.push((ret - 1) & 0xFF)
        self.pc = entry
        n = 0
        while self.pc != ret:
            self.step()
            n += 1
            if n > limit:
                raise RuntimeError(f"무한 루프? pc={self.pc:#06x}")
        return n

    def step(self):
        pc0 = self.pc
        op = self.fetch()
        key = DEC.get(op)
        if key is None:
            raise RuntimeError(f"모르는 옵코드 {op:#04x} @ {pc0:#06x}")
        mn, mode = key
        if mn == "LDA":
            self.a = self.nz(self.val(mode))
        elif mn == "LDX":
            self.x = self.nz(self.val(mode))
        elif mn == "LDY":
            self.y = self.nz(self.val(mode))
        elif mn == "STA":
            self.wr(self.ea(mode), self.a)
        elif mn == "STX":
            self.wr(self.ea(mode), self.x)
        elif mn == "STY":
            self.wr(self.ea(mode), self.y)
        elif mn == "STZ":
            self.wr(self.ea(mode), 0)
        elif mn == "CLA":  # HuC6280 — 플래그를 안 건드린다
            self.a = 0
        elif mn == "CLX":
            self.x = 0
        elif mn == "CLY":
            self.y = 0
        elif mn == "ADC":
            self.adc(self.val(mode))
        elif mn == "SBC":
            self.adc(self.val(mode), True)
        elif mn == "AND":
            self.a = self.nz(self.a & self.val(mode))
        elif mn == "ORA":
            self.a = self.nz(self.a | self.val(mode))
        elif mn == "EOR":
            self.a = self.nz(self.a ^ self.val(mode))
        elif mn == "CMP":
            self.cmp(self.a, self.val(mode))
        elif mn == "CPX":
            self.cmp(self.x, self.val(mode))
        elif mn == "CPY":
            self.cmp(self.y, self.val(mode))
        elif mn == "BIT":
            v = self.val(mode)
            self.z = int((self.a & v) == 0)
            if mode != "imm":
                self.n = v >> 7
        elif mn in ("INC", "DEC"):
            d = 1 if mn == "INC" else -1
            if mode == "imp":
                self.a = self.nz(self.a + d)
            else:
                e = self.ea(mode)
                self.wr(e, self.nz(self.rd(e) + d))
        elif mn == "INX":
            self.x = self.nz(self.x + 1)
        elif mn == "INY":
            self.y = self.nz(self.y + 1)
        elif mn == "DEX":
            self.x = self.nz(self.x - 1)
        elif mn == "DEY":
            self.y = self.nz(self.y - 1)
        elif mn in ("ASL", "LSR", "ROL", "ROR"):
            if mode == "imp":
                v = self.a
            else:
                e = self.ea(mode)
                v = self.rd(e)
            if mn == "ASL":
                self.c, r = v >> 7, v << 1
            elif mn == "LSR":
                self.c, r = v & 1, v >> 1
            elif mn == "ROL":
                c = self.c
                self.c, r = v >> 7, (v << 1) | c
            else:
                c = self.c
                self.c, r = v & 1, (v >> 1) | (c << 7)
            r = self.nz(r)
            if mode == "imp":
                self.a = r
            else:
                self.wr(e, r)
        elif mn == "JMP":
            t = self.fetch2()
            if mode == "indx":
                t = (t + self.x) & 0xFFFF
                t = self.m[t] | self.m[(t + 1) & 0xFFFF] << 8
            self.pc = t
        elif mn == "JSR":
            t = self.fetch2()
            self.push((self.pc - 1) >> 8)
            self.push((self.pc - 1) & 0xFF)
            self.pc = t
        elif mn == "RTS":
            lo = self.pull()
            hi = self.pull()
            self.pc = (lo | hi << 8) + 1
        elif mn in ("BCC", "BCS", "BEQ", "BNE", "BMI", "BPL", "BRA"):
            d = self.fetch()
            t = {"BCC": not self.c, "BCS": self.c, "BEQ": self.z, "BNE": not self.z, "BMI": self.n, "BPL": not self.n, "BRA": True}[mn]
            if t:
                self.pc += d - 256 if d > 127 else d
        elif mn == "PHA":
            self.push(self.a)
        elif mn == "PLA":
            self.a = self.nz(self.pull())
        elif mn == "PHX":
            self.push(self.x)
        elif mn == "PLX":
            self.x = self.nz(self.pull())
        elif mn == "PHY":
            self.push(self.y)
        elif mn == "PLY":
            self.y = self.nz(self.pull())
        elif mn == "PHP":
            self.push(self.c | self.z << 1 | self.i << 2 | self.n << 7)
        elif mn == "PLP":
            f = self.pull()
            self.c, self.z, self.i, self.n = f & 1, f >> 1 & 1, f >> 2 & 1, f >> 7
        elif mn == "CLC":
            self.c = 0
        elif mn == "SEC":
            self.c = 1
        elif mn == "SEI":
            self.i = 1
        elif mn == "CLI":
            self.i = 0
        elif mn == "TAX":
            self.x = self.nz(self.a)
        elif mn == "TAY":
            self.y = self.nz(self.a)
        elif mn == "TXA":
            self.a = self.nz(self.x)
        elif mn == "TYA":
            self.a = self.nz(self.y)
        elif mn == "TSX":
            self.x = self.nz(self.sp)
        elif mn == "CLA":
            self.a = 0  # 깃발은 안 건드린다
        elif mn == "CLY":
            self.y = 0
        elif mn == "SAX":
            self.a, self.x = self.x, self.a
        elif mn == "NOP":
            pass
        elif mn == "ST0":
            self.sel = self.fetch()
        elif mn == "ST1":
            self.wr(0x0002, self.fetch())
        elif mn == "ST2":
            self.wr(0x0003, self.fetch())
        elif mn == "TMA":
            mask = self.fetch()
            self.a = self.mpr[mask.bit_length() - 1]
        elif mn == "TAM":
            mask = self.fetch()
            k = mask.bit_length() - 1
            self.mpr[k] = self.a
            img = self.banks.get(self.a)
            if img is not None:
                self.m[k * 0x2000 : k * 0x2000 + 0x2000] = img.ljust(0x2000, b"\0")
        elif mn in ("TII", "TIA", "TAI"):
            s, d, n = self.fetch2(), self.fetch2(), self.fetch2()
            n = n or 0x10000
            for k in range(n):
                if mn == "TII":
                    self.wr(d + k, self.rd(s + k))
                elif mn == "TIA":
                    self.wr(d + (k & 1), self.rd(s + k))
                else:
                    self.wr(d + k, self.rd(s + (k & 1)))
        else:
            raise RuntimeError(f"미구현 {mn} {mode}")
