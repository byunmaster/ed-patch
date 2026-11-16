"""작은 HuC6280 어셈블러 — 비모달 자막 런타임(`gwin_rt` 안 B)의 명령 표. 필요한 명령만, 피연산자는 숫자 · 라벨 · `라벨+N` · `<라벨`(하위) · `>라벨`(상위).

`gwin_rt.Mini` 가 이 표를 빌려 쓴다(간접 Y · 시프트/회전 · 블록 전송). 시험(`tools/tests/cpu65.py`)이 같은 표로 디코드해 실제로 돌려 본다.
"""

import re

OPC = {
    ("LDA", "imm"): 0xA9, ("LDA", "zp"): 0xA5, ("LDA", "abs"): 0xAD, ("LDA", "absx"): 0xBD, ("LDA", "absy"): 0xB9, ("LDA", "izpy"): 0xB1, ("LDA", "izp"): 0xB2,
    ("STA", "zp"): 0x85, ("STA", "abs"): 0x8D, ("STA", "absx"): 0x9D, ("STA", "absy"): 0x99, ("STA", "izpy"): 0x91, ("STA", "izp"): 0x92,
    ("LDX", "imm"): 0xA2, ("LDX", "zp"): 0xA6, ("LDX", "abs"): 0xAE, ("LDX", "absy"): 0xBE,
    ("LDY", "imm"): 0xA0, ("LDY", "zp"): 0xA4, ("LDY", "abs"): 0xAC, ("LDY", "absx"): 0xBC,
    ("STX", "zp"): 0x86, ("STX", "abs"): 0x8E, ("STY", "zp"): 0x84, ("STY", "abs"): 0x8C,
    ("STZ", "zp"): 0x64, ("STZ", "abs"): 0x9C, ("STZ", "absx"): 0x9E,
    ("ADC", "imm"): 0x69, ("ADC", "zp"): 0x65, ("ADC", "abs"): 0x6D, ("ADC", "absx"): 0x7D, ("ADC", "absy"): 0x79,
    ("SBC", "imm"): 0xE9, ("SBC", "zp"): 0xE5, ("SBC", "abs"): 0xED, ("SBC", "absx"): 0xFD, ("SBC", "absy"): 0xF9,
    ("AND", "imm"): 0x29, ("AND", "zp"): 0x25, ("AND", "abs"): 0x2D, ("AND", "absx"): 0x3D,
    ("ORA", "imm"): 0x09, ("ORA", "zp"): 0x05, ("ORA", "abs"): 0x0D, ("ORA", "absx"): 0x1D, ("ORA", "izpy"): 0x11,
    ("EOR", "imm"): 0x49, ("EOR", "zp"): 0x45, ("EOR", "abs"): 0x4D,
    ("CMP", "imm"): 0xC9, ("CMP", "zp"): 0xC5, ("CMP", "abs"): 0xCD, ("CMP", "absx"): 0xDD, ("CMP", "absy"): 0xD9, ("CMP", "izpy"): 0xD1,
    ("CPX", "imm"): 0xE0, ("CPX", "zp"): 0xE4, ("CPX", "abs"): 0xEC, ("CPY", "imm"): 0xC0, ("CPY", "zp"): 0xC4, ("CPY", "abs"): 0xCC,
    ("INC", "imp"): 0x1A, ("INC", "zp"): 0xE6, ("INC", "abs"): 0xEE, ("INC", "absx"): 0xFE,
    ("DEC", "imp"): 0x3A, ("DEC", "zp"): 0xC6, ("DEC", "abs"): 0xCE, ("DEC", "absx"): 0xDE,
    ("INX", "imp"): 0xE8, ("INY", "imp"): 0xC8, ("DEX", "imp"): 0xCA, ("DEY", "imp"): 0x88,
    ("ASL", "imp"): 0x0A, ("ASL", "zp"): 0x06, ("ASL", "abs"): 0x0E, ("LSR", "imp"): 0x4A, ("LSR", "zp"): 0x46, ("LSR", "abs"): 0x4E,
    ("ROL", "imp"): 0x2A, ("ROL", "zp"): 0x26, ("ROL", "abs"): 0x2E, ("ROR", "imp"): 0x6A, ("ROR", "zp"): 0x66, ("ROR", "abs"): 0x6E,
    ("BIT", "imm"): 0x89, ("BIT", "zp"): 0x24, ("BIT", "abs"): 0x2C,
    ("JMP", "abs"): 0x4C, ("JMP", "indx"): 0x7C, ("JSR", "abs"): 0x20, ("RTS", "imp"): 0x60,
    ("BCC", "rel"): 0x90, ("BCS", "rel"): 0xB0, ("BEQ", "rel"): 0xF0, ("BNE", "rel"): 0xD0, ("BMI", "rel"): 0x30, ("BPL", "rel"): 0x10, ("BRA", "rel"): 0x80,
    ("PHA", "imp"): 0x48, ("PLA", "imp"): 0x68, ("PHX", "imp"): 0xDA, ("PLX", "imp"): 0xFA, ("PHY", "imp"): 0x5A, ("PLY", "imp"): 0x7A, ("PHP", "imp"): 0x08, ("PLP", "imp"): 0x28,
    ("CLC", "imp"): 0x18, ("SEC", "imp"): 0x38, ("SEI", "imp"): 0x78, ("CLI", "imp"): 0x58,
    ("TAX", "imp"): 0xAA, ("TAY", "imp"): 0xA8, ("TXA", "imp"): 0x8A, ("TYA", "imp"): 0x98, ("TSX", "imp"): 0xBA,
    ("ST0", "imm"): 0x03, ("ST1", "imm"): 0x13, ("ST2", "imm"): 0x23, ("TMA", "mpr"): 0x43, ("TAM", "mpr"): 0x53,
    ("TII", "blk"): 0x73, ("TIA", "blk"): 0xE3, ("TAI", "blk"): 0xF3,
}
LEN = {"imp": 1, "imm": 2, "zp": 2, "izp": 2, "izpy": 2, "rel": 2, "mpr": 2, "abs": 3, "absx": 3, "absy": 3, "indx": 3, "blk": 7}


