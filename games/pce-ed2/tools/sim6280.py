"""HuC6280 부분집합 시뮬레이터 — `asm.py` 가 낼 수 있는 옵코드만. **후킹 루틴의 논리를 에뮬 없이 검증**한다.

(손인코딩 기계어는 디스어셈블로 검산한다 — 루트 CLAUDE.md. 이쪽은 의미 검증이고, 에뮬 디스어셈블이 바이트 검증이다.)
메모리 = 64KB 논리 공간 + MPR 8개(뱅크 → 8KB). `TMA/TAM` 으로 MPR 를 바꾸면 그 창이 바뀐다.
"""


class Sim:
    def __init__(self, banks: dict[int, bytes], mpr: list[int], zp_ram: bytearray):
        self.banks = {b: bytearray(v) for b, v in banks.items()}
        self.mpr = list(mpr)
        self.ram = zp_ram  # 8KB 작업 RAM(`$2000~$3FFF`) — MPR1 = 0xF8
        self.a = self.x = self.y = 0
        self.c = self.z = self.n = 0
        self.i = 0
        self.sp = 0xFF
        self.pc = 0
        self.log = []

    # --- 메모리
    def rd(self, addr: int) -> int:
        w = addr >> 13
        b = self.mpr[w]
        if b == 0xF8:
            return self.ram[addr & 0x1FFF]
        return self.banks.get(b, bytes(8192))[addr & 0x1FFF]

    def wr(self, addr: int, v: int) -> None:
        w = addr >> 13
        b = self.mpr[w]
        if b == 0xF8:
            self.ram[addr & 0x1FFF] = v & 0xFF
        else:
            self.banks.setdefault(b, bytearray(8192))[addr & 0x1FFF] = v & 0xFF

    def zp(self, a):  # 영 페이지 = 작업 RAM 맨 앞 `$2000~$20FF`
        return 0x2000 + a

    def push(self, v):
        self.wr(0x2100 + self.sp, v)
        self.sp = (self.sp - 1) & 0xFF

    def pull(self):
        self.sp = (self.sp + 1) & 0xFF
        return self.rd(0x2100 + self.sp)

    def nz(self, v):
        v &= 0xFF
        self.z = int(v == 0)
        self.n = v >> 7
        return v

    def fetch(self):
        v = self.rd(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def fetch16(self):
        lo = self.fetch()
        return lo | self.fetch() << 8

    def run(self, pc: int, until_ret_depth: int = 0, max_steps: int = 100000, base_sp: int | None = None):
        """`pc` 에서 시작해 최상위 RTS(스택이 처음 깊이로 돌아옴)까지. JMP 는 따라간다. 반환: 도달한 `JMP` 대상 또는 None."""
        self.pc = pc
        start_sp = self.sp if base_sp is None else base_sp  # JMP 를 따라 이어 돌 때는 처음 깊이를 유지한다
        for _ in range(max_steps):
            op = self.fetch()
            r = self.step(op, start_sp)
            if r is not None:
                return r
        raise RuntimeError("시뮬레이터가 안 끝난다")

    def step(self, op, start_sp):
        zp = lambda: self.zp(self.fetch())
        if op == 0xA5:
            self.a = self.nz(self.rd(zp()))
        elif op == 0xA9:
            self.a = self.nz(self.fetch())
        elif op == 0xAD:
            self.a = self.nz(self.rd(self.fetch16()))
        elif op == 0xBD:
            self.a = self.nz(self.rd(self.fetch16() + self.x))
        elif op == 0xB9:
            self.a = self.nz(self.rd(self.fetch16() + self.y))
        elif op == 0xB1:
            p = self.zp(self.fetch())
            base = self.rd(p) | self.rd(p + 1) << 8
            self.a = self.nz(self.rd(base + self.y))
        elif op == 0x85:
            self.wr(zp(), self.a)
        elif op == 0x8D:
            self.wr(self.fetch16(), self.a)
        elif op == 0x8E:  # STX abs
            self.wr(self.fetch16(), self.x)
        elif op == 0x86:  # STX zp
            self.wr(zp(), self.x)
        elif op == 0x9D:
            self.wr(self.fetch16() + self.x, self.a)
        elif op == 0x99:
            self.wr(self.fetch16() + self.y, self.a)
        elif op == 0x64:
            self.wr(zp(), 0)
        elif op == 0x9C:  # STZ abs
            self.wr(self.fetch16(), 0)
        elif op == 0xA6:  # LDX zp
            self.x = self.nz(self.rd(zp()))
        elif op == 0xA2:
            self.x = self.nz(self.fetch())
        elif op == 0xA0:
            self.y = self.nz(self.fetch())
        elif op == 0xC9:
            self.cmp(self.a, self.fetch())
        elif op == 0xC5:
            self.cmp(self.a, self.rd(zp()))
        elif op == 0xDD:
            self.cmp(self.a, self.rd(self.fetch16() + self.x))
        elif op == 0xCD:
            self.cmp(self.a, self.rd(self.fetch16()))
        elif op == 0x6D:
            self.adc(self.rd(self.fetch16()))
        elif op == 0xED:
            self.adc(self.rd(self.fetch16()) ^ 0xFF)
        elif op == 0x0D:
            self.a = self.nz(self.a | self.rd(self.fetch16()))
        elif op == 0xE0:
            self.cmp(self.x, self.fetch())
        elif op == 0xC0:
            self.cmp(self.y, self.fetch())
        elif op == 0x69:
            self.adc(self.fetch())
        elif op == 0x65:
            self.adc(self.rd(zp()))
        elif op == 0x7D:
            self.adc(self.rd(self.fetch16() + self.x))
        elif op == 0xE9:
            self.adc(self.fetch() ^ 0xFF)
        elif op == 0xE5:
            self.adc(self.rd(zp()) ^ 0xFF)
        elif op == 0xFD:
            self.adc(self.rd(self.fetch16() + self.x) ^ 0xFF)
        elif op == 0x29:
            self.a = self.nz(self.a & self.fetch())
        elif op == 0x09:
            self.a = self.nz(self.a | self.fetch())
        elif op == 0x05:
            self.a = self.nz(self.a | self.rd(zp()))
        elif op == 0x0A:
            self.c = self.a >> 7
            self.a = self.nz(self.a << 1)
        elif op == 0x4A:
            self.c = self.a & 1
            self.a = self.nz(self.a >> 1)
        elif op == 0x06:
            p = zp()
            v = self.rd(p)
            self.c = v >> 7
            self.wr(p, self.nz(v << 1))
        elif op == 0x26:
            p = zp()
            v = self.rd(p)
            c = self.c
            self.c = v >> 7
            self.wr(p, self.nz((v << 1) | c))
        elif op == 0x1E:  # ASL abs,X
            p = self.fetch16() + self.x
            v = self.rd(p)
            self.c = v >> 7
            self.wr(p, self.nz(v << 1))
        elif op == 0x3E:  # ROL abs,X
            p = self.fetch16() + self.x
            v = self.rd(p)
            c = self.c
            self.c = v >> 7
            self.wr(p, self.nz((v << 1) | c))
        elif op == 0x62:  # CLA
            self.a = 0
        elif op == 0x3A:  # DEC A
            self.a = self.nz(self.a - 1)
        elif op == 0xBA:  # TSX
            self.x = self.nz(self.sp)
        elif op == 0xE6:
            p = zp()
            self.wr(p, self.nz(self.rd(p) + 1))
        elif op == 0xE8:
            self.x = self.nz(self.x + 1)
        elif op == 0xCA:
            self.x = self.nz(self.x - 1)
        elif op == 0xC8:
            self.y = self.nz(self.y + 1)
        elif op == 0x88:
            self.y = self.nz(self.y - 1)
        elif op == 0xAA:
            self.x = self.nz(self.a)
        elif op == 0xA8:
            self.y = self.nz(self.a)
        elif op == 0x8A:
            self.a = self.nz(self.x)
        elif op == 0x98:
            self.a = self.nz(self.y)
        elif op == 0x48:
            self.push(self.a)
        elif op == 0x68:
            self.a = self.nz(self.pull())
        elif op == 0xDA:
            self.push(self.x)
        elif op == 0xFA:
            self.x = self.nz(self.pull())
        elif op == 0x08:
            self.push(self.c | self.z << 1 | self.i << 2 | self.n << 7)
        elif op == 0x28:
            p = self.pull()
            self.c = p & 1
            self.z = p >> 1 & 1
            self.i = p >> 2 & 1
            self.n = p >> 7
        elif op == 0x38:
            self.c = 1
        elif op == 0x18:
            self.c = 0
        elif op == 0x78:
            self.i = 1
        elif op == 0x58:
            self.i = 0
        elif op in (0x90, 0xB0, 0xF0, 0xD0, 0x30, 0x10, 0x80):
            d = self.fetch()
            d = d - 256 if d > 127 else d
            take = {
                0x90: not self.c,
                0xB0: self.c,
                0xF0: self.z,
                0xD0: not self.z,
                0x30: self.n,
                0x10: not self.n,
                0x80: True,
            }[op]
            if take:
                self.pc = (self.pc + d) & 0xFFFF
        elif op == 0x20:  # JSR
            t = self.fetch16()
            ret = (self.pc - 1) & 0xFFFF
            self.push(ret >> 8)
            self.push(ret & 0xFF)
            self.pc = t
        elif op == 0xB2:  # LDA (zp)
            p = zp()
            self.a = self.nz(self.rd(self.rd(p) | self.rd(p + 1) << 8))
        elif op == 0x92:  # STA (zp)
            p = zp()
            self.wr(self.rd(p) | self.rd(p + 1) << 8, self.a)
        elif op == 0x1A:  # INC A
            self.a = self.nz(self.a + 1)
        elif op == 0xEE:  # INC abs
            p = self.fetch16()
            self.wr(p, self.nz(self.rd(p) + 1))
        elif op == 0xCE:  # DEC abs
            p = self.fetch16()
            self.wr(p, self.nz(self.rd(p) - 1))
        elif op == 0x49:  # EOR #imm
            self.a = self.nz(self.a ^ self.fetch())
        elif op == 0x46:  # LSR zp
            p = zp()
            v = self.rd(p)
            self.c = v & 1
            self.wr(p, self.nz(v >> 1))
        elif op == 0x66:  # ROR zp
            p = zp()
            v = self.rd(p)
            c = self.c
            self.c = v & 1
            self.wr(p, self.nz((v >> 1) | c << 7))
        elif op == 0x82:  # CLX
            self.x = 0
        elif op == 0xFE:  # INC abs,X
            p = self.fetch16() + self.x
            self.wr(p, self.nz(self.rd(p) + 1))
        elif op == 0x4C:
            return self.fetch16()
        elif op == 0x60:
            if self.sp == start_sp:
                return -1
            lo = self.pull()
            hi = self.pull()
            self.pc = (lo | hi << 8) + 1
        elif op == 0x43:  # TMA
            m = self.fetch()
            self.a = self.mpr[m.bit_length() - 1]
        elif op == 0x53:  # TAM
            m = self.fetch()
            self.mpr[m.bit_length() - 1] = self.a
        else:
            raise NotImplementedError(f"옵코드 {op:02X} @ {self.pc - 1:04X}")

    def cmp(self, r, v):
        self.c = int(r >= v)
        self.nz(r - v)

    def adc(self, v):
        t = self.a + v + self.c
        self.c = int(t > 0xFF)
        self.a = self.nz(t)
