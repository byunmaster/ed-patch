"""오프닝 성우 크레딧(크레딧 모듈 rel 514, 논리 = 오프셋 + $4000 · 뱅크 0x68/0x6A/0x6B 가 $4000/$6000/$8000 에 걸린다) 한글화.

마스터 10-16 「성우 출연도 한글 안 되는 줄 알고 CAST 로 한 건데 되면 성우 출연 으로 하자」·「성우 이름도 한글로」(규칙 3-7).

크레딧 모듈은 SJIS 평문(rel 517 +0x420 = $5C20, `00` 종단)을 글자마다 `JSR $E060`(+0x1CE3 = $5CE3)로 그린다(`$F9`=리드 · `$F8`=트레일 → `$38BB` 32B → VRAM).
🔴 **정본 글리프 후킹($2300)은 이 모듈에서 못 쓴다** — 모듈이 그 RAM($2300~)을 제 용도로 덮어 쓴다(시험 실측: $2300 에 `43 10 48 A9 6A …` 가 있었다 → 표제가 안 그려졌다).
그래서 **모듈 안 빈 구역(모듈 +0x7F0D~, 243B — $8000 창(MPR4), 항상 걸려 있다)에 자체 루틴**을 두고 호출 피연산자를 돌린다.
🔴 **상주 글리프 뱅크(0x86~0x87)는 크레딧 때 비어 있다**(시험 실측: 그 자리에 다른 자료 — 리소스 캐시를 모듈이 쓴다) → 글리프는 **모듈 안 0 구역(뱅크 0x69 = 모듈 +0x2000~, 항상 걸려 있지 않아
MPR5($A000)에 잠깐 걸어 읽는다)에 18B 묶음으로** 싣는다: A 구역 +0x3910(794B, 44자) · B 구역 +0x3287(165B, 9자). 코드는 리드 F0 + 트레일 0x24+번호(이 표 안 번호).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font
import hook
from hook import Asm

hook.OPS.update(
    {
        ("CLI", "imp"): 0x58,
        ("ORA", "izpy"): 0x11,
        ("DEC", "zp"): 0xC6,
        ("CPX", "imm"): 0xE0,
    }
)

MODULE_REL = 514
CALL_OPERAND = 0x1CE4  # `JSR $E060` 의 피연산자(모듈 오프셋)
ROUTINE_OFF = 0x7F0D  # 모듈 안 0 구역 시작(243B) — 논리 $8000 + (off − 0x6000)
ROUTINE_ROOM = 0x8000 - ROUTINE_OFF
TEXT_OFF = 0x1C20  # 표제 문자열(rel 517 +0x420)
BIOS_GETFNT = 0xE060
MAP_BANK = 0x69  # 모듈 +0x2000~0x3FFF — 평소엔 안 걸려 있다
SEG_A, SEG_A_N = 0x3910, 44  # 794B
SEG_B, SEG_B_N = 0x3287, 9  # 165B


def routine(base: int) -> bytes:
    a = Asm(base)
    a.op("LDA", "zp", 0xF9)
    a.op("CMP", "imm", font.LEAD0)
    a.op("BNE", "rel", "orig")
    a.op("BRA", "rel", "main")
    a.label("orig")
    a.op("JMP", "abs", BIOS_GETFNT)
    a.label("main")
    a.op("LDA", "zp", 0xF8)
    a.op("SEC")
    a.op("SBC", "imm", font.TRAIL0)
    a.op("TAX")  # X = k(이 표 안 번호)
    a.op("CPX", "imm", SEG_A_N)
    a.op("BCS", "rel", "segb")
    a.op("LDA", "imm", (0xA000 + SEG_A - 0x2000) & 0xFF)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "imm", (0xA000 + SEG_A - 0x2000) >> 8)
    a.op("STA", "zp", 0xED)
    a.op("BRA", "rel", "lp")
    a.label("segb")
    a.op("TXA")
    a.op("SEC")
    a.op("SBC", "imm", SEG_A_N)
    a.op("TAX")
    a.op("LDA", "imm", (0xA000 + SEG_B - 0x2000) & 0xFF)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "imm", (0xA000 + SEG_B - 0x2000) >> 8)
    a.op("STA", "zp", 0xED)
    a.label("lp")  # ptr += 18 · X
    a.op("CPX", "imm", 0)
    a.op("BEQ", "rel", "go")
    a.op("CLC")
    a.op("LDA", "zp", 0xEC)
    a.op("ADC", "imm", font.PACKED_BYTES)
    a.op("STA", "zp", 0xEC)
    a.op("BCC", "rel", "nc")
    a.op("INC", "zp", 0xED)
    a.label("nc")
    a.op("DEX")
    a.op("BRA", "rel", "lp")
    a.label("go")
    a.op("SEI")
    a.op("TMA", "tma", 5)
    a.op("PHA")  # 걸려 있던 MPR5 저장
    a.op("LDA", "imm", MAP_BANK)
    a.op("TAM", "tam", 5)
    a.op("LDY", "imm", 0)
    a.op("LDA", "imm", 6)
    a.op("STA", "zp", 0xEE)  # 6묶음(18B → 24B)

    def inc(n):
        a.op("INC", "zp", 0xEC)
        a.op("BNE", "rel", f"i{n}")
        a.op("INC", "zp", 0xED)
        a.label(f"i{n}")

    a.label("grp")
    a.op("LDA", "izp", 0xEC)
    a.op("STA", "izpy", 0xFA)
    a.op("INY")  # ha
    inc(0)
    a.op("LDA", "izp", 0xEC)
    inc(1)
    a.op("TAX")  # b1
    a.op("AND", "imm", 0xF0)
    a.op("STA", "izpy", 0xFA)
    a.op("INY")  # la
    a.op("LDA", "izp", 0xEC)
    inc(2)
    a.op("PHA")  # b2
    for _ in range(4):
        a.op("LSR")
    a.op("STA", "izpy", 0xFA)  # hb 아래 니블 = b2 >> 4
    a.op("TXA")
    for _ in range(4):
        a.op("ASL")
    a.op("ORA", "izpy", 0xFA)
    a.op("STA", "izpy", 0xFA)
    a.op("INY")  # hb
    a.op("PLA")
    for _ in range(4):
        a.op("ASL")
    a.op("STA", "izpy", 0xFA)
    a.op("INY")  # lb
    a.op("DEC", "zp", 0xEE)
    a.op("BNE", "rel", "grp")
    a.op("LDA", "imm", 0)
    a.label("z")  # 렌더러는 32B 를 읽는다 — 뒤 8B 는 0
    a.op("STA", "izpy", 0xFA)
    a.op("INY")
    a.op("CPY", "imm", 32)
    a.op("BNE", "rel", "z")
    a.op("PLA")
    a.op("TAM", "tam", 5)
    a.op("CLI")
    a.op("LDA", "imm", 0)
    a.op("RTS")
    return a.bytes()


def logical(off: int) -> int:
    """모듈 오프셋 → 논리 주소($4000 창 · $6000 은 +0x4000 · $8000 은 +0x6000 — 뱅크 0x69 는 안 걸린다)."""
    if off < 0x2000:
        return 0x4000 + off
    if 0x4000 <= off < 0x6000:
        return 0x6000 + (off - 0x4000)
    if 0x6000 <= off < 0x8000:
        return 0x8000 + (off - 0x6000)
    raise ValueError(hex(off))


TITLE = "성우 출연"


def glyph_set() -> list[str]:
    """이 크레딧이 쓰는 한글(표 안 번호 순)."""
    return sorted({c for c in TITLE if c != " "})


def chars() -> set[str]:
    return set(glyph_set())


def _code(text: str) -> bytes:
    idx = {c: i for i, c in enumerate(glyph_set())}
    out = bytearray()
    for c in text:
        out += b"\x81\x40" if c == " " else bytes([font.LEAD0, font.TRAIL0 + idx[c]])
    return bytes(out)


def title_bytes() -> tuple[bytes, bytes]:
    """(원문 10B: 声優出演 + 전각 공백, 새 10B: 성우 + 전각 공백 + 출연)."""
    old = "声優出演".encode("sjis") + b"\x81\x40"
    new = _code("성 우 출 연".replace("성 우 출 연", "성우 출연"))
    assert len(old) == len(new), (len(old), len(new))
    return old, new


def glyph_blobs() -> list[tuple[int, bytes]]:
    """[(모듈 오프셋, 18B 묶음들)] — A·B 구역."""
    packed = [font.pack(font.glyph(c)) for c in glyph_set()]
    assert len(packed) <= SEG_A_N + SEG_B_N, len(packed)
    a, b = packed[:SEG_A_N], packed[SEG_A_N:]
    out = [(SEG_A, b"".join(a))]
    if b:
        out.append((SEG_B, b"".join(b)))
    return out


def patches() -> list[tuple[str, int, int, bytes, bytes]]:
    """build.code_patches 꼴 (라벨, rel, 구간 안 오프셋, 기대, 새값)."""
    r = routine(logical(ROUTINE_OFF))
    assert len(r) <= ROUTINE_ROOM, (len(r), ROUTINE_ROOM)
    old, new = title_bytes()
    out = [("cast title 声優出演→성우 출연", 517, 0x0420, old, new)]
    out.append(("cast 글리프 루틴", MODULE_REL + ROUTINE_OFF // 2048, ROUTINE_OFF % 2048, bytes(len(r)), r))
    for off, blob in glyph_blobs():
        # 구역이 섹터 경계를 넘으면 나눈다
        pos = 0
        while pos < len(blob):
            o = off + pos
            n = min(len(blob) - pos, 2048 - o % 2048)
            out.append(("cast 글리프 표", MODULE_REL + o // 2048, o % 2048, bytes(n), blob[pos : pos + n]))
            pos += n
    out.append(("cast EX_GETFNT seam", MODULE_REL + CALL_OPERAND // 2048, CALL_OPERAND % 2048, b"\x60\xe0", logical(ROUTINE_OFF).to_bytes(2, "little")))
    return out