class AsmError(Exception):
    pass


class Asm:
    def __init__(self, org: int):
        self.org, self.out = org, bytearray()
        self.labels: dict[str, int] = {}
        self.fix: list[tuple[int, str, str]] = []

    @property
    def pc(self) -> int:
        return self.org + len(self.out)

    def L(self, name: str):
        assert name not in self.labels, name
        self.labels[name] = self.pc

    def _arg(self, arg, kind: str):
        if isinstance(arg, str):
            self.fix.append((len(self.out), arg, kind))
            self.out += b"\0\0" if kind == "abs" else b"\0"
        elif kind == "abs":
            self.out += (arg & 0xFFFF).to_bytes(2, "little")
        else:
            self.out.append(arg & 0xFF)

    def op(self, mn: str, mode: str = "imp", arg=None):
        if (mn, mode) not in OPC:
            raise AsmError(f"{mn} {mode}")
        self.out.append(OPC[(mn, mode)])
        if mode == "imp":
            return
        if mode in ("imm", "zp", "izp", "izpy"):
            self._arg(arg, "imm")
        elif mode == "mpr":
            self.out.append(1 << arg)
        elif mode == "rel":
            self.fix.append((len(self.out), arg, "rel"))
            self.out.append(0)
        elif mode == "blk":  # (원본, 목적지, 길이) — 주소 셋 16비트
            for a in arg:
                self._arg(a, "abs")
        else:
            self._arg(arg, "abs")

    def raw(self, b: bytes):
        self.out += b

    def word(self, label):
        self._arg(label, "abs")

    def val(self, expr: str) -> int:
        m = re.fullmatch(r"([<>]?)([A-Za-z_]\w*)([+-]\d+)?", expr)
        if not m:
            raise AsmError(f"피연산자 {expr!r}")
        v = self.labels[m.group(2)] + int(m.group(3) or 0)
        return v & 0xFF if m.group(1) == "<" else v >> 8 if m.group(1) == ">" else v

    def bytes(self) -> bytes:
        for pos, expr, kind in self.fix:
            if kind == "rel":
                d = self.val(expr) - (self.org + pos + 1)
                if not -128 <= d <= 127:
                    raise AsmError(f"분기 범위 {expr} {d}")
                self.out[pos] = d & 0xFF
            elif kind == "imm":
                self.out[pos] = self.val(expr) & 0xFF
            else:
                self.out[pos : pos + 2] = self.val(expr).to_bytes(2, "little")
        return bytes(self.out)
