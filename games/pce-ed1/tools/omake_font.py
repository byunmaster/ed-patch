"""오마케 모듈(rel 450 — 사운드 테스트 · 몬스터 도감)의 **한글 글리프** — 전용 미니 훅 + 전용 글리프 블록.

    python3 games/pce-ed1/tools/omake_font.py        # 훅 바이트·글리프 블록 크기 확인

왜 필요한가 — 오마케 모듈은 글자를 **자기 호출부**로 BIOS `EX_GETFNT`($E060)에서 받는다. 우리 훅($2300)은 본 프로그램 호출부
네 곳만 돌려 놓아서, 이 모듈에 한글 코드(리드 F0~F3)를 넣으면 BIOS 가 그걸 SJIS 로 읽어 **엉뚱한 한자·점**을 낸다(2026-10-14
원판/우리 빌드를 같은 지점에서 비교 — 사운드 테스트 곡 목록이 깨졌다). 게다가 부팅 직후 오마케 경로엔 훅 본체도 글리프 뱅크도
**아예 없고**, 모듈이 `$2400` 대 워크 RAM 을 쓴다 — 본 훅을 옮겨 쓸 수 없다.

그래서 엔딩·오프닝 자막처럼 **모듈 안에 자기 코드를 심는다**(마스터 10-14 「1번 B안」):
  · 미니 훅(`OHOOK`) — 모듈 +0x7E4F(뱅크 0x6B 끝 0 구간 433B, 논리 `$BE4F` — MPR5 창)에 산다. 호출부 둘(+0x7A8C `JSR`, +0x7B76 `JMP`)을
    여기로 돌린다. 리드 F0~F3 이면 전용 표에서 글리프를 `_bx`(32B)에 쓰고 A=0, 아니면 `JMP $E060`.
  · 글리프 블록 — 디스크 rel 447~449(원판 0)에 [2N][(리드,트레일)×N][글리프 32B×N]. 모듈이 뜰 때 `OINIT` 가 BIOS `CD_READ` 로
    **확장 RAM 뱅크 0x6E**(오마케가 안 쓰는 뱅크 — 세 화면 내내 0, 2026-10-14 RAM 대조)에 올린다. 훅은 MPR3($6000)를 잠깐
    그 뱅크로 바꿔 읽고 되돌린다(SEI).
  · `OINIT` 는 모듈 입구의 `JSR $404D`(+0x14)를 가로챈다 — MPR3~6 이 막 잡힌 직후라 $BE4F 가 보인다(+5 의 `LDA $3EF1` 자리는
    아직 안 보인다). 끝에 `JMP $404D` 로 원래대로 이어진다.
  · 🔴 `$22BC~`(BIOS) · 0x6A 꼬리 · 본 훅 자리(`$2300~`)는 안 쓴다. 쓰는 곳 = 모듈 자기 0 구간 + 뱅크 0x6E + 영(零) 페이지 `$EC~$EE`(BIOS 스크래치).
도감 설명도 같은 훅·블록 포맷에 글리프만 더 싣는다(블록 상한 N ≤ 180 — 더 필요하면 섹터를 늘린다).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import font
import hook
import sysstrings
from hook import Asm

MODULE_REL = 450
CODE_OFF = 0x7E4F  # 모듈 오프셋 — 뱅크 0x6B 끝 0 구간(원판 0, 433B)
# 🔴 **$A000 창(MPR5)으로 부른다** — 모듈 입구에서는 MPR3~6 = 0x69·0x6A·0x6B·0x6C(MPR4 가 아직 0x6A 라 $9E4F 는 다른 뱅크다 —
#   처음에 $9E4F 로 불렀다가 입구에서 죽었다). 글자를 그리는 동안엔 MPR4·MPR5 둘 다 0x6B 라 $A000 창도 같은 자리다(2026-10-14 실측).
CODE_ADDR = 0xA000 + (CODE_OFF - 0x6000)  # $BE4F
CODE_ROOM = 0x8000 - CODE_OFF  # 433
CALL_SITES = ((0x7A8C, 0x20), (0x7B76, 0x4C))  # (모듈 오프셋, JSR/JMP 오피코드) — 원래 `xx 60 E0`
INIT_SITE = 0x14  # 모듈 입구의 `JSR $404D` — 뒤에서 `JMP $404D` 로 이어 준다
INIT_NEXT = 0x404D
GLYPH_BANK = 0x78  # 확장 RAM 뱅크 0x78~0x7B — 도감 그림이 0x6D 부터 위로 자란다(마지막 장은 0x6F 까지, 2026-10-14 실측: 0x6E~0x6F 에 두었던 글리프가 깨졌다)
GLYPH_REL = 466  # 디스크 빈 섹터(원판 0, 466~481 16개) — 오마케 모듈(450~465) 바로 뒤
GLYPH_SECTORS = 16  # 32KB = 글리프 1024칸
LEADS = (font.LEAD0, 0xF8)  # F0 ≤ 리드 < F8 — 오마케 전용 코드 공간(리드 8 × 220 = 1760칸)
STRIDE = 32
ASK_OFF, ASK_LEN = 0x498B, 16  # 도감 장 선택 질문(원문 8자 = 16B)


def _assemble() -> bytes:
    """미니 훅 + 입구 초기화 — 반환 바이트는 `CODE_ADDR` 에 놓인다. 호출부 둘이 가리키는 `OHOOK` 는 맨 앞."""
    a = Asm(CODE_ADDR)
    # ── OHOOK: EX_GETFNT 대체. 입력 `$F9`=리드 `$F8`=트레일 `$FA/$FB`=출력 32B 주소. ──
    #   코드 = 직접 색인: idx = (리드−F0)·220 + (트레일−24), 글리프 = 블록 앞에서 32B·idx(뱅크 0x6E 부터 이어 붙은 칸 — 8KB 에 256개).
    a.label("ohook")
    a.op("LDA", "zp", 0xF9)
    a.op("CMP", "imm", LEADS[0])
    a.op("BCC", "rel", "bios")
    a.op("CMP", "imm", LEADS[1])
    a.op("BCS", "rel", "bios")
    a.op("PHX")
    a.op("PHY")
    a.op("PHP")  # 부른 쪽의 I 플래그를 그대로 되돌린다
    a.op("SEI")
    a.op("TMA", "tma", 3)
    a.op("PHA")
    a.op("LDA", "zp", 0xF8)
    a.op("SEC")
    a.op("SBC", "imm", font.TRAIL0)
    a.op("BCC", "rel", "miss")  # 트레일 < 24 — 우리 코드가 아니다
    a.op("STA", "zp", 0xEC)
    a.op("STZ", "zp", 0xED)
    a.op("LDA", "zp", 0xF9)
    a.op("SEC")
    a.op("SBC", "imm", LEADS[0])
    a.op("TAX")
    a.label("mul")  # idx += 220 · 리드 번호
    a.op("CPX", "imm", 0)
    a.op("BEQ", "rel", "mdone")
    a.op("LDA", "zp", 0xEC)
    a.op("CLC")
    a.op("ADC", "imm", font.PER_LEAD)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0xED)
    a.op("ADC", "imm", 0)
    a.op("STA", "zp", 0xED)
    a.op("DEX")
    a.op("BRA", "rel", "mul")
    a.label("mdone")
    for _ in range(5):  # ·32
        a.op("ASL", "zp", 0xEC)
        a.op("ROL", "zp", 0xED)
    a.op("LDA", "zp", 0xED)
    for _ in range(5):
        a.op("LSR")  # 상위 → 8KB 뱅크 번호
    a.op("CLC")
    a.op("ADC", "imm", GLYPH_BANK)
    a.op("TAM", "tam", 3)
    a.op("LDA", "zp", 0xED)
    a.op("AND", "imm", 0x1F)
    a.op("ORA", "imm", 0x60)  # $6000 창
    a.op("STA", "zp", 0xED)
    a.op("LDY", "imm", 0)
    a.label("cp")
    a.op("LDA", "izpy", 0xEC)
    a.op("STA", "izpy", 0xFA)
    a.op("INY")
    a.op("CPY", "imm", STRIDE)
    a.op("BNE", "rel", "cp")
    a.op("PLA")
    a.op("TAM", "tam", 3)
    a.op("PLP")
    a.op("PLY")
    a.op("PLX")
    a.op("LDA", "imm", 0)
    a.op("RTS")
    a.label("miss")  # 우리 코드가 아니다 — 원상 복구하고 BIOS 로
    a.op("PLA")
    a.op("TAM", "tam", 3)
    a.op("PLP")
    a.op("PLY")
    a.op("PLX")
    a.label("bios")
    a.op("JMP", "abs", 0xE060)
    # ── OINIT: 모듈 입구 `JSR $404D` 자리 — 글리프 블록을 뱅크 0x6E 에 올린다. $F8~$FF·MPR3~6 은 저장·복원. ──
    a.label("oinit")
    for m in (3, 4, 5, 6):
        a.op("TMA", "tma", m)
        a.op("PHA")
    a.op("LDX", "imm", 0)
    a.label("sv")
    a.out += bytes([0xB5, 0xF8])  # LDA $F8,X
    a.op("PHA")
    a.op("INX")
    a.op("CPX", "imm", 8)
    a.op("BNE", "rel", "sv")
    a.label("rd")
    for zp, val in (
        (0xF8, GLYPH_SECTORS),
        (0xF9, 0),
        (0xFA, GLYPH_BANK),
        (0xFB, 0),
        (0xFC, GLYPH_REL >> 16),
        (0xFD, (GLYPH_REL >> 8) & 0xFF),
        (0xFE, GLYPH_REL & 0xFF),
        (0xFF, 6),
    ):
        a.op("LDA", "imm", val)
        a.op("STA", "zp", zp)
    a.op("JSR", "abs", 0xE009)  # CD_READ — 오프닝·모듈 자신의 적재와 같은 규약(_dh=6, _bl=뱅크)
    a.op("CMP", "imm", 0)
    a.op("BNE", "rel", "rd")
    a.op("LDX", "imm", 8)
    a.label("rs")
    a.op("DEX")
    a.op("PLA")
    a.out += bytes([0x95, 0xF8])  # STA $F8,X
    a.op("CPX", "imm", 0)
    a.op("BNE", "rel", "rs")
    for m in (6, 5, 4, 3):
        a.op("PLA")
        a.op("TAM", "tam", m)
    a.op("JMP", "abs", INIT_NEXT)
    code = a.bytes()
    return code, a.labels["ohook"], a.labels["oinit"]


# `CPX imm` 은 hook.OPS 에 없어 여기서 보탠다(오프닝 모듈이 `zpx` 를 보태는 것과 같은 방식).
hook.OPS.setdefault(("CPX", "imm"), 0xE0)
hook.OPS.setdefault(("CLC", "imp"), 0x18)
hook.OPS.setdefault(("ADC", "imm"), 0x69)


# 🔴 **오마케 문구는 픽셀 줄(proportional)로 짠다 — 공백·구두점은 반각**(마스터 10-14 「공백은 반각이 규칙」). 오마케 렌더러는 글자마다 12px 칸을
#   고정으로 먹어 공백 코드(`81 40`)가 12px 이고 `.`·`,` 도 12px 이다. 렌더러는 BIOS 쪽이라 코드로 줄일 길이가 없다. 그래서 **글자(한글·ASCII)로 된
#   덩이를 픽셀로 이어 붙여(공백 6px · 구두점 4~6px) 12px 칸으로 다시 잘라**, 칸마다 이 모듈 전용 글리프를 만든다. 칸 글리프는 같으면 하나로 합치고
#   만난 순서대로 번호(idx)를 매긴다 — 코드 = (리드 F0+idx//220, 트레일 24+idx%220). 전각 SJIS 로 적히는 글자(`・` 등)는 BIOS 에 맡긴다(덩이를 끊는다).
_CELLS: dict[bytes, int] = {}  # 칸 글리프(24B) → idx
BLANK_CELL = b"\x81\x40"  # 빈 칸은 BIOS 전각 공백
ADV = {" ": 6, ".": 4, ",": 4, "!": 4, ":": 4, "·": 4, "?": 6}  # 그 밖(한글·영문 등)은 12


def _adv(ch: str) -> int:
    return ADV.get(ch, 12)


def _code(g: bytes) -> bytes:
    idx = _CELLS.setdefault(g, len(_CELLS))
    lead = LEADS[0] + idx // font.PER_LEAD
    assert lead < LEADS[1], (
        f"오마케 칸 글리프가 코드 공간({(LEADS[1] - LEADS[0]) * font.PER_LEAD})을 넘었다"
    )
    assert (len(_CELLS)) * STRIDE <= GLYPH_SECTORS * common.USER, (
        f"오마케 글리프 {len(_CELLS)}칸 > 블록 {GLYPH_SECTORS}섹터"
    )
    return bytes([lead, font.TRAIL0 + idx % font.PER_LEAD])


def _flush(rows: list[int], width: int) -> bytes:
    if not width:
        return b""
    pad = -width % 12
    rows = [r << pad for r in rows]
    width += pad
    cells = [[(r >> (width - 12 * (k + 1))) & 0xFFF for r in rows] for k in range(width // 12)]
    while cells and not any(cells[-1]):
        cells.pop()  # 꼬리의 빈 칸은 안 쓴다
    out = bytearray()
    for c in cells:
        out += _code(b"".join((v << 4).to_bytes(2, "big") for v in c)) if any(c) else BLANK_CELL
    return bytes(out)


def px_width(text: str) -> int:
    return sum(_adv(ch) for ch in text)


# 합자 「다.」 — 12px 한 칸에 「다」+마침표(2026-10-15 마스터: 도감 거북 괴물 한 줄이 156px 를 4px 넘는다). 「다」 글리프는 가로 11px 라 오른쪽 12번째 열이 비어 있고, 거기에 지금 마침표와 같은 높이의 점 하나를 얹는다.
# ⚠ 도감 한 레코드(`DEX_LIGATURE`)에서만 쓴다 — 다른 줄 끝 「다.」 는 그대로다.
LIGATURE = "\ue000"
DEX_LIGATURE = {28: "다."}  # 레코드 번호 → 그 줄 끝에서 합자로 바꿀 말(거북 괴물)
_DOT_ROW = 10  # 마침표 점의 행(font.glyph(".") 와 같은 높이)


def _ligature_glyph() -> bytes:
    g = font.glyph("다")
    rows = [int.from_bytes(g[2 * y : 2 * y + 2], "big") >> 4 for y in range(12)]
    assert not rows[_DOT_ROW] & 1, "「다」 글리프 12번째 열이 비어 있지 않다"
    rows[_DOT_ROW] |= 1
    return b"".join((r << 4).to_bytes(2, "big") for r in rows)


def dex_lines(i: int, text: str) -> list[str]:
    """도감 레코드 i 의 설명 줄들 — 합자 레코드는 끝 「다.」 를 합자 한 글자로 바꾼 뒤 어절 단위로 나눈다."""
    suffix = DEX_LIGATURE.get(i)
    if suffix:
        assert text.endswith(suffix), f"합자 레코드 {i} 끝이 {suffix!r} 가 아니다"
        text = text[: -len(suffix)] + LIGATURE
    return wrap_words(text)


def encode_item(text: str, table: dict[str, bytes] | None = None) -> bytes:
    """오마케 문구 → 바이트. 글자 덩이는 픽셀로 이어 붙인 칸 글리프, 그 밖(`・`·전각 기호)은 cp932 그대로. `table`(본 게임 코드표)은 안 쓴다."""
    out = bytearray()
    rows = [0] * 12
    width = 0
    for ch in text:
        if ch not in (" ", LIGATURE) and not font.needs_glyph(ch):
            out += _flush(rows, width) + ch.encode("cp932")
            rows, width = [0] * 12, 0
            continue
        w = _adv(ch)
        g = None if ch == " " else (_ligature_glyph() if ch == LIGATURE else font.glyph(ch))
        for y in range(12):
            v = (int.from_bytes(g[2 * y : 2 * y + 2], "big") >> 4) if g else 0
            rows[y] = (rows[y] << w) | (v >> (12 - w) if w < 12 else v)
        width += w
    return bytes(out + _flush(rows, width))


def wrap_words(text: str, cap_px: int = 156) -> list[str]:
    """어절 단위로 줄을 나눈다(명시 `\n` 은 그대로). 렌더러 자동 줄바꿈(13~14자)에 안 닿게 한 줄 폭을 `cap_px`(13칸) 이하로 둔다."""
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            cand = word if not cur else cur + " " + word
            if cur and px_width(cand) > cap_px:
                lines.append(cur)
                cur = word
            else:
                cur = cand
        lines.append(cur)
    return lines


def build(table: dict[str, bytes], extras: dict, dex=None) -> tuple[bytes, int, int, bytes, int]:
    """(코드, ohook 주소, oinit 주소, 글리프 블록, 칸 수). 문구(extras)와 도감(dex 레코드)을 먼저 모두 짜서 칸 번호를 확정한 뒤 블록을 만든다."""
    code, ohook, oinit = _assemble()
    assert len(code) <= CODE_ROOM, f"오마케 훅 {len(code)}B > {CODE_ROOM}B"
    for key, items in extras.items():
        if not key.startswith("_"):
            for t in items:
                encode_item(t)  # 칸 번호 배정(sysbuild 가 먼저 불렀으면 이미 있다)
    if dex is not None:
        dex_bytes(dex)
    block = bytearray()
    for g in _CELLS:
        block += g + b"\0" * (STRIDE - font.GLYPH_BYTES)
    cap = GLYPH_SECTORS * common.USER
    assert len(block) <= cap, f"오마케 글리프 블록 {len(block)}B > {cap}B"
    return code, ohook, oinit, bytes(block) + b"\0" * (cap - len(block)), len(_CELLS)


# ── 몬스터 도감 ─────────────────────────────────────────────────────────────────────────
# 모듈 rel 459~463 에 레코드 88개가 이어져 있다: `1F 이름 04 01 [HP 칸: 전각 공백 + ＨＰ + 전각 숫자] 01 05 설명줄 01 설명줄 … 06`. 앞(0x26B)에 포인터 표 88항목이 있다(아래 `dex_pointer_table`).
# 설명은 렌더러가 13~14칸에서 자동으로 접는다. 창에는 **4줄**까지 한 번에 보인다(2026-10-14 실측 —
# 5줄 이상이면 위로 밀린다). 이름은 정본(`shared/canon` 몬스터·인물·호칭), 설명은 `script/sys/dex.json` — 이 파일엔 한국어만 둔다.
DEX_REL, DEX_OFF, DEX_COUNT, DEX_MAX_LINES = 459, 0x31B, 88, 4
DEX_GAP_END = 0x2448  # 레코드 뒤 0 구간 끝(그 뒤는 그림 자료) — 새 레코드가 길면 여기까지만 쓴다


def _dex_original() -> tuple[bytes, list[tuple[int, int]]]:
    """(rel 459~463 원본, [(레코드 시작, 끝+1)…])."""
    d = b"".join(common.track_data(DEX_REL + i, 1) for i in range(5))
    recs, pos = [], DEX_OFF
    while len(recs) < DEX_COUNT:
        i = d.index(b"\x1f", pos)
        j = d.index(b"\x06", i) + 1
        recs.append((i, j))
        pos = j
    assert recs[0][0] == DEX_OFF
    return d, recs


def dex_names() -> list[str]:
    """레코드마다 우리 이름 — 정본(canon)에서. 원문 가나는 읽기만 한다(문서·코드에 안 옮긴다)."""
    import battle
    import canon

    g = canon.nouns("ed1")["categories"]
    idx: dict[str, str] = {}
    for cat in ("monster", "person"):
        for k, v in g[cat].items():
            idx.setdefault(battle._norm(k), v)
    for k, v in canon.table("speaker", "ed1").items():
        idx.setdefault(battle._norm(k), v)
    d, recs = _dex_original()
    out = []
    for i, _j in recs:
        jp = d[i + 1 : d.index(b"\x04", i)].decode("cp932")
        kr = idx.get(battle._norm(jp))
        assert kr, f"도감 이름이 정본에 없다(레코드 {len(out)})"
        out.append(kr)
    return out


def dex_bytes(desc: list[str]) -> bytes:
    """도감 영역 새 바이트(레코드 88개, 원본 시작 자리부터). HP 칸은 원본 바이트 그대로."""
    return _dex_build(desc)[0]


def _dex_build(desc: list[str]) -> tuple[bytes, list[int]]:
    """(새 레코드 바이트, 레코드마다 새 시작 오프셋 — rel 459 스트림 기준)."""
    d, recs = _dex_original()
    assert len(desc) == DEX_COUNT, f"도감 설명 {len(desc)} ≠ {DEX_COUNT}"
    names = dex_names()
    out = bytearray()
    starts = []
    for n, ((i, j), kr, text) in enumerate(zip(recs, names, desc, strict=True)):
        starts.append(DEX_OFF + len(out))
        rec = d[i:j]
        hp = rec[rec.index(b"\x04\x01") + 2 : rec.index(b"\x01\x05")]
        lines = dex_lines(n, text)
        assert len(lines) <= DEX_MAX_LINES, (
            f"도감 설명 {len(lines)}줄 > {DEX_MAX_LINES}: {text[:12]}…"
        )
        body = b"\x01".join(encode_item(ln) for ln in lines)
        assert not set(body.replace(b"\x01", b"")) & {1, 4, 5, 6, 0x1F}, (
            "제어 바이트가 글자 안에 있다"
        )
        out += b"\x1f" + encode_item(kr) + b"\x04\x01" + hp + b"\x01\x05" + body + b"\x06"
    return bytes(out), starts


# 🔴 **레코드 앞에 포인터 표가 있다**(2026-10-14 마스터 「도감 깨진 데가 많다」로 찾았다 — 전엔 「표 없다」고 썼으나 틀렸다). 스트림 0x26B 부터 88항목 × 2B
#   (리틀엔디언 절대 주소 `$6800 + 스트림 오프셋`), 순서는 화면(장별) 순서이고 값은 레코드 시작이다(원판은 레코드 순서와 다르다 — 표가 순열이다).
#   레코드 길이를 바꾸면 표를 새 시작으로 다시 써야 한다 — 안 쓰면 첫 레코드(길이가 그대로 시작하는 곳) 말고는 포인터가 옛 자리라 이름이 엉뚱한 바이트에서 읽힌다.
DEX_PTR_OFF, DEX_PTR_BASE = 0x26B, 0x6800


def dex_pointer_table(desc: list[str]) -> bytes:
    """새 포인터 표 176B — 원판 표의 화면 순서(순열)를 그대로 두고 값만 새 레코드 시작으로."""
    d, recs = _dex_original()
    old_start = {DEX_PTR_BASE + i: k for k, (i, _j) in enumerate(recs)}
    starts = _dex_build(desc)[1]
    out = bytearray()
    for n in range(DEX_COUNT):
        t = int.from_bytes(d[DEX_PTR_OFF + 2 * n : DEX_PTR_OFF + 2 * n + 2], "little")
        out += (DEX_PTR_BASE + starts[old_start[t]]).to_bytes(2, "little")
    return bytes(out)


# 🔴 **오마케 목록엔 포인터 표가 있다**(2026-10-14 실측 — status 의 「포인터 표가 없다」는 틀렸다: 간격이 아니라 **절대 주소**(`$67C9` 꼴)다).
#   곡 목록 20항목은 모듈 +0x479D~0x47C6(화면 순서), 장 목록은 +0x492B~0x4938(장 6 + 「나가기」), 쪽 라벨은 +0x4963~0x4968.
#   한글 문자열은 길이가 달라 주소가 밀리므로 **표를 새 주소로 다시 쓴다**(안 쓰면 문자열 중간에서 읽기 시작해 글자가 깨진다 — 사운드 테스트에서 실제로 그랬다).
POINTER_TABLES = (
    (0x479D, 0x47C7),
    (0x492B, 0x4939),
    (0x4963, 0x4969),
)  # (모듈 오프셋 시작, 끝) — 16비트 LE 열


def _logical(off_in_458: int) -> int:
    """rel 458 안 오프셋 → 모듈이 보는 논리 주소(뱅크 0x6A 가 $6000 창)."""
    return 0x6000 + (sysstrings.EXTRAS_REL - MODULE_REL) * common.USER + off_in_458 - 0x4000


def pointer_fixes(table, extras) -> list[tuple[int, bytes, bytes]]:
    """[(모듈 오프셋, 원본 바이트, 새 바이트)] — 문구 덩이별로 항목의 옛 주소 → 새 주소를 대응시켜 표 열을 고친다."""
    orig = common.track_data(sysstrings.EXTRAS_REL, 2)
    mapping: dict[int, int] = {}
    for name, lo, hi in sysstrings.EXTRAS:
        items_old = []
        pos, st = lo, lo
        while pos < hi:
            if orig[pos] == 0:
                items_old.append(st)
                st = pos + 1
            pos += 1
        new_items = extras[name]
        assert len(new_items) == len(items_old), (name, len(new_items), len(items_old))
        cur = lo
        for st_old, text in zip(items_old, new_items, strict=True):
            mapping[_logical(st_old)] = _logical(cur)
            cur += len(encode_item(text, table)) + 1
    data = common.track_data(MODULE_REL, 20)
    out = []
    used = set()
    for a, b in POINTER_TABLES:
        for k in range(a, b, 2):
            old = int.from_bytes(data[k : k + 2], "little")
            if old in mapping:
                new = mapping[old]
                used.add(old)
                if new != old:
                    out.append((k, data[k : k + 2], new.to_bytes(2, "little")))
    # 곡 목록(20)과 장·쪽 목록의 항목은 전부 표에 있어야 한다 — 「메뉴 첫 줄」 둘(omake)만 표가 없다
    missing = [hex(m) for m in mapping if m not in used and m < 0x6900]
    assert not missing, f"포인터 표에 없는 곡 항목 {missing}"
    return out


def apply(f, table, extras, touched) -> str:
    from shared.disc import mode1

    dex = json.loads((common.GAME_DIR / "script" / "sys" / "dex.json").read_text(encoding="utf-8"))[
        "desc"
    ]
    code, ohook, oinit, block, ncells = build(table, extras, dex)
    T2 = common.T2_SECTOR

    def patch(off, new, expect, label):
        rel, o = MODULE_REL + off // common.USER, off % common.USER
        mode1.write_at(f, T2 + rel, common.USER, o, new, label=label, expect=expect)
        touched.append((T2 + rel, 1))

    # 1. 코드(모듈 +0x7E4F, 한 섹터 안 — 0x7800~0x7FFF)
    assert CODE_OFF // common.USER == (CODE_OFF + len(code) - 1) // common.USER
    patch(CODE_OFF, code, b"\0" * len(code), "omake hook code")
    # 2. 호출부 둘 → OHOOK, 입구 → OINIT
    for off, op in CALL_SITES:
        patch(
            off,
            bytes([op]) + ohook.to_bytes(2, "little"),
            bytes([op, 0x60, 0xE0]),
            f"omake call +0x{off:X}",
        )
    patch(INIT_SITE, b"\x20" + oinit.to_bytes(2, "little"), b"\x20\x4d\x40", "omake init call")
    # 2b. 포인터 표 다시 쓰기(문자열 길이가 달라져 주소가 밀린다)
    fixes = pointer_fixes(table, extras)
    for off, old, new in fixes:
        patch(off, new, old, f"omake pointer +0x{off:X}")
    # 2c. 도감 장 선택 창의 질문 한 줄(`08 06 08 <문구> 06` 의 문구 16B — 원문은 8자 전각) — 길이는 같아야 뒤 제어코드가 안 밀린다
    ask = encode_item(extras["ask"][0], table)
    ask += BLANK_CELL * (
        (ASK_LEN - len(ask)) // 2
    )  # 반각 공백으로 줄어든 만큼 빈 칸으로 채운다(뒤 제어코드가 안 밀리게)
    assert len(ask) == ASK_LEN, f"질문 문구 {len(ask)}B ≠ {ASK_LEN}B"
    patch(
        ASK_OFF,
        ask,
        common.track_data(MODULE_REL, 20)[ASK_OFF : ASK_OFF + ASK_LEN],
        "omake chapter question",
    )
    # 2d. 첫 메뉴 라벨 그림(rel 642~673 VRAM 덩어리)
    menu_msg = apply_menu_labels(f, table, extras, touched)
    # 2e. 몬스터 도감(레코드 88) — 원본 자리에서 새 길이로 다시 쓴다. 남는 옛 바이트는 0 으로, 넘치면 뒤 0 구간까지만
    d0, recs = _dex_original()
    new = dex_bytes(dex)
    old_end = recs[-1][1]
    room_end = DEX_OFF + len(new)
    assert room_end <= DEX_GAP_END, (
        f"도감 {len(new)}B — 영역 끝(0x{DEX_GAP_END:X})을 {room_end - DEX_GAP_END}B 넘는다"
    )
    end = max(old_end, room_end)
    assert not any(d0[old_end:end]), "도감 뒤 덮을 구간이 0 이 아니다"
    blob = new + b"\0" * (end - DEX_OFF - len(new))
    mode1.write_at(
        f,
        T2 + DEX_REL,
        common.USER * 5,
        DEX_OFF,
        blob,
        label="omake dex",
        expect=d0[DEX_OFF:end],
    )
    for k in range(DEX_OFF // common.USER, (end - 1) // common.USER + 1):
        touched.append((T2 + DEX_REL + k, 1))
    ptab = dex_pointer_table(dex)
    mode1.write_at(
        f,
        T2 + DEX_REL,
        common.USER * 5,
        DEX_PTR_OFF,
        ptab,
        label="omake dex pointer table",
        expect=d0[DEX_PTR_OFF : DEX_PTR_OFF + len(ptab)],
    )
    dex_msg = f" · 도감 {DEX_COUNT}건 {len(new)}B/원본 {old_end - DEX_OFF}B"
    # 3. 글리프 블록 → rel 466~481
    lba = T2 + GLYPH_REL
    mode1.write_user_data(f, lba, block, label="omake glyph block", expect=b"\0" * len(block))
    touched.append((lba, GLYPH_SECTORS))
    return (
        menu_msg
        + dex_msg
        + f" · 오마케 한글 훅(포인터 {len(fixes)}곳): 코드 {len(code)}B · 칸 글리프 {ncells}개 · 블록 {len(block)}B → 뱅크 0x{GLYPH_BANK:02X}~"
    )


# ── 오마케 첫 메뉴 라벨(그림) ───────────────────────────────────────────────────────────────
# 첫 화면의 「音楽を聞く」「モンスター図鑑を見る」는 글자가 아니라 **타일 그림**이다 — 모듈이 시작할 때 rel 642~673(32섹터 = VRAM 64KB
# 통째)을 VRAM 에 그대로 올리고(`CD_READ` 모드 FF), 그 덩어리에 타일 패턴과 BAT 가 다 들어 있다(2026-10-14: 타일 바이트를 디스크 전체에서
# 찾아 rel 649·650 에서 원본 VRAM 순서 그대로 찾았다). 글자 타일은 BAT 에 **한 번씩만** 쓰이는 전용 칸(0x1DB~0x229)이라 마음대로 덮어도 된다.
#   라벨1 = BAT 행 19·20 × 열 10~17 · 라벨2 = 행 21·22 × 열 10~24(행 21 열 16 은 공용 빈 타일 0x236 이라 잉크가 닿으면 빈 타일 0x237~ 로 갈아 끼운다).
#   바탕 색 2 · 글자 색 6(원본 그림에서 읽었다). 한글은 `font.glyph`(12×12)를 같은 세로 자리(행 2~13)에 놓는다.
VRAM_IMG_REL, VRAM_IMG_SECTORS = 642, 32
MENU_LABELS = (
    ("omake", 0, 19, 10, 8),
    ("omake", 1, 21, 10, 15),
)  # (extras 키, 항목, BAT 첫 행, 첫 열, 칸 수)
LABEL_BG, LABEL_INK = 2, 6
SPARE_TILE0 = 0x237  # BAT 에 안 쓰이고 비어 있는 타일 번호(원본 VRAM 에서 확인)
BLANK_TILE = 0x236
SPACE_PX = 6


def _tile_decode(w: list[int], t: int) -> list[list[int]]:
    base = t * 16
    px = [[0] * 8 for _ in range(8)]
    for y in range(8):
        lo, hi = w[base + y], w[base + 8 + y]
        for x in range(8):
            b = 7 - x
            px[y][x] = (
                ((lo >> b) & 1)
                | (((lo >> (8 + b)) & 1) << 1)
                | (((hi >> b) & 1) << 2)
                | (((hi >> (8 + b)) & 1) << 3)
            )
    return px


def _tile_encode(px: list[list[int]]) -> list[int]:
    words = [0] * 16
    for y in range(8):
        for x in range(8):
            v, b = px[y][x], 7 - x
            words[y] |= ((v & 1) << b) | (((v >> 1) & 1) << (8 + b))
            words[8 + y] |= (((v >> 2) & 1) << b) | (((v >> 3) & 1) << (8 + b))
    return words


def menu_label_edits(table, extras, vram: bytes):
    """원본 VRAM(64KB) → [(바이트 오프셋, 새 바이트)] — 라벨 타일 패턴과 BAT 한 칸. 원본 잉크 박스의 왼쪽 위에 맞춘다."""
    import struct

    w = list(struct.unpack("<32768H", vram))
    edits: list[tuple[int, bytes]] = []
    spare = SPARE_TILE0
    for key, idx, row0, col0, ncell in MENU_LABELS:
        text = extras[key][idx]
        # 원본 잉크 박스(색 6) 왼쪽·위 — 같은 자리에 맞춘다
        x0 = y0 = None
        for r in (row0, row0 + 1):
            for c in range(col0, col0 + ncell):
                t = w[r * 64 + c] & 0xFFF
                if t == BLANK_TILE:
                    continue
                for y, line in enumerate(_tile_decode(w, t)):
                    for x, v in enumerate(line):
                        if v == LABEL_INK:
                            px, py = (c - col0) * 8 + x, (r - row0) * 8 + y
                            x0 = px if x0 is None else min(x0, px)
                            y0 = py if y0 is None else min(y0, py)
        assert x0 is not None, f"라벨 잉크를 못 찾았다: {key}[{idx}]"
        W, H = ncell * 8, 16
        img = [[LABEL_BG] * W for _ in range(H)]
        x = x0
        for ch in text:
            if ch == " ":
                x += SPACE_PX
                continue
            g = font.glyph(ch)
            for gy in range(12):
                row = int.from_bytes(g[2 * gy : 2 * gy + 2], "big")
                for gx in range(12):
                    if row >> (15 - gx) & 1 and 0 <= y0 + gy < H and 0 <= x + gx < W:
                        img[y0 + gy][x + gx] = LABEL_INK
            x += 12
        assert x <= W, f"라벨 「{text}」 {x}px > {W}px"
        for r in (row0, row0 + 1):
            for c in range(col0, col0 + ncell):
                ty, tx = (r - row0) * 8, (c - col0) * 8
                blk = [img[ty + y][tx : tx + 8] for y in range(8)]
                bat_off = (r * 64 + c) * 2
                t = w[r * 64 + c] & 0xFFF
                if all(v == LABEL_BG for line in blk for v in line) and t == BLANK_TILE:
                    continue  # 빈 칸 그대로
                if t == BLANK_TILE:  # 공용 빈 타일 — 새 타일을 쓴다
                    t = spare
                    spare += 1
                    edits.append((bat_off, ((w[r * 64 + c] & 0xF000) | t).to_bytes(2, "little")))
                words = _tile_encode(blk)
                edits.append((t * 32, b"".join(v.to_bytes(2, "little") for v in words)))
    return edits


def apply_menu_labels(f, table, extras, touched) -> str:
    from shared.disc import mode1

    vram = common.track_data(VRAM_IMG_REL, VRAM_IMG_SECTORS)
    edits = menu_label_edits(table, extras, vram)
    import omake_art  # 제목·간판 그림 — 같은 VRAM 덩어리(빈 타일은 메뉴 라벨 다음부터)

    spare0 = max([off // 32 + 1 for off, _ in edits if off >= SPARE_TILE0 * 32] + [SPARE_TILE0])
    art = omake_art.edits(vram, spare0)
    buf = bytearray(vram)
    for off, new in edits + art:
        buf[off : off + len(new)] = new
    omake_art.check_vram(bytes(buf))  # 굽기 전에 도안과 픽셀까지 같은지
    edits += art
    lba0 = common.T2_SECTOR + VRAM_IMG_REL
    for off, new in edits:
        old = vram[off : off + len(new)]
        mode1.write_at(
            f,
            lba0,
            VRAM_IMG_SECTORS * common.USER,
            off,
            new,
            label=f"omake menu vram +0x{off:X}",
            expect=old,
        )
        for sct in range(off // common.USER, (off + len(new) - 1) // common.USER + 1):
            touched.append((lba0 + sct, 1))
    return f"오마케 메뉴 라벨 {len(MENU_LABELS)}개 · 제목·간판 그림 · VRAM 쓰기 {len(edits)}곳"


def main():
    extras = json.loads(
        (common.GAME_DIR / "script" / "sys" / "extras.json").read_text(encoding="utf-8")
    )
    dex = json.loads((common.GAME_DIR / "script" / "sys" / "dex.json").read_text(encoding="utf-8"))
    ex = {k: v for k, v in extras.items() if not k.startswith("_")}
    code, ohook, oinit, block, ncells = build({}, ex, dex["desc"])
    print(
        f"코드 {len(code)}B (여유 {CODE_ROOM - len(code)}B) · ohook ${ohook:04X} · oinit ${oinit:04X}"
    )
    print(f"칸 글리프 {ncells}개 · 블록 {len(block)}B · 도감 {len(dex_bytes(dex['desc']))}B")
    print(code.hex(" "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
