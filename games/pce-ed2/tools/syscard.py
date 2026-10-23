"""시스템 카드·백업 RAM 안내문(패키지 20 = rel 2562) — 한글 번역과 자체 글리프 후킹.

게임을 켤 때 시스템 카드 버전이 다르거나 백업 RAM 이 비었을 때 뜨는 네 메시지다(2026-10-15 실측: BRAM 앞 32바이트를 0 으로 쓰고 이어하기를 고르면 「초기화되지 않았습니다」가 뜬다).
  · 평문 SJIS 가 패키지 +0x12C3~0x13B9 에 있다. 메시지 하나 = 원본 칸 수 30(+ 끝 `FF FF`) = 62B(셋째만 29칸 = 60B), 네 개가 이어진다 — 줄바꿈은 **14칸**마다
    (시작 +0x12C3 · +0x1301 · +0x133F · +0x137B — 포인터 표가 다른 뱅크에 있어 **시작 위치는 그대로 둔다**).
  · 글자는 패키지 자체 렌더러(+0x1188~)가 한 칸씩 그린다: 첫 호출이 `($F9=리드, $F8=트레일)` 글자를 `JSR $E060`(BIOS EX_GETFNT)으로 16×16(32B) 글리프로 받아 `$300B` 에,
    둘째 호출이 `$9E` 가 가리키는 **`EF D3` 줄**(+0x13B9~, 칸마다 하나 — 평면 1 용, 비어 있는 줄이 아니다)의 글자를 `$302B` 에 받아 두 평면으로 타일을 만든다.
  → 첫 호출 이음매(+0x11B4)와 둘째 호출 이음매(+0x11D5) 둘을 우리 후킹으로 돌린다. 리드가 우리 것(`F0`)이면 글리프 표(24B = 12행)를 버퍼 4행째부터 복사하고, 아니면 BIOS 로 간다.
  · 칸은 16px 격자다. 한글 한 글자 = 한 칸, 낱말 사이 = 빈 칸(`81 40`), 숫자·영문은 반각 둘을 한 칸에 묶고, 끝 마침표는 앞 글자 칸 오른쪽(x 12~15)에 붙인다(칸 수를 15 안에 맞추려고).
빈 자리: 0xFF 1240B(+0x1B28) 에 후킹 루틴과 글리프 표(24B × n)를 둔다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asm
import common
import font

PKG_REL, PKG_SECTORS = 2562, 78
U = common.USER
BASE = 0x4000  # 패키지 오프셋 → 논리 주소(`$4000~$DFFF` 5개 뱅크 창)
MSG_OFF = (0x12C3, 0x1301, 0x133F, 0x137B)
MSG_LEN = (62, 62, 60, 62)  # 원본 메시지 바이트(끝 `FF FF` 포함) — 셋째는 29칸이다(다음 시작이 2B 앞). 우리는 28칸 + `FF FF` = 58B 만 쓴다
MSG_CELLS = 28  # 14 × 2줄 — 한 줄은 **14칸**이다(15번째 칸은 다음 줄로 넘어간다, 에뮬 실측 10-15). 원본은 30칸까지 잡혀 있어 뒤 두 칸은 안 쓴다
ROW = 14
SEAMS = (0x11B4, 0x11D5)  # 두 `JSR $E060` 의 피연산자
SEAM_OLD = bytes([0x60, 0xE0])
HOOK_OFF = 0x1B28
FREE_END = 0x2000  # 0xFF 런 끝(1240B)
BIOS_GETFNT = 0xE060
LEAD, TRAIL0 = font.LEAD0, font.TRAIL0
SPACE = "_"  # 빈 칸 표지(원본 전각 공백 `81 40`)

# 메시지 = [첫 줄, 둘째 줄] 평문. 마스터 10-15 「글자 간격 좁히기 — 한글은 붙여 쓰고 공백은 반각(0.5칸)」: 한글 12px 연속 · 공백 8px(칸 16px 의 절반) · 영문·숫자·`.` 8px.
# 줄은 연속 비트맵으로 그려 16px 칸으로 **잘라** 칸마다 24B 조각(표 항목)이 된다 — 고유 조각이 47 개 안이어야 빈 자리에 든다. 줄마다 시작 x(`X0`)는 가운데 ±6px 안에서 고유 조각이 가장 적게 고른 값(45개 — 빈 자리 47개 안).
MESSAGES = [
    ("버전 3.00 이상의 시스템", "카드를 사용해 주세요."),
    ("시스템 카드의 버전이", "다릅니다."),
    ("백업 RAM에", "빈 공간이 없습니다……"),
    ("백업 RAM이", "초기화되지 않았습니다."),
]
SPACE_ADV, NARROW_ADV, HANGUL_ADV, DOT_ADV = 8, 8, 12, 4  # 점·쉼표는 글리프가 왼쪽 2px 뿐이라 4px


GAP_LATIN_HANGUL = 2  # 반각 영문·숫자 바로 뒤에 한글이 오면 전진 폭 +2px(「RAM에」 의 M 과 「에」 가 붙어 보였다 — 마스터 10-22). 문안은 그대로, 조판만


def _hangul(ch: str) -> bool:
    return 0xAC00 <= ord(ch) <= 0xD7A3


def render(line: str):
    """줄 → (행 12개 정수[폭 1000px 안 왼쪽 정렬], 폭 px)."""
    rows = [0] * 12
    x = 0
    prev_latin = False
    for ch in line:
        if ch == " ":
            x += SPACE_ADV
            prev_latin = False
            continue
        if prev_latin and _hangul(ch):
            x += GAP_LATIN_HANGUL
        g = font.glyph(ch)
        for y in range(12):
            rows[y] |= (int.from_bytes(g[2 * y : 2 * y + 2], "big") >> 4) << (1000 - x - 12)
        x += DOT_ADV if ch in ".," else NARROW_ADV if ch in font.NARROW else HANGUL_ADV
        prev_latin = ch in font.NARROW and ch not in ".,"
    return rows, x


# 줄 가운데 맞춤(마스터 10-22 「카드 중앙정렬」): 줄마다 **글자 잉크의 가운데가 화면 가운데(x=128)** — 줄 끝 「.」「,」「…」 는 계산에서 뺀다(번역 규칙 2-8, 마스터 10-22
# 「문장끝 …은 계산하지 말고 정렬」 — 그 글자는 가운데에서 뒤로 매달린다). 14칸 줄의 칸 원점(화면 x)은 제품 롬 실화면으로 쟀다(비트맵을 칸 원점+X0 에 놓고 캡처와 픽셀이
# 0 어긋남으로 맞췄다) — 줄1 은 8(셋째 메시지만 24), 줄2 는 −8(셋째 메시지만 8).
ROW_ORIGIN = [(8, -8), (8, -8), (24, 8), (8, -8)]
CENTER_X = 128


def _ink_span(line: str) -> tuple[int, int]:
    rows, _w = render(line)
    cols = [x for x in range(1000) if any((r >> (1000 - x - 1)) & 1 for r in rows)]
    return cols[0], cols[-1] + 1


def x0_for(mi: int, r: int, line: str) -> int:
    l, rr = _ink_span(line.rstrip(".,…"))
    return round(CENTER_X - (l + rr) / 2) - ROW_ORIGIN[mi][r]


# 줄 시작 x(`ROW_ORIGIN` 기준 px). 이상값(`x0_for`)에서 **±4px 안**으로 골라 고유 24B 조각 수를 빈 자리 한도 47 개에 맞췄다(정확 탐색 — ±3 이내에는 47 개 안의 해가 없다,
# 편차 제곱합 최소 해). 이상값 대비 편차: −2 −1 +2 +4 / 0 +4 0 −4 (`test_syscard_layout` 이 지킨다).
X0 = [(45, 73), (61, 116), (70, 68), (86, 68)]


def line_cells(line: str, x0: int) -> list:
    """줄 → 14칸(빈 칸 = SPACE · 조각 = 24B)."""
    rows, w = render(line)
    assert x0 + w <= 14 * 16, (line, x0, w)
    out = [SPACE] * 14
    sh = x0 % 16
    for k in range((w + sh + 15) // 16):
        cell = [((rows[y] >> (1000 - 16 * (k + 1) + sh)) & 0xFFFF) for y in range(12)]
        if any(cell):
            out[x0 // 16 + k] = b"".join(r.to_bytes(2, "big") for r in cell)
    return out


def cell_bitmap(spec: bytes) -> bytes:
    assert len(spec) == 24
    return spec


def cells_of(msg, mi: int = 0) -> list:
    """두 줄 → 28칸 목록(`mi` = 메시지 번호 — 줄 시작 x 를 고른다)."""
    out = []
    for row, x0 in zip(msg, X0[mi], strict=True):
        out += line_cells(row, x0)
    assert len(out) == MSG_CELLS
    return out


def glyph_set():
    specs = sorted({c for mi, m in enumerate(MESSAGES) for c in cells_of(m, mi) if c != SPACE})
    return specs, {sp: k for k, sp in enumerate(specs)}


def encode(msg, idx, mi: int = 0, nbytes=2 * MSG_CELLS + 2) -> bytes:  # nbytes = 우리가 쓰는 길이
    out = bytearray()
    cs = cells_of(msg, mi)
    keep = (nbytes - 2) // 2
    assert all(c == SPACE for c in cs[keep:]), (msg, nbytes)  # 줄인 칸은 빈 칸뿐이어야 한다
    for c in cs[:keep]:
        out += b"\x81\x40" if c == SPACE else bytes([LEAD, TRAIL0 + idx[c]])
    return bytes(out) + b"\xff\xff"


def hook_code(table_addr: int) -> bytes:
    """리드 `F0` 이면 글리프 표에서 24B 를 버퍼 4행째부터 복사(나머지 행은 0), 아니면 BIOS 로. $EC/$ED 는 저장·복원한다."""
    a = asm.Asm(BASE + HOOK_OFF)
    a.op("LDA", "zp", 0xF9)
    a.op("CMP", "imm", LEAD)
    a.op("BNE", "rel", "orig")
    a.op("LDA", "zp", 0xF8)
    a.op("SEC")
    a.op("SBC", "imm", TRAIL0)  # A = 글리프 번호
    a.op("LDX", "zp", 0xEC)
    a.op("PHX")
    a.op("LDX", "zp", 0xED)
    a.op("PHX")
    a.op("STA", "zp", 0xEC)
    a.op("STZ", "zp", 0xED)
    a.op("ASL", "zp", 0xEC)
    a.op("ROL", "zp", 0xED)  # 2k
    a.op("CLC")
    a.op("ADC", "zp", 0xEC)  # A = k (이전 값 그대로)
    a.op("STA", "zp", 0xEC)
    a.op("BCC", "rel", "m3")
    a.op("INC", "zp", 0xED)  # 3k
    a.label("m3")
    for _ in range(3):
        a.op("ASL", "zp", 0xEC)
        a.op("ROL", "zp", 0xED)  # 24k
    a.op("CLC")
    a.op("LDA", "zp", 0xEC)
    a.op("ADC", "imm", table_addr & 0xFF)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0xED)
    a.op("ADC", "imm", table_addr >> 8)
    a.op("STA", "zp", 0xED)
    a.op("LDY", "imm", 31)
    a.op("CLA")
    a.label("clr")
    a.op("STA", "izpy", 0xFA)
    a.op("DEY")
    a.op("BPL", "rel", "clr")
    a.op("LDA", "zp", 0xFA)
    a.op("CLC")
    a.op("ADC", "imm", 4)  # 버퍼 4행째(바이트 4)부터 — 12행 글리프를 16행 칸 가운데에
    a.op("STA", "zp", 0xFA)
    a.op("LDY", "imm", 23)
    a.label("cp")
    a.op("LDA", "izpy", 0xEC)
    a.op("STA", "izpy", 0xFA)
    a.op("DEY")
    a.op("BPL", "rel", "cp")
    a.op("LDA", "zp", 0xFA)
    a.op("SEC")
    a.op("SBC", "imm", 4)
    a.op("STA", "zp", 0xFA)
    a.op("PLX")
    a.op("STX", "zp", 0xED)
    a.op("PLX")
    a.op("STX", "zp", 0xEC)
    a.op("CLA")
    a.op("RTS")
    a.label("orig")
    a.op("JMP", "abs", BIOS_GETFNT)
    return a.bytes()


def writes(pkg: bytes):
    """[(선형 오프셋, 새 바이트, 기대 원본, 라벨)] — `pkg` = 원본 패키지."""
    specs, idx = glyph_set()
    table = b"".join(specs)
    hook0 = hook_code(BASE + HOOK_OFF)  # 길이만 잰다
    table_off = HOOK_OFF + len(hook0)
    hook = hook_code(BASE + table_off)
    assert len(hook) == len(hook0)
    assert table_off + len(table) <= FREE_END, (table_off, len(table))
    base = PKG_REL * U
    out = []
    for mi, (off, msg, n) in enumerate(zip(MSG_OFF, MESSAGES, MSG_LEN, strict=True)):
        assert 2 * MSG_CELLS + 2 <= n
        new = encode(msg, idx, mi)
        out.append((base + off, new, pkg[off : off + len(new)], "시스템 카드 안내문"))
    blob = hook + table
    out.append((base + HOOK_OFF, blob, b"\xff" * len(blob), "안내문 글리프 후킹 루틴 + 표"))
    seam = (BASE + HOOK_OFF).to_bytes(2, "little")
    for s in SEAMS:
        assert pkg[s : s + 2] == SEAM_OLD, hex(s)
        out.append((base + s, seam, SEAM_OLD, "안내문 EX_GETFNT 이음매"))
    return out, {"glyphs": len(specs), "hook": len(hook), "table": len(table)}


def apply(w) -> dict:
    pkg = common.track_data(PKG_REL, PKG_SECTORS)
    spans, info = writes(pkg)
    for linear, new, expect, label in spans:
        w.put(linear, new, expect, label)
    print(f"  시스템 카드 안내문: 글리프 {info['glyphs']}칸 · 후킹 {info['hook']}B · 표 {info['table']}B")
    return info
