"""폰트 후킹 루틴·초기화 스텁 — 손인코딩 HuC6280 을 **미니 어셈블러**로 낸다(오타 방지).

배치(status.md 9절):
  · 루틴 본체 `$3B00~`(워크 RAM, 쓰기 0회 확인 구간). 원본은 디스크 rel 126(뱅크 0x7F 적재분) 앞 256B 에
    실어 두고 스텁이 TII 로 옮긴다.
  · 글리프 뱅크: rel 114~125(뱅크 0x7C~0x7E 적재분, 원본 0) → 스텁이 0x85~0x87 로 복사.
  · 스텁: 뱅크 0x69 +0x1852(루틴 사이 850B 패딩, 논리 $7852). 본 프로그램 진입 `JSR $5798` 을 스텁으로 돌리고
    스텁이 `JMP $5798` 로 잇는다.
  · 호출 규약은 EX_GETFNT 그대로: `_ax`=코드(`$F9` 리드 · `$F8` 트레일), `_bx`=출력 32B, 성공 시 A=0.
    리드 F0~F9 만 가로채고 나머지는 `JMP $E060`. BIOS 처럼 `$EC~$EE` 를 스크래치로 쓴다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font

HOOK_ADDR = 0x3B00
STUB_ADDR = 0x7852  # 뱅크 0x69 +0x1852
ORIG_INIT = 0x5798
GLYPH_WINDOW_HI = 0x60  # 글리프 뱅크를 MPR3($6000) 에 잠깐 건다
GLYPH_BANK0 = 0x85

# (니모닉, 모드) → 옵코드. 모드: imp · imm · zp · abs · absx · absy · izpy · rel · tma · tam
OPS = {
    ("LDA", "zp"): 0xA5,
    ("LDA", "imm"): 0xA9,
    ("LDA", "abs"): 0xAD,
    ("LDA", "absx"): 0xBD,
    ("LDA", "izpy"): 0xB1,
    ("STA", "zp"): 0x85,
    ("STA", "abs"): 0x8D,
    ("STA", "izpy"): 0x91,
    ("STZ", "zp"): 0x64,
    ("CMP", "imm"): 0xC9,
    ("CPY", "imm"): 0xC0,
    ("BCC", "rel"): 0x90,
    ("BCS", "rel"): 0xB0,
    ("BNE", "rel"): 0xD0,
    ("JMP", "abs"): 0x4C,
    ("RTS", "imp"): 0x60,
    ("INY", "imp"): 0xC8,
    ("CLA", "imp"): 0x62,
    ("CLY", "imp"): 0xC2,
    ("PHA", "imp"): 0x48,
    ("PLA", "imp"): 0x68,
    ("PHP", "imp"): 0x08,
    ("PLP", "imp"): 0x28,
    ("SEI", "imp"): 0x78,
    ("PHX", "imp"): 0xDA,
    ("PLX", "imp"): 0xFA,
    ("PHY", "imp"): 0x5A,
    ("PLY", "imp"): 0x7A,
    ("TAX", "imp"): 0xAA,
    ("SEC", "imp"): 0x38,
    ("CLC", "imp"): 0x18,
    ("ASL", "imp"): 0x0A,
    ("SBC", "imm"): 0xE9,
    ("ADC", "imm"): 0x69,
    ("ADC", "zp"): 0x65,
    ("ADC", "absx"): 0x7D,
    ("AND", "imm"): 0x29,
    ("ORA", "imm"): 0x09,
    ("ASL", "zp"): 0x06,
    ("ROL", "zp"): 0x26,
    ("LSR", "imp"): 0x4A,
    ("TMA", "tma"): 0x43,
    ("TAM", "tam"): 0x53,
}


class Asm:
    def __init__(self, org: int):
        self.org = org
        self.out = bytearray()
        self.labels: dict[str, int] = {}
        self.fix: list[tuple[int, str, str]] = []  # (pos, label, kind)

    @property
    def pc(self):
        return self.org + len(self.out)

    def label(self, name):
        self.labels[name] = self.pc

    def op(self, mn, mode="imp", arg=None):
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
        elif mode in ("abs", "absx"):
            if isinstance(arg, str):
                self.fix.append((len(self.out), arg, "abs"))
                self.out += b"\0\0"
            else:
                self.out += arg.to_bytes(2, "little")

    def tii(self, src, dst, ln):
        self.out += (
            b"\x73"
            + src.to_bytes(2, "little")
            + dst.to_bytes(2, "little")
            + ln.to_bytes(2, "little")
        )

    def data(self, b: bytes):
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


def hook_routine() -> bytes:
    a = Asm(HOOK_ADDR)
    a.op("LDA", "zp", 0xF9)
    a.op("CMP", "imm", font.LEAD0)
    a.op("BCC", "rel", "bios")
    a.op("CMP", "imm", font.LEAD0 + 10)
    a.op("BCC", "rel", "ours")
    a.label("bios")
    a.op("JMP", "abs", 0xE060)  # 리드가 우리 범위 밖 — BIOS 그대로(_dh 는 호출부가 이미 세웠다)
    a.label("ours")
    a.op("PHP")
    a.op("SEI")
    a.op("PHX")
    a.op("PHY")
    # off = base[lead] + (trail-0x24)*24 → $EC/$ED
    a.op("SEC")
    a.op("SBC", "imm", font.LEAD0)
    a.op("ASL")
    a.op("TAX")  # X = lead*2 (안 쓰지만 base 표 인덱스용)
    a.op("LDA", "zp", 0xF8)
    a.op("SEC")
    a.op("SBC", "imm", font.TRAIL0)
    a.op("STA", "zp", 0xEC)
    a.op("STZ", "zp", 0xED)
    for _ in range(3):  # ×8
        a.op("ASL", "zp", 0xEC)
        a.op("ROL", "zp", 0xED)
    a.op("LDA", "zp", 0xEC)
    a.op("PHA")
    a.op("LDA", "zp", 0xED)
    a.op("PHA")  # ×8 보관
    a.op("ASL", "zp", 0xEC)
    a.op("ROL", "zp", 0xED)  # ×16
    a.op("PLA")
    a.op("STA", "zp", 0xEE)  # hi8
    a.op("PLA")
    a.op("CLC")
    a.op("ADC", "zp", 0xEC)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0xEE)
    a.op("ADC", "zp", 0xED)
    a.op("STA", "zp", 0xED)  # ×24
    # X = lead (0..9) 로 base 표
    a.op("LDA", "zp", 0xF9)
    a.op("SEC")
    a.op("SBC", "imm", font.LEAD0)
    a.op("TAX")
    a.op("CLC")
    a.op("LDA", "zp", 0xEC)
    a.op("ADC", "absx", "base_lo")
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0xED)
    a.op("ADC", "absx", "base_hi")
    a.op("STA", "zp", 0xED)
    # bank = 0x85 + (off>>13) ; MPR3 저장 후 걸기
    a.op("TMA", "tma", 3)
    a.op("STA", "zp", 0xEE)
    a.op("LDA", "zp", 0xED)
    for _ in range(5):
        a.op("LSR")
    a.op("CLC")
    a.op("ADC", "imm", GLYPH_BANK0)
    a.op("TAM", "tam", 3)
    a.op("LDA", "zp", 0xED)
    a.op("AND", "imm", 0x1F)
    a.op("ORA", "imm", GLYPH_WINDOW_HI)
    a.op("STA", "zp", 0xED)
    a.op("CLY")
    a.label("copy")
    a.op("LDA", "izpy", 0xEC)
    a.op("STA", "izpy", 0xFA)
    a.op("INY")
    a.op("CPY", "imm", font.GLYPH_BYTES)
    a.op("BNE", "rel", "copy")
    a.op("CLA")
    a.label("zero")
    a.op("STA", "izpy", 0xFA)
    a.op("INY")
    a.op("CPY", "imm", 0x20)
    a.op("BNE", "rel", "zero")
    a.op("LDA", "zp", 0xEE)
    a.op("TAM", "tam", 3)
    a.op("PLY")
    a.op("PLX")
    a.op("PLP")
    a.op("CLA")
    a.op("RTS")
    a.label("base_lo")
    a.data(font.base_table()[:10])
    a.label("base_hi")
    a.data(font.base_table()[10:])
    b = a.bytes()
    assert len(b) <= 256, len(b)
    return b + b"\0" * (256 - len(b))


def init_stub() -> bytes:
    a = Asm(STUB_ADDR)
    a.op("TMA", "tma", 5)
    a.op("PHA")
    a.op("TMA", "tma", 6)
    a.op("PHA")
    for i in range(3):
        a.op("LDA", "imm", 0x7C + i)
        a.op("TAM", "tam", 5)
        a.op("LDA", "imm", GLYPH_BANK0 + i)
        a.op("TAM", "tam", 6)
        a.tii(0xA000, 0xC000, 0x2000)
    a.op("LDA", "imm", 0x7F)
    a.op("TAM", "tam", 5)
    a.tii(0xA000, HOOK_ADDR, 0x100)
    a.op("PLA")
    a.op("TAM", "tam", 6)
    a.op("PLA")
    a.op("TAM", "tam", 5)
    a.op("JMP", "abs", ORIG_INIT)
    return a.bytes()


if __name__ == "__main__":
    h = hook_routine()
    print("hook", len(h.rstrip(b"\0")), "B:", h.rstrip(b"\0").hex())
    s = init_stub()
    print("stub", len(s), "B:", s.hex())
