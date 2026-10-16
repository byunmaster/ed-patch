"""HuC6280 디스어셈블러(읽기용) — 디스크 이미지의 코드를 에뮬 없이 읽는다. 에뮬 `disassemble` 와 같은 꼴을 낸다.

모드: imp · imm · zp · zpx · zpy · abs · absx · absy · ind · indx · indy · zpind · absindx · rel · zprel(BBR/BBS) ·
tst(TST #imm,zp/abs[,x]) · blk(TII 따위 3워드) · imm_zp(ST0 따위는 imm).
"""

OPS: dict[int, tuple[str, str]] = {}


def _def(mn, modes):
    for op, mode in modes.items():
        OPS[op] = (mn, mode)


# 65C02 기본
_def(
    "ADC",
    {
        0x69: "imm",
        0x65: "zp",
        0x75: "zpx",
        0x6D: "abs",
        0x7D: "absx",
        0x79: "absy",
        0x61: "indx",
        0x71: "indy",
        0x72: "zpind",
    },
)
_def(
    "AND",
    {
        0x29: "imm",
        0x25: "zp",
        0x35: "zpx",
        0x2D: "abs",
        0x3D: "absx",
        0x39: "absy",
        0x21: "indx",
        0x31: "indy",
        0x32: "zpind",
    },
)
_def("ASL", {0x0A: "imp", 0x06: "zp", 0x16: "zpx", 0x0E: "abs", 0x1E: "absx"})
_def("BIT", {0x89: "imm", 0x24: "zp", 0x34: "zpx", 0x2C: "abs", 0x3C: "absx"})
_def(
    "CMP",
    {
        0xC9: "imm",
        0xC5: "zp",
        0xD5: "zpx",
        0xCD: "abs",
        0xDD: "absx",
        0xD9: "absy",
        0xC1: "indx",
        0xD1: "indy",
        0xD2: "zpind",
    },
)
_def("CPX", {0xE0: "imm", 0xE4: "zp", 0xEC: "abs"})
_def("CPY", {0xC0: "imm", 0xC4: "zp", 0xCC: "abs"})
_def("DEC", {0x3A: "imp", 0xC6: "zp", 0xD6: "zpx", 0xCE: "abs", 0xDE: "absx"})
_def(
    "EOR",
    {
        0x49: "imm",
        0x45: "zp",
        0x55: "zpx",
        0x4D: "abs",
        0x5D: "absx",
        0x59: "absy",
        0x41: "indx",
        0x51: "indy",
        0x52: "zpind",
    },
)
_def("INC", {0x1A: "imp", 0xE6: "zp", 0xF6: "zpx", 0xEE: "abs", 0xFE: "absx"})
_def("JMP", {0x4C: "abs", 0x6C: "ind", 0x7C: "absindx"})
_def("JSR", {0x20: "abs"})
_def(
    "LDA",
    {
        0xA9: "imm",
        0xA5: "zp",
        0xB5: "zpx",
        0xAD: "abs",
        0xBD: "absx",
        0xB9: "absy",
        0xA1: "indx",
        0xB1: "indy",
        0xB2: "zpind",
    },
)
_def("LDX", {0xA2: "imm", 0xA6: "zp", 0xB6: "zpy", 0xAE: "abs", 0xBE: "absy"})
_def("LDY", {0xA0: "imm", 0xA4: "zp", 0xB4: "zpx", 0xAC: "abs", 0xBC: "absx"})
_def("LSR", {0x4A: "imp", 0x46: "zp", 0x56: "zpx", 0x4E: "abs", 0x5E: "absx"})
_def(
    "ORA",
    {
        0x09: "imm",
        0x05: "zp",
        0x15: "zpx",
        0x0D: "abs",
        0x1D: "absx",
        0x19: "absy",
        0x01: "indx",
        0x11: "indy",
        0x12: "zpind",
    },
)
_def("ROL", {0x2A: "imp", 0x26: "zp", 0x36: "zpx", 0x2E: "abs", 0x3E: "absx"})
_def("ROR", {0x6A: "imp", 0x66: "zp", 0x76: "zpx", 0x6E: "abs", 0x7E: "absx"})
_def(
    "SBC",
    {
        0xE9: "imm",
        0xE5: "zp",
        0xF5: "zpx",
        0xED: "abs",
        0xFD: "absx",
        0xF9: "absy",
        0xE1: "indx",
        0xF1: "indy",
        0xF2: "zpind",
    },
)
_def(
    "STA",
    {
        0x85: "zp",
        0x95: "zpx",
        0x8D: "abs",
        0x9D: "absx",
        0x99: "absy",
        0x81: "indx",
        0x91: "indy",
        0x92: "zpind",
    },
)
_def("STX", {0x86: "zp", 0x96: "zpy", 0x8E: "abs"})
_def("STY", {0x84: "zp", 0x94: "zpx", 0x8C: "abs"})
_def("STZ", {0x64: "zp", 0x74: "zpx", 0x9C: "abs", 0x9E: "absx"})
_def("TRB", {0x14: "zp", 0x1C: "abs"})
_def("TSB", {0x04: "zp", 0x0C: "abs"})
for mn, op in (
    ("BCC", 0x90),
    ("BCS", 0xB0),
    ("BEQ", 0xF0),
    ("BNE", 0xD0),
    ("BMI", 0x30),
    ("BPL", 0x10),
    ("BVC", 0x50),
    ("BVS", 0x70),
    ("BRA", 0x80),
    ("BSR", 0x44),
):
    OPS[op] = (mn, "rel")
