"""미니 HuC6280 어셈블러 — 손인코딩 오타를 막는다(pce-ed1 `hook.py` 의 `Asm` 에서 옮겼다 — 필요한 옵코드만).

사용: `a = Asm(org)`; `a.op("LDA", "zp", 0xF9)`; `a.label("x")`; `a.op("BCC", "rel", "x")`; `a.bytes()`.
모드: imp · imm · zp · abs · absx · absy · izpy · rel · tma · tam. 분기는 -128~127 안이어야 한다(아니면 단언).
"""

OPS = {
    ("LDA", "zp"): 0xA5,
    ("LDA", "imm"): 0xA9,
    ("LDA", "abs"): 0xAD,
    ("LDA", "absx"): 0xBD,
    ("LDA", "absy"): 0xB9,
    ("STA", "absx"): 0x9D,
    ("CMP", "absx"): 0xDD,
    ("ADC", "absx"): 0x7D,
    ("SBC", "absx"): 0xFD,
    ("ORA", "zp"): 0x05,
    ("CPX", "zp"): 0xE4,
    ("CPY", "zp"): 0xC4,
    ("LDA", "izpy"): 0xB1,
    ("STA", "zp"): 0x85,
    ("STA", "abs"): 0x8D,
    ("STA", "absy"): 0x99,
    ("STA", "izpy"): 0x91,
    ("STZ", "zp"): 0x64,
    ("STZ", "abs"): 0x9C,
    ("LDX", "imm"): 0xA2,
    ("LDX", "zp"): 0xA6,
    ("LDY", "imm"): 0xA0,
    ("LDY", "zp"): 0xA4,
    ("STX", "zp"): 0x86,
    ("STY", "zp"): 0x84,
    ("CMP", "imm"): 0xC9,
    ("CMP", "zp"): 0xC5,
    ("CPY", "imm"): 0xC0,
    ("CPX", "imm"): 0xE0,
    ("ADC", "imm"): 0x69,
    ("ADC", "zp"): 0x65,
    ("SBC", "imm"): 0xE9,
    ("SBC", "zp"): 0xE5,
    ("AND", "imm"): 0x29,
    ("AND", "zp"): 0x25,
    ("ORA", "imm"): 0x09,
    ("EOR", "imm"): 0x49,
    ("ASL", "imp"): 0x0A,
    ("ASL", "zp"): 0x06,
    ("LSR", "imp"): 0x4A,
    ("LSR", "zp"): 0x46,
    ("ROL", "imp"): 0x2A,
    ("ROL", "zp"): 0x26,
    ("ROR", "imp"): 0x6A,
    ("ROR", "zp"): 0x66,
    ("INC", "imp"): 0x1A,
    ("INC", "zp"): 0xE6,
    ("DEC", "imp"): 0x3A,
    ("DEC", "zp"): 0xC6,
    ("INX", "imp"): 0xE8,
    ("DEX", "imp"): 0xCA,
    ("INY", "imp"): 0xC8,
    ("DEY", "imp"): 0x88,
    ("TAX", "imp"): 0xAA,
    ("TAY", "imp"): 0xA8,
    ("TXA", "imp"): 0x8A,
    ("TYA", "imp"): 0x98,
    ("PHA", "imp"): 0x48,
    ("PLA", "imp"): 0x68,
    ("PHX", "imp"): 0xDA,
    ("PLX", "imp"): 0xFA,
    ("PHY", "imp"): 0x5A,
    ("PLY", "imp"): 0x7A,
    ("PHP", "imp"): 0x08,
    ("PLP", "imp"): 0x28,
    ("CLA", "imp"): 0x62,
    ("CLX", "imp"): 0x82,
    ("CLY", "imp"): 0xC2,
    ("SEC", "imp"): 0x38,
    ("CLC", "imp"): 0x18,
    ("SEI", "imp"): 0x78,
    ("CLI", "imp"): 0x58,
    ("BCC", "rel"): 0x90,
    ("BCS", "rel"): 0xB0,
    ("BEQ", "rel"): 0xF0,
    ("BNE", "rel"): 0xD0,
    ("BMI", "rel"): 0x30,
    ("BPL", "rel"): 0x10,
    ("BRA", "rel"): 0x80,
    ("JMP", "abs"): 0x4C,
    ("JSR", "abs"): 0x20,
    ("RTS", "imp"): 0x60,
    ("TMA", "tma"): 0x43,
    ("TAM", "tam"): 0x53,
}


class Asm:
    def __init__(self, org: int):
        self.org = org
        self.out = bytearray()
        self.labels: dict[str, int] = {}
        self.fix: list[tuple[int, str, str]] = []

    @property
    def pc(self) -> int:
        return self.org + len(self.out)

    def label(self, name: str) -> None:
        self.labels[name] = self.pc

    def op(self, mn: str, mode: str = "imp", arg=None) -> None:
        self.out.append(OPS[(mn, mode)])
        if mode == "imp":
            return
        if mode in ("imm", "zp", "izpy"):
            self.out.append(arg & 0xFF)
        elif mode in ("tma", "tam"):
            self.out.append(1 << arg)  # MPR 번호 → 비트
        elif mode == "rel":
            self.fix.append((len(self.out), arg, "rel"))
            self.out.append(0)
        elif mode in ("abs", "absx", "absy"):
            if isinstance(arg, str):
                self.fix.append((len(self.out), arg, "abs"))
                self.out += b"\0\0"
            else:
                self.out += arg.to_bytes(2, "little")

    def data(self, b: bytes) -> None:
        self.out += b

    def bytes(self) -> bytes:
        for pos, lab, kind in self.fix:
            tgt = self.labels[lab]
            if kind == "rel":
                d = tgt - (self.org + pos + 1)
                assert -128 <= d <= 127, (lab, d)
                self.out[pos] = d & 0xFF
            else:
                self.out[pos : pos + 2] = tgt.to_bytes(2, "little")
        return bytes(self.out)
