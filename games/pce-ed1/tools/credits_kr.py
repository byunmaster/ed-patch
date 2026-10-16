"""오프닝 성우 크레딧(크레딧 모듈 rel 514, 논리 = 오프셋 + $4000 · 뱅크 0x68/0x6A/0x6B 가 $4000/$6000/$8000 에 걸린다) 한글화.

마스터 10-16 「성우 출연도 한글 안 되는 줄 알고 CAST 로 한 건데 되면 성우 출연 으로 하자」·「성우 이름도 한글로」(규칙 3-7) — 이름 13명은 갈무리 콘덴스드 7px 글자 둘/칸(아래 NAMES).

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

# 성우 이름 표(원문 10B 열쇠 → 한글) — 제작진·성우 이름 표는 게임별이라 `staffroll.py` 에 둔다(자기 표 검사 예외, 마스터 10-08)
from staffroll import OPENING_CAST as NAMES

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


def _emit_name(a: Asm, tbl: int, bank: int) -> None:
    """이름 칸 = 리드(왼 반 칸 번호+1) · 트레일(오른 반 칸 번호) — 갈무리 콘덴스드 7px 글자 둘을 한 칸(16px)에 나란히(왼 글자 = 위 바이트, 오른 글자 = 아래 바이트). 번호 0 = 빈 반 칸.
    글리프는 12B(행마다 1B, 왼쪽 정렬) 표 `tbl`(뱅크 `bank`). 출력 = `$38BB` 32B(행 2B)."""
    a.op("SEI")
    a.op("TMA", "tma", 5)
    a.op("PHA")
    a.op("LDA", "imm", bank)
    a.op("TAM", "tam", 5)
    a.op("LDA", "zp", 0xF9)
    a.op("SEC")
    a.op("SBC", "imm", 1)
    a.op("TAX")
    a.op("JSR", "abs", "mul")
    a.op("LDY", "imm", 0)
    a.op("LDX", "imm", 0)
    a.label("l1")
    a.op("LDA", "izpy", 0xEC)
    a.op("STA", "absx", 0x38BB)
    a.op("INX")
    a.op("INX")
    a.op("INY")
    a.op("CPY", "imm", 12)
    a.op("BNE", "rel", "l1")
    a.op("LDX", "zp", 0xF8)
    a.op("JSR", "abs", "mul")
    a.op("LDY", "imm", 0)
    a.op("LDX", "imm", 1)
    a.label("l2")
    a.op("LDA", "izpy", 0xEC)
    a.op("STA", "absx", 0x38BB)
    a.op("INX")
    a.op("INX")
    a.op("INY")
    a.op("CPY", "imm", 12)
    a.op("BNE", "rel", "l2")
    a.op("LDA", "imm", 0)
    a.op("LDX", "imm", 24)
    a.label("zn")
    a.op("STA", "absx", 0x38BB)
    a.op("INX")
    a.op("CPX", "imm", 32)
    a.op("BNE", "rel", "zn")
    a.op("PLA")
    a.op("TAM", "tam", 5)
    a.op("CLI")
    a.op("LDA", "imm", 0)
    a.op("RTS")
    a.label("mul")  # X = 번호 → $EC/$ED = tbl + 12·X
    a.op("LDA", "imm", tbl & 0xFF)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "imm", tbl >> 8)
    a.op("STA", "zp", 0xED)
    a.label("m1")
    a.op("CPX", "imm", 0)
    a.op("BEQ", "rel", "m2")
    a.op("CLC")
    a.op("LDA", "zp", 0xEC)
    a.op("ADC", "imm", 12)
    a.op("STA", "zp", 0xEC)
    a.op("BCC", "rel", "m3")
    a.op("INC", "zp", 0xED)
    a.label("m3")
    a.op("DEX")
    a.op("BRA", "rel", "m1")
    a.label("m2")
    a.op("RTS")


def routine(base: int, segs: list[tuple[int, int]], bank: int | None, names_tbl: int | None = None) -> bytes:
    """리드 F0 + 트레일(0x24+번호) → 18B 묶음 표(`segs` = [(논리 주소, 글자 수)…], 번호 순)에서 24B 로 풀어 `($FA)` 에 쓰고 뒤 8B 는 0 으로.
    `bank` 가 있으면 그 뱅크를 MPR5($A000)에 잠깐 건다(크레딧 모듈의 뱅크 0x69 표). 엔딩 스태프롤도 같은 루틴(`bank=None`)을 쓴다 — 영 페이지 `$EC`·`$ED` 만 쓴다."""
    a = Asm(base)
    a.op("LDA", "zp", 0xF9)
    a.op("CMP", "imm", font.LEAD0)
    if names_tbl is None:
        a.op("BNE", "rel", "orig")
        a.op("BRA", "rel", "main")
        a.label("orig")
        a.op("JMP", "abs", BIOS_GETFNT)
    else:
        a.op("BNE", "rel", "n1")
        a.op("JMP", "abs", "main")
        a.label("n1")
        a.op("CMP", "imm", 0x80)
        a.op("BCC", "rel", "name")  # 리드 1~0x7F = 이름 칸(반 칸 둘)
        a.op("JMP", "abs", BIOS_GETFNT)
        a.label("name")
        _emit_name(a, names_tbl, bank)
    a.label("main")
    a.op("LDA", "zp", 0xF8)
    a.op("SEC")
    a.op("SBC", "imm", font.TRAIL0)
    a.op("TAX")  # X = k(이 표 안 번호)
    for n, (addr, count) in enumerate(segs):
        last = n == len(segs) - 1
        if not last:
            a.op("CPX", "imm", count)
            a.op("BCS", "rel", f"seg{n + 1}")
        a.op("LDA", "imm", addr & 0xFF)
        a.op("STA", "zp", 0xEC)
        a.op("LDA", "imm", addr >> 8)
        a.op("STA", "zp", 0xED)
        if not last:
            a.op("BRA", "rel", "lp")
            a.label(f"seg{n + 1}")
            a.op("TXA")
            a.op("SEC")
            a.op("SBC", "imm", count)
            a.op("TAX")
            # 다음 구역 머리는 다음 반복에서 넣는다
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
    if bank is not None:
        a.op("SEI")
        a.op("TMA", "tma", 5)
        a.op("PHA")  # 걸려 있던 MPR5 저장
        a.op("LDA", "imm", bank)
        a.op("TAM", "tam", 5)
    a.op("LDY", "imm", 0)

    def inc(n):
        a.op("INC", "zp", 0xEC)
        a.op("BNE", "rel", f"i{n}")
        a.op("INC", "zp", 0xED)
        a.label(f"i{n}")

    a.label("grp")  # 3B(2 행 낱말 셋) → 4B, 여섯 번 = 18B → 24B (Y 가 24 가 되면 끝)
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
    a.op("CPY", "imm", 24)
    a.op("BNE", "rel", "grp")
    a.op("LDA", "imm", 0)
    a.label("z")  # 렌더러는 32B 를 읽는다 — 뒤 8B 는 0
    a.op("STA", "izpy", 0xFA)
    a.op("INY")
    a.op("CPY", "imm", 32)
    a.op("BNE", "rel", "z")
    if bank is not None:
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


# ── 성우 이름 13명 — 마스터 10-16 「이름이 긴 사람은 갈무리 콘덴스드로」·「성우이름을 일괄 갈무리 콘덴스드로 해도 될듯」 ────────────────────────────────────────
# 이름 글자는 `shared/fonts/Galmuri11-Condensed.bdf`(폭 7px)를 **한 칸(16px)에 둘씩** 나란히 놓는다(왼 글자 = 칸의 위 바이트, 오른 글자 = 아래 바이트). 반 칸 피치 8px — 8음절 + 공백이 5칸(80px)에 든다.
# 문자열은 원문과 같은 11B 간격(5칸 = 10B + 0)이라 자리를 안 옮긴다. 칸 코드 = (왼 반칸 번호+1, 오른 반칸 번호), 번호 0 = 빈 반 칸, 1~47 = 글자.
# 스프라이트 서술자(모듈 +0x65F2·+0x660C — 칸 5개, 가운데 한 칸을 비운 배치)는 **칸 간격만** 붙여 이어 쓴다(바이트 5개 제자리 수정).
NAME_STR0 = 0x042B  # rel 517 안 첫 이름 문자열(표제 +0x420 바로 뒤)
NAME_STRIDE = 11
TITLE_TBL = SEG_A  # 표제 글리프 4자(18B 묶음) 뒤에 이름 글리프 표
NAME_TBL = SEG_A + 18 * 4  # 이름 글리프 표 — 번호 0(빈) + 47자, 글리프 12B(행마다 1B)
DESC_X_PATCHES = [  # (서술자 모듈 오프셋, 칸 x 오프셋 바이트 위치들) — [48, 32, 16, -16, -32] → [32, 16, 0, -16, -32]
    (0x65F3, 48, 32),
    (0x65F8, 32, 16),
    (0x65FD, 16, 0),
    (0x660D, 48, 32),
    (0x6612, 32, 16),
    (0x6617, 16, 0),
    # 같은 서술자의 둘째 사본(뱅크 0x69 +0x219E · +0x21B8) — 한 명 장면은 이쪽을 읽는다(시험 실측: 첫 사본만 고쳤더니 한 명 장면에 틈이 남았다)
    (0x219F, 48, 32),
    (0x21A4, 32, 16),
    (0x21A9, 16, 0),
    (0x21B9, 48, 32),
    (0x21BE, 32, 16),
    (0x21C3, 16, 0),
]


def _cond_font() -> dict[int, tuple[int, int, int, int, list[int]]]:
    import re

    s = (font.common.ROOT / "shared" / "fonts" / "Galmuri11-Condensed.bdf").read_text(encoding="utf-8", errors="replace")
    out = {}
    for m in re.finditer(r"STARTCHAR [^\n]*\nENCODING (\d+)\n(.*?)ENDCHAR", s, re.DOTALL):
        body = m.group(2)
        w, h, xo, yo = map(int, re.search(r"BBX (-?\d+) (-?\d+) (-?\d+) (-?\d+)", body).groups())
        rows = [int(r, 16) for r in re.search(r"BITMAP\n(.*)", body, re.DOTALL).group(1).split()]
        out[int(m.group(1))] = (w, h, xo, yo, rows)
    return out


def _cond_glyph(cf, ch: str) -> bytes:
    """콘덴스드 글자 → 12B(행마다 1B, 7px 왼쪽 정렬). 세로는 기본 글꼴과 같은 기준선에 앉힌다."""
    w, h, xo, yo, rows = cf[ord(ch)]
    assert w <= 7 and xo >= 0 and (7 + xo) <= 8, (ch, w, xo)
    out = [0] * 12
    top = font.BASELINE_ROW - (h + yo)
    for i, r in enumerate(rows):
        y = top + i
        if 0 <= y < 12:
            out[y] = (r >> xo) & 0xFE if xo else r & 0xFE
    assert any(out), ch
    return bytes(out)


def name_syllables() -> list[str]:
    return sorted({c for _, ko in NAMES for c in ko if c != " "})


def name_blob() -> bytes:
    cf = _cond_font()
    return bytes(12) + b"".join(_cond_glyph(cf, c) for c in name_syllables())


def name_string(ko: str) -> bytes:
    """한글 이름 → 칸 5개(10B) + 0 — 반 칸 번호 열(음절 · 공백=0)을 둘씩 묶는다."""
    idx = {c: i + 1 for i, c in enumerate(name_syllables())}
    halves = [0 if c == " " else idx[c] for c in ko]
    assert len(halves) <= 10, (ko, len(halves))
    halves += [0] * (10 - len(halves))
    out = bytearray()
    for k in range(5):
        out += bytes([halves[2 * k] + 1, halves[2 * k + 1]])
    assert 0 not in out[0::2]
    return bytes(out) + b"\0"


def _sjis10(jp: str) -> bytes:
    b = jp.encode("sjis")
    if len(b) == 8:
        b += b"\x81\x40"
    assert len(b) == 10, (jp, len(b))
    return b


def glyph_blobs() -> list[tuple[int, bytes]]:
    """[(모듈 오프셋, 바이트)] — 뱅크 0x69 0 구역: 표제 18B 묶음 4자 + 이름 12B 글리프 표."""
    packed = [font.pack(font.glyph(c)) for c in glyph_set()]
    assert len(packed) == 4, len(packed)
    nb = name_blob()
    assert TITLE_TBL + 72 + len(nb) <= SEG_A + 794, len(nb)
    return [(TITLE_TBL, b"".join(packed)), (NAME_TBL, nb)]


def patches() -> list[tuple[str, int, int, bytes, bytes]]:
    """build.code_patches 꼴 (라벨, rel, 구간 안 오프셋, 기대, 새값)."""
    r = routine(
        logical(ROUTINE_OFF),
        [(0xA000 + TITLE_TBL - 0x2000, 4)],
        MAP_BANK,
        names_tbl=0xA000 + NAME_TBL - 0x2000,
    )
    assert len(r) <= ROUTINE_ROOM, (len(r), ROUTINE_ROOM)
    old, new = title_bytes()
    out = [("cast title 声優出演→성우 출연", 517, 0x0420, old, new)]
    for k, (jp, ko) in enumerate(NAMES):
        out.append((f"cast name {k}", 517, NAME_STR0 + NAME_STRIDE * k, _sjis10(jp), name_string(ko)[:10]))
    out.append(("cast 글리프 루틴", MODULE_REL + ROUTINE_OFF // 2048, ROUTINE_OFF % 2048, bytes(len(r)), r))
    for off, blob in glyph_blobs():
        pos = 0
        while pos < len(blob):
            o = off + pos
            n = min(len(blob) - pos, 2048 - o % 2048)
            out.append(("cast 글리프 표", MODULE_REL + o // 2048, o % 2048, bytes(n), blob[pos : pos + n]))
            pos += n
    for off, was, now in DESC_X_PATCHES:
        out.append(("cast 서술자 칸 간격", MODULE_REL + off // 2048, off % 2048, bytes([was]), bytes([now])))
    out.append(("cast EX_GETFNT seam", MODULE_REL + CALL_OPERAND // 2048, CALL_OPERAND % 2048, b"\x60\xe0", logical(ROUTINE_OFF).to_bytes(2, "little")))
    return out
