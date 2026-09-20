"""sfc-ed1 65816 디스어셈블러 — **조사용**(빌드 경로가 아니다).

이 게임은 실기 디버거를 늦게 얻었고, 실제로 막힌 자리를 푼 것은 **롬을 펴 읽은 것**이었다
(2026-09-08 저장 소프트락: 메시지 번호 → 표 선택 → 종료 코드 의미가 전부 정적으로 나왔다).
`tools/asm65816.py` 가 **쓰는** 쪽이면 이건 **읽는** 쪽이다.

⚠ **선형 해독기다** — `SEP`/`REP` 를 따라가며 즉치 폭을 정하되 **분기는 안 따라간다.** 코드가
아닌 자리(표·문안)를 주면 그럴듯한 헛것이 나온다. 시작점은 **호출 자리에서 얻는다.**
⚠ 진입 시점의 `m`/`x` 폭은 **모르면 틀린다** — 기본은 8비트이고, 16비트로 들어가는 자리는
`m16`/`x16` 을 준다. 스트림이 어긋나면 니모닉이 갑자기 말이 안 되는 것으로 알아챈다.

    python3 games/sfc-ed1/tools/dis65816.py 0x0298E0 0x029960        # $02:98E0 ~ $02:9960
    python3 games/sfc-ed1/tools/dis65816.py 0x02DCC0 0x02DD60 m16    # 16비트 누산기로 들어가는 자리
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: F401, I001  (common 보다 먼저 — shared/text 와 이름이 겹친다)
import common

# (name, mode) 표 — mode: imp imm_m imm_x imm8 imm16 dp dpx dpy idp idpx idpy idl idly
#                          sr isry abs absx absy abl ablx ind iax ial rel rell bm acc
TAB = {
    0x00: ("brk", "imm8"),
    0x01: ("ora", "idpx"),
    0x02: ("cop", "imm8"),
    0x03: ("ora", "sr"),
    0x04: ("tsb", "dp"),
    0x05: ("ora", "dp"),
    0x06: ("asl", "dp"),
    0x07: ("ora", "idl"),
    0x08: ("php", "imp"),
    0x09: ("ora", "imm_m"),
    0x0A: ("asl", "acc"),
    0x0B: ("phd", "imp"),
    0x0C: ("tsb", "abs"),
    0x0D: ("ora", "abs"),
    0x0E: ("asl", "abs"),
    0x0F: ("ora", "abl"),
    0x10: ("bpl", "rel"),
    0x11: ("ora", "idpy"),
    0x12: ("ora", "idp"),
    0x13: ("ora", "isry"),
    0x14: ("trb", "dp"),
    0x15: ("ora", "dpx"),
    0x16: ("asl", "dpx"),
    0x17: ("ora", "idly"),
    0x18: ("clc", "imp"),
    0x19: ("ora", "absy"),
    0x1A: ("inc", "acc"),
    0x1B: ("tcs", "imp"),
    0x1C: ("trb", "abs"),
    0x1D: ("ora", "absx"),
    0x1E: ("asl", "absx"),
    0x1F: ("ora", "ablx"),
    0x20: ("jsr", "abs"),
    0x21: ("and", "idpx"),
    0x22: ("jsl", "abl"),
    0x23: ("and", "sr"),
    0x24: ("bit", "dp"),
    0x25: ("and", "dp"),
    0x26: ("rol", "dp"),
    0x27: ("and", "idl"),
    0x28: ("plp", "imp"),
    0x29: ("and", "imm_m"),
    0x2A: ("rol", "acc"),
    0x2B: ("pld", "imp"),
    0x2C: ("bit", "abs"),
    0x2D: ("and", "abs"),
    0x2E: ("rol", "abs"),
    0x2F: ("and", "abl"),
    0x30: ("bmi", "rel"),
    0x31: ("and", "idpy"),
    0x32: ("and", "idp"),
    0x33: ("and", "isry"),
    0x34: ("bit", "dpx"),
    0x35: ("and", "dpx"),
    0x36: ("rol", "dpx"),
    0x37: ("and", "idly"),
    0x38: ("sec", "imp"),
    0x39: ("and", "absy"),
    0x3A: ("dec", "acc"),
    0x3B: ("tsc", "imp"),
    0x3C: ("bit", "absx"),
    0x3D: ("and", "absx"),
    0x3E: ("rol", "absx"),
    0x3F: ("and", "ablx"),
    0x40: ("rti", "imp"),
    0x41: ("eor", "idpx"),
    0x42: ("wdm", "imm8"),
    0x43: ("eor", "sr"),
    0x44: ("mvp", "bm"),
    0x45: ("eor", "dp"),
    0x46: ("lsr", "dp"),
    0x47: ("eor", "idl"),
    0x48: ("pha", "imp"),
    0x49: ("eor", "imm_m"),
    0x4A: ("lsr", "acc"),
    0x4B: ("phk", "imp"),
    0x4C: ("jmp", "abs"),
    0x4D: ("eor", "abs"),
    0x4E: ("lsr", "abs"),
    0x4F: ("eor", "abl"),
    0x50: ("bvc", "rel"),
    0x51: ("eor", "idpy"),
    0x52: ("eor", "idp"),
    0x53: ("eor", "isry"),
    0x54: ("mvn", "bm"),
    0x55: ("eor", "dpx"),
    0x56: ("lsr", "dpx"),
    0x57: ("eor", "idly"),
    0x58: ("cli", "imp"),
    0x59: ("eor", "absy"),
    0x5A: ("phy", "imp"),
    0x5B: ("tcd", "imp"),
    0x5C: ("jml", "abl"),
    0x5D: ("eor", "absx"),
    0x5E: ("lsr", "absx"),
    0x5F: ("eor", "ablx"),
    0x60: ("rts", "imp"),
    0x61: ("adc", "idpx"),
    0x62: ("per", "rell"),
    0x63: ("adc", "sr"),
    0x64: ("stz", "dp"),
    0x65: ("adc", "dp"),
    0x66: ("ror", "dp"),
    0x67: ("adc", "idl"),
    0x68: ("pla", "imp"),
    0x69: ("adc", "imm_m"),
    0x6A: ("ror", "acc"),
    0x6B: ("rtl", "imp"),
    0x6C: ("jmp", "ind"),
    0x6D: ("adc", "abs"),
    0x6E: ("ror", "abs"),
    0x6F: ("adc", "abl"),
    0x70: ("bvs", "rel"),
    0x71: ("adc", "idpy"),
    0x72: ("adc", "idp"),
    0x73: ("adc", "isry"),
    0x74: ("stz", "dpx"),
    0x75: ("adc", "dpx"),
    0x76: ("ror", "dpx"),
    0x77: ("adc", "idly"),
    0x78: ("sei", "imp"),
    0x79: ("adc", "absy"),
    0x7A: ("ply", "imp"),
    0x7B: ("tdc", "imp"),
    0x7C: ("jmp", "iax"),
    0x7D: ("adc", "absx"),
    0x7E: ("ror", "absx"),
    0x7F: ("adc", "ablx"),
    0x80: ("bra", "rel"),
    0x81: ("sta", "idpx"),
    0x82: ("brl", "rell"),
    0x83: ("sta", "sr"),
    0x84: ("sty", "dp"),
    0x85: ("sta", "dp"),
    0x86: ("stx", "dp"),
    0x87: ("sta", "idl"),
    0x88: ("dey", "imp"),
    0x89: ("bit", "imm_m"),
    0x8A: ("txa", "imp"),
    0x8B: ("phb", "imp"),
    0x8C: ("sty", "abs"),
    0x8D: ("sta", "abs"),
    0x8E: ("stx", "abs"),
    0x8F: ("sta", "abl"),
    0x90: ("bcc", "rel"),
    0x91: ("sta", "idpy"),
    0x92: ("sta", "idp"),
    0x93: ("sta", "isry"),
    0x94: ("sty", "dpx"),
    0x95: ("sta", "dpx"),
    0x96: ("stx", "dpy"),
    0x97: ("sta", "idly"),
    0x98: ("tya", "imp"),
    0x99: ("sta", "absy"),
    0x9A: ("txs", "imp"),
    0x9B: ("txy", "imp"),
    0x9C: ("stz", "abs"),
    0x9D: ("sta", "absx"),
    0x9E: ("stz", "absx"),
    0x9F: ("sta", "ablx"),
    0xA0: ("ldy", "imm_x"),
    0xA1: ("lda", "idpx"),
    0xA2: ("ldx", "imm_x"),
    0xA3: ("lda", "sr"),
    0xA4: ("ldy", "dp"),
    0xA5: ("lda", "dp"),
    0xA6: ("ldx", "dp"),
    0xA7: ("lda", "idl"),
    0xA8: ("tay", "imp"),
    0xA9: ("lda", "imm_m"),
    0xAA: ("tax", "imp"),
    0xAB: ("plb", "imp"),
    0xAC: ("ldy", "abs"),
    0xAD: ("lda", "abs"),
    0xAE: ("ldx", "abs"),
    0xAF: ("lda", "abl"),
    0xB0: ("bcs", "rel"),
    0xB1: ("lda", "idpy"),
    0xB2: ("lda", "idp"),
    0xB3: ("lda", "isry"),
    0xB4: ("ldy", "dpx"),
    0xB5: ("lda", "dpx"),
    0xB6: ("ldx", "dpy"),
    0xB7: ("lda", "idly"),
    0xB8: ("clv", "imp"),
    0xB9: ("lda", "absy"),
    0xBA: ("tsx", "imp"),
    0xBB: ("tyx", "imp"),
    0xBC: ("ldy", "absx"),
    0xBD: ("lda", "absx"),
    0xBE: ("ldx", "absy"),
    0xBF: ("lda", "ablx"),
    0xC0: ("cpy", "imm_x"),
    0xC1: ("cmp", "idpx"),
    0xC2: ("rep", "imm8"),
    0xC3: ("cmp", "sr"),
    0xC4: ("cpy", "dp"),
    0xC5: ("cmp", "dp"),
    0xC6: ("dec", "dp"),
    0xC7: ("cmp", "idl"),
    0xC8: ("iny", "imp"),
    0xC9: ("cmp", "imm_m"),
    0xCA: ("dex", "imp"),
    0xCB: ("wai", "imp"),
    0xCC: ("cpy", "abs"),
    0xCD: ("cmp", "abs"),
    0xCE: ("dec", "abs"),
    0xCF: ("cmp", "abl"),
    0xD0: ("bne", "rel"),
    0xD1: ("cmp", "idpy"),
    0xD2: ("cmp", "idp"),
    0xD3: ("cmp", "isry"),
    0xD4: ("pei", "dp"),
    0xD5: ("cmp", "dpx"),
    0xD6: ("dec", "dpx"),
    0xD7: ("cmp", "idly"),
    0xD8: ("cld", "imp"),
    0xD9: ("cmp", "absy"),
    0xDA: ("phx", "imp"),
    0xDB: ("stp", "imp"),
    0xDC: ("jml", "ial"),
    0xDD: ("cmp", "absx"),
    0xDE: ("dec", "absx"),
    0xDF: ("cmp", "ablx"),
    0xE0: ("cpx", "imm_x"),
    0xE1: ("sbc", "idpx"),
    0xE2: ("sep", "imm8"),
    0xE3: ("sbc", "sr"),
    0xE4: ("cpx", "dp"),
    0xE5: ("sbc", "dp"),
    0xE6: ("inc", "dp"),
    0xE7: ("sbc", "idl"),
    0xE8: ("inx", "imp"),
    0xE9: ("sbc", "imm_m"),
    0xEA: ("nop", "imp"),
    0xEB: ("xba", "imp"),
    0xEC: ("cpx", "abs"),
    0xED: ("sbc", "abs"),
    0xEE: ("inc", "abs"),
    0xEF: ("sbc", "abl"),
    0xF0: ("beq", "rel"),
    0xF1: ("sbc", "idpy"),
    0xF2: ("sbc", "idp"),
    0xF3: ("sbc", "isry"),
    0xF4: ("pea", "imm16"),
    0xF5: ("sbc", "dpx"),
    0xF6: ("inc", "dpx"),
    0xF7: ("sbc", "idly"),
    0xF8: ("sed", "imp"),
    0xF9: ("sbc", "absy"),
    0xFA: ("plx", "imp"),
    0xFB: ("xce", "imp"),
    0xFC: ("jsr", "iax"),
    0xFD: ("sbc", "absx"),
    0xFE: ("inc", "absx"),
    0xFF: ("sbc", "ablx"),
}
LEN = {
    "imp": 0,
    "acc": 0,
    "imm_m": 1,
    "imm_x": 1,
    "imm8": 1,
    "imm16": 2,
    "dp": 1,
    "dpx": 1,
    "dpy": 1,
    "idp": 1,
    "idpx": 1,
    "idpy": 1,
    "idl": 1,
    "idly": 1,
    "sr": 1,
    "isry": 1,
    "abs": 2,
    "absx": 2,
    "absy": 2,
    "abl": 3,
    "ablx": 3,
    "ind": 2,
    "iax": 2,
    "ial": 2,
    "rel": 1,
    "rell": 2,
    "bm": 2,
}


def dis(rom, start, end, m8=True, x8=True):
    """start/end 는 $bb:aaaa. 줄 목록을 낸다."""
    bank = (start >> 16) & 0xFF
    pc = start & 0xFFFF
    out = []
    while (bank << 16 | pc) < end:
        off = common.snes2off(bank << 16 | pc)
        op = rom[off]
        name, mode = TAB[op]
        n = LEN[mode]
        if mode == "imm_m":
            n = 1 if m8 else 2
        elif mode == "imm_x":
            n = 1 if x8 else 2
        raw = rom[off + 1 : off + 1 + n]
        v = int.from_bytes(raw, "little") if n else 0
        if mode in ("rel",):
            tgt = (pc + 2 + (v - 256 if v > 127 else v)) & 0xFFFF
            arg = f"${bank:02X}:{tgt:04X}"
        elif mode == "rell":
            tgt = (pc + 3 + (v - 65536 if v > 32767 else v)) & 0xFFFF
            arg = f"${bank:02X}:{tgt:04X}"
        elif mode == "bm":
            arg = f"${raw[0]:02X},${raw[1]:02X}"
        elif mode in ("imm_m", "imm_x", "imm8", "imm16"):
            arg = f"#${v:0{n * 2}X}"
        elif mode in ("abl", "ablx"):
            arg = f"${v >> 16:02X}:{v & 0xFFFF:04X}" + (",x" if mode == "ablx" else "")
        elif mode == "acc":
            arg = "a"
        elif mode == "imp":
            arg = ""
        else:
            sfx = {
                "dp": "",
                "dpx": ",x",
                "dpy": ",y",
                "idp": ")",
                "idpx": ",x)",
                "idpy": "),y",
                "idl": "]",
                "idly": "],y",
                "sr": ",s",
                "isry": ",s),y",
                "abs": "",
                "absx": ",x",
                "absy": ",y",
                "ind": ")",
                "iax": ",x)",
                "ial": "]",
            }[mode]
            pre = {
                "idp": "(",
                "idpx": "(",
                "idpy": "(",
                "idl": "[",
                "idly": "[",
                "isry": "(",
                "ind": "(",
                "iax": "(",
                "ial": "[",
            }.get(mode, "")
            w = 2 if n == 1 else 4
            arg = f"{pre}${v:0{w}X}{sfx}"
        out.append(
            f"${bank:02X}:{pc:04X}  "
            + " ".join(f"{b:02X}" for b in rom[off : off + 1 + n]).ljust(12)
            + f"  {name} {arg}".rstrip()
        )
        if op == 0xE2:  # sep
            if v & 0x20:
                m8 = True
            if v & 0x10:
                x8 = True
        elif op == 0xC2:  # rep
            if v & 0x20:
                m8 = False
            if v & 0x10:
                x8 = False
        pc += 1 + n
        if pc > 0xFFFF:
            break
    return out


if __name__ == "__main__":
    rom = common.rom_bytes()
    a = int(sys.argv[1], 16)
    b = int(sys.argv[2], 16)
    m8 = "m16" not in sys.argv
    x8 = "x16" not in sys.argv
    print("\n".join(dis(rom, a, b, m8, x8)))