for mn, op in (
    ("BRK", 0x00),
    ("CLC", 0x18),
    ("CLD", 0xD8),
    ("CLI", 0x58),
    ("CLV", 0xB8),
    ("DEX", 0xCA),
    ("DEY", 0x88),
    ("INX", 0xE8),
    ("INY", 0xC8),
    ("NOP", 0xEA),
    ("PHA", 0x48),
    ("PHP", 0x08),
    ("PHX", 0xDA),
    ("PHY", 0x5A),
    ("PLA", 0x68),
    ("PLP", 0x28),
    ("PLX", 0xFA),
    ("PLY", 0x7A),
    ("RTI", 0x40),
    ("RTS", 0x60),
    ("SEC", 0x38),
    ("SED", 0xF8),
    ("SEI", 0x78),
    ("TAX", 0xAA),
    ("TAY", 0xA8),
    ("TSX", 0xBA),
    ("TXA", 0x8A),
    ("TXS", 0x9A),
    ("TYA", 0x98),
    ("CLA", 0x62),
    ("CLX", 0x82),
    ("CLY", 0xC2),
    ("CSH", 0xD4),
    ("CSL", 0x54),
    ("SAX", 0x22),
    ("SAY", 0x42),
    ("SXY", 0x02),
    ("SET", 0xF4),
):
    OPS[op] = (mn, "imp")
for i in range(8):
    OPS[0x07 + 0x10 * i] = (f"RMB{i}", "zp")
    OPS[0x87 + 0x10 * i] = (f"SMB{i}", "zp")
    OPS[0x0F + 0x10 * i] = (f"BBR{i}", "zprel")
    OPS[0x8F + 0x10 * i] = (f"BBS{i}", "zprel")
for op, mn in ((0x03, "ST0"), (0x13, "ST1"), (0x23, "ST2"), (0x43, "TMA"), (0x53, "TAM")):
    OPS[op] = (mn, "imm")
for op, mn in ((0x73, "TII"), (0xC3, "TDD"), (0xD3, "TIN"), (0xE3, "TIA"), (0xF3, "TAI")):
    OPS[op] = (mn, "blk")
OPS.update(
    {
        0x83: ("TST", "tstzp"),
        0xA3: ("TST", "tstzpx"),
        0x93: ("TST", "tstabs"),
        0xB3: ("TST", "tstabsx"),
    }
)

SIZE = {
    "imp": 1,
    "imm": 2,
    "zp": 2,
    "zpx": 2,
    "zpy": 2,
    "abs": 3,
    "absx": 3,
    "absy": 3,
    "ind": 3,
    "indx": 2,
    "indy": 2,
    "zpind": 2,
    "absindx": 3,
    "rel": 2,
    "zprel": 3,
    "blk": 7,
    "tstzp": 3,
    "tstzpx": 3,
    "tstabs": 4,
    "tstabsx": 4,
}


def decode(code: bytes, pc: int):
    """한 명령 → (텍스트, 길이)."""
    op = code[0]
    if op not in OPS:
        return f".db ${op:02X}", 1
    mn, mode = OPS[op]
    n = SIZE[mode]
    b = code[:n]
    if len(b) < n:
        return f".db ${op:02X}", 1
    w = lambda i: b[i] | b[i + 1] << 8
    if mode == "imp":
        t = mn
    elif mode == "imm":
        t = f"{mn} #${b[1]:02X}"
    elif mode == "zp":
        t = f"{mn} ${b[1]:02X}"
    elif mode == "zpx":
        t = f"{mn} ${b[1]:02X},X"
    elif mode == "zpy":
        t = f"{mn} ${b[1]:02X},Y"
    elif mode == "abs":
        t = f"{mn} ${w(1):04X}"
    elif mode == "absx":
        t = f"{mn} ${w(1):04X},X"
    elif mode == "absy":
        t = f"{mn} ${w(1):04X},Y"
    elif mode == "ind":
        t = f"{mn} (${w(1):04X})"
    elif mode == "indx":
        t = f"{mn} (${b[1]:02X},X)"
    elif mode == "indy":
        t = f"{mn} (${b[1]:02X}),Y"
    elif mode == "zpind":
        t = f"{mn} (${b[1]:02X})"
    elif mode == "absindx":
        t = f"{mn} (${w(1):04X},X)"
    elif mode == "rel":
        d = b[1] - 256 if b[1] > 127 else b[1]
        t = f"{mn} ${(pc + 2 + d) & 0xFFFF:04X}"
    elif mode == "zprel":
        d = b[2] - 256 if b[2] > 127 else b[2]
        t = f"{mn} ${b[1]:02X},${(pc + 3 + d) & 0xFFFF:04X}"
    elif mode == "blk":
        t = f"{mn} ${w(1):04X},${w(3):04X},${w(5):04X}"
    elif mode.startswith("tstzp"):
        t = f"{mn} #${b[1]:02X},${b[2]:02X}" + (",X" if mode.endswith("x") else "")
    else:
        t = f"{mn} #${b[1]:02X},${w(2):04X}" + (",X" if mode.endswith("x") else "")
    return t, n


def disasm(data: bytes, org: int, start: int = 0, count: int = 64) -> list[str]:
    out = []
    i = start
    while i < len(data) and len(out) < count:
        t, n = decode(data[i : i + 7], org + i)
        out.append(f"{org + i:04X}  {data[i : i + n].hex(' '):<12} {t}")
        i += n
    return out
