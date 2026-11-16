"""필드 HUD 지명 뒷말(부근·입구) · 방위(동서남북) — 텍스트맵을 거치지 않는다. md-ed1 `field_hud.py` 의 ED2 판.

    python3 tools/field_hud.py --check   # 여덟 자리(+공백·정렬 자리)가 원본과 같은 값인지 검산

ED2 는 ED1 과 **같은 루틴**이 +0x4378 에 있다(ED1 $1EC20 → ED2 $22F98 — 명령 바이트 일치로 대응을 확인했다. `--check` 가 매번 본다).
이유·마스터 판정(앞 공백 · 가운데 정렬 상수 · 콘덴스드 압축)은 ED1 문서가 정본이다 — `games/md-ed1/tools/field_hud.py`·`docs/devlog.md`.
여기엔 **ED2 에서 달라진 것만** 둔다: 주소(ED1 + 0x4378) · 트램펄린 자리(`FIELD_HUD_RESERVE`, build.py).
🔴 ED1 에서 마스터가 고른 값(앞 공백 6px · K=1 · 콘덴스드 갈무리11)을 **그대로** 옮겼다 — ED2 화면은 판정 대기다.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import hangul

SPACE_SITE = 0x22FE2  # movea.l a3,a2 (2B) + lea.l $1ED10,a1 (6B) — 방위·뒷말 공통 진입점
SPACE_SITE_LEN = 8
SPACE_RESUME = 0x22FEA  # 원래 흐름으로 되돌아갈 자리(공백 삽입 다음 원래 명령)
SPACE_A1 = 0x23088  # lea 가 원래 가리키던 곳("입구") — 트램펄린에서 복제한다
SPACE_TRAMP_LEN = 14  # movea(2)+lea(6)+jmp(6) — 공백은 이제 콘덴스드 그림 안에 있어 별도 write 없음

ALIGN_SITE = 0x230A8  # subq.b #2,d1(원본) — 가운데 정렬 앞 공백 계산의 상수. 즉값 1바이트만 바꾼다
ALIGN_PATCH = b"\x53\x01\xe2\x09"  # subq.b #1,d1(="K=1") + lsr.b #1,d1(원본 그대로)

# 월드맵 「X 입구·부근·방위」 둘째 루틴(0x22930~)의 이름 복사(0x22892, 불리는 곳은 이 루틴의 둘뿐)는 **앞 공백을 전부 건너뛰고** 접미(콘덴스드 22px)를 붙여
# 늘 왼쪽 정렬이었다(11-08 실측: 「루디아 입구」 왼 4px · 오른 30px). 레코드의 앞 공백은 이름만 기준으로 가운데 맞춘 값이라, **앞 공백 WORLD_SKIP 칸만 건너뛰고
# 나머지는 그대로 복사**하게 한다 — 접미 폭(≈22px ≈ 반각 3.5칸)의 반만큼 왼쪽으로 당겨 이름+접미가 칸 가운데에 온다. 다른 호출자 없음(bsr 둘뿐).
WORLD_SITE = 0x228B0  # cmpi.b #6,(a1) 부터 복사 루프 직전(0x228C6)까지 22B — 원래는 06 이 아닌 공백을 끝까지 건너뛰는 루프
WORLD_SITE_LEN = 22
WORLD_RESUME = 0x228C6  # move.b (a1)+,d0 — 복사 루프(첫 글자부터)
WORLD_RESERVE = 0xD0  # 트램펄린 칸 전체(build.FIELD_HUD_RESERVE) — 공백 트램펄린 14B + 월드 트램펄린 84B + 방위 붙임 트램펄린

# 월드 HUD 방위 둘(북동·남서 …) 붙여 쓰기(마스터 11-09 「북동 남서 등 방향은 띄어쓰기 없이 붙여써야해」) — 둘째 루틴의 마지막 복사(4B, 0x22AD8)가 방위 둘을 다 남긴 경우
# (플래그 d1 의 남북 비트 0·1 · 동서 비트 2·3 이 둘 다 서 있음)에만 둘째 글자(동·서)를 **앞 공백이 짧은 변형 글리프**로 바꾼다 — 첫째 글자 칸에 구운 앞 공백 6px(이름과의 띄움)가
# 둘째 칸에도 있어 「북 동」으로 벌어졌었다. 하나뿐일 땐 원래 글리프(앞 공백 6px)를 그대로 쓴다.
JOIN_SITE = 0x22AD8
JOIN_SITE_LEN = 24  # move.b d(a2),d(a3) × 4
JOIN_RESUME = 0x22AF0  # move.b #6,0(a3) — 종결자
JOIN_LEAD_PX = 2  # 변형 글리프 앞 공백 — 콘덴스드 전진 8px 에서 첫째 칸(6+8)이 14, 둘째 칸이 12 피치 뒤 시작이라 2px 이면 글자 사이 간격이 8px 전진과 같다
# (자리, 글자) — 즉값 이동/비교 명령의 피연산자 2B. 전부 같은 함수(`$1EC20`) 안. `글자`는
# PUA 코드를 찾는 키(아래 DIR_PUA)일 뿐, 실제로 이 글자 하나짜리 코드를 굽지는 않는다.
DIRECTIONS = [
    (0x22FB4, "서", "move.w #서,d6 — 서쪽 기본값"),
    (0x22FBE, "동", "move.w #동,d6 — 동쪽"),
    (0x22FD2, "북", "move.w #북,d3 — 북쪽 기본값"),
    (0x22FDC, "남", "move.w #남,d3 — 남쪽"),
    (0x2301C, "북", "cmpi.w #북,d3 — 북/남 갈림(캐시 플래그), 위 북 값과 같아야 한다"),
    (0x23040, "동", "cmpi.w #동,d6 — 동/서 갈림(캐시 플래그), 위 동 값과 같아야 한다"),
    # ── 둘째 루틴(0x22930~0x22AF0) — 같은 방위 즉값 넷과 뒷말 리터럴 둘. **ED1 에서는 따로 안 잡았던 자리**(ED2 census 로 찾았다, 마스터 10-12)
    (0x229F6, "북", "move.w #북,d0 — 둘째 루틴 북쪽"),
    (0x22A02, "남", "move.w #남,d0 — 둘째 루틴 남쪽"),
    (0x22A1E, "서", "move.w #서,d0 — 둘째 루틴 서쪽"),
    (0x22A2A, "동", "move.w #동,d0 — 둘째 루틴 동쪽"),
]
# (자리, 낱말) — 4B 리터럴(콘덴스드 슬라이스 코드 2개). 出典 위치는 표 0x23084(付近)·0x23088(入口).
SUFFIX = [
    (0x23084, "부근", "「부근」— 마을과 떨어졌을 때"),
    (0x23088, "입구", "「입구」— 마을 그 칸일 때"),
    (0x22B50, "입구", "둘째 루틴의 「입구」 리터럴(4B)"),
    (0x22B54, "부근", "둘째 루틴의 「부근」 리터럴(4B)"),
]

# ── 콘덴스드 합성 글리프 — PUA(U+E000~) 자리표시로 hangul.py 기존 파이프라인을 그대로 탄다 ──
CONDENSED_BDF = common.ROOT / "shared" / "fonts" / "Galmuri11-Condensed.bdf"
CONDENSED_ADVANCE = 8  # 콘덴스드 한글 1자 전진폭(BDF DWIDTH 실측, 전부 8)
SPACE_PX = 6  # 압축분 앞 공백(마스터 확정 2026-09-28 — 8px/꼬리0 은 우측여유 1px라 반려, 최종 6px)
CELL = hangul.CELL  # 14
DIR_LEAD_PX = SPACE_PX - 1  # 방위 글자 앞 공백 — 방위 하나일 때 이름+방위가 칸에서 왼 +1~+2px 쏠려(실측 31개) 1px 당긴다(마스터 11-09 「최대한 가운데」, 방위 둘은 둘째 글자가 제자리라 글자 사이만 1px 벌어진다)
PITCH = 12

PUA_SUFFIX = {"부근": ["", ""], "입구": ["", ""]}
PUA_DIR = {"동": "", "서": "", "남": "", "북": ""}
PUA_DIR2 = {"동": "", "서": ""}  # 방위 둘일 때 둘째 글자(앞 공백 짧음)

_cbdf_cache: dict | None = None


def _load_condensed() -> dict:
    global _cbdf_cache
    if _cbdf_cache is not None:
        return _cbdf_cache
    raw = {}
    lines = CONDENSED_BDF.read_text(encoding="utf-8", errors="replace").split("\n")
    i = 0
    while i < len(lines):
        if lines[i].startswith("ENCODING "):
            code = int(lines[i].split()[1])
            j = i
            while not lines[j].startswith("BBX"):
                j += 1
            bw, bh, bx, by = map(int, lines[j].split()[1:5])
            while lines[j].strip() != "BITMAP":
                j += 1
            rows = []
            for r in lines[j + 1 : j + 1 + bh]:
                r = r.strip()
                v = int(r, 16) if r else 0
                nb = len(r) * 4
                rows.append([(v >> (nb - 1 - x)) & 1 for x in range(bw)])
            raw[chr(code)] = (bw, bh, bx, by, rows)
            i = j + bh
        i += 1
    _cbdf_cache = raw
    return raw


def _condensed_strip(text: str, space_px: int) -> list[list[int]]:
    """「공백 + text」를 이어 그린 연속 채움 비트맵(높이 CELL, 폭 = space_px + 8*len(text))."""
    bdf = _load_condensed()
    _bw, _bh, _bx, _by, _ = bdf.get("가", (0, 0, 0, 0, []))
    ref = _by + _bh
    width = space_px + CONDENSED_ADVANCE * len(text)
    grid = [[0] * width for _ in range(CELL)]
    top = 1
    for k, ch in enumerate(text):
        bw, bh, bx, by, rows = bdf[ch]
        y0 = top + (ref - (by + bh))
        x_off = space_px + k * CONDENSED_ADVANCE
        for y in range(bh):
            ry = y0 + y
            if not 0 <= ry < CELL:
                continue
            for x in range(bw):
                rx = x_off + x + bx
                if 0 <= rx < width:
                    grid[ry][rx] = grid[ry][rx] or rows[y][x]
    return grid


def _slice_multi(strip: list[list[int]]) -> list[list[list[int]]]:
    """12px 피치 · 14px 폭 창으로 자른다 — 뒷말(부근/입구)용, 코드 여러 개."""
    width = len(strip[0])
    n = -(-width // PITCH)
    out = []
    for k in range(n):
        x0 = k * PITCH
        g = [[0] * CELL for _ in range(CELL)]
        for y in range(CELL):
            for x in range(CELL):
                sx = x0 + x
                if 0 <= sx < width:
                    g[y][x] = strip[y][sx]
        out.append(g)
    return out


def _slice_single(strip: list[list[int]]) -> list[list[int]]:
    """칸 하나(0~13열)만 잘라낸다 — 방위용. 코드 하나짜리 즉값이라 여러 칸으로 못 나눈다
    (내용을 칸 폭(14px) 안에 들어오게 미리 맞춘다 — `SPACE_PX+8` = 14, 정확히 한 칸)."""
    g = [[0] * CELL for _ in range(CELL)]
    width = len(strip[0])
    for y in range(CELL):
        for x in range(CELL):
            if x < width:
                g[y][x] = strip[y][x]
    return g


# 월드 HUD 길 A(위치 키 표, 접미 「입구」 22px 고정)에 오는 긴 이름 둘 — 보통 글자(12px)로는 이름+접미가 칸(90px)을 넘어 「구」가 잘린다(원판 가나는 들어간다).
# **이름을 접미와 같은 콘덴스드 8px 글자로 그린다**(마스터 11-09 「2 고쳐서 캡쳐로 보여줘」). 같은 레코드를 쓰는 마을 HUD 에서도 콘덴스드로 보인다(월드·마을이 레코드를 공유).
# 슬라이스 하나가 코드 하나(12px 피치) — 6글자 × 8px = 48px → 4코드.
CONDENSED_NAMES = {
    "사피아의호수": [chr(0xE100 + i) for i in range(4)],
    "그로스토스성": [chr(0xE110 + i) for i in range(4)],
}
CONDENSED_LEAD = 3  # 앞 공백 칸(마을 HUD 칸 90px 에서 이름 48px 이 가운데 — 반각 3칸 ≈ 19px)

_registered = False


def _ensure_custom_glyphs() -> None:
    """합성 글리프 8개를 `hangul.CUSTOM_GLYPHS`에 등록 — 코드 배정·표0 굽기는 기존 길을 탄다."""
    global _registered
    if _registered:
        return
    for word, puas in PUA_SUFFIX.items():
        slices = _slice_multi(_condensed_strip(word, SPACE_PX))
        if len(slices) != len(puas):
            raise SystemExit(
                f"뒷말 「{word}」 슬라이스 수가 예상과 다르다: {len(slices)} ≠ {len(puas)}"
            )
        for pua, g in zip(puas, slices, strict=True):
            hangul.CUSTOM_GLYPHS[pua] = g
    for ch, pua in PUA_DIR.items():
        hangul.CUSTOM_GLYPHS[pua] = _slice_single(_condensed_strip(ch, DIR_LEAD_PX))
    for ch, pua in PUA_DIR2.items():
        hangul.CUSTOM_GLYPHS[pua] = _slice_single(_condensed_strip(ch, JOIN_LEAD_PX))
    for name, puas in CONDENSED_NAMES.items():
        slices = _slice_multi(_condensed_strip(name, 0))
        if len(slices) != len(puas):
            raise SystemExit(f"콘덴스드 이름 「{name}」 슬라이스 수가 예상과 다르다: {len(slices)} ≠ {len(puas)}")
        for pua, g in zip(puas, slices, strict=True):
            hangul.CUSTOM_GLYPHS[pua] = g
    _registered = True


def space_tramp(at: int) -> bytes:
    """트램펄린 본체 — 원래 명령 둘(공백 쓰기는 이제 없다), 그리고 원래 흐름으로 복귀."""
    b = bytearray()
    b += struct.pack(">H", 0x244B)  # movea.l a3,a2
    b += struct.pack(">H", 0x43F9) + struct.pack(">I", SPACE_A1)  # lea.l $1ED10.l,a1
    b += struct.pack(">H", 0x4EF9) + struct.pack(">I", SPACE_RESUME)  # jmp $1EC72.l
    assert len(b) == SPACE_TRAMP_LEN, len(b)
    return bytes(b)


def world_tramp() -> bytes:
    """접미 폭별 앞 공백 건너뛰기 — 월드 HUD 둘째 루틴이 접미를 붙이기 **전에** 이름을 복사하므로, 접미를 정하는 같은 RAM 값
    (`$FF344A` 거리 · `$FF344C`/`$FF344E` 두 축 거리, 0x22A3C~0x22AEA 가 읽는 그대로)으로 접미 종류를 미리 가른다.

    · 입구·부근(거리 < 5) · 첫째 호출 자리(0x2297C 바로 뒤 = 특수 지명, 늘 입구) → 콘덴스드 22px → 2칸 건너뜀
    · 방위 한 개(`c>>1 >= e` 또는 `e>>1 >= c`, 코드가 한 방위를 지우는 조건 그대로) → 14px → 1칸
    · 방위 둘 → 28px → 2칸
    건너뛴 칸 수 = 앞 공백 (레코드 값은 이름만 기준) 에서 뺀다 — 접미 폭의 반만큼 당겨 이름+접미가 칸 가운데로. d1 은 저장한다(복귀 뒤 쓴다)."""
    code = bytearray()
    labels: dict[str, int] = {}
    fix: list[tuple[int, str]] = []

    def op(*words: int) -> None:
        for w in words:
            code.extend(struct.pack(">H", w))

    def br(op_hi: int, label: str) -> None:  # 8비트 변위 분기 — 자리만 잡고 나중에 채운다
        fix.append((len(code), label))
        code.extend(bytes([op_hi, 0]))

    op(0x48E7, 0x4000)  # movem.l d1,-(a7)
    op(0x7001)  # moveq #1,d0 — 기본 2칸(dbra 횟수 = 칸 수 − 1)
    op(0x0CAF, 0x0002, 0x2980, 0x000C)  # cmpi.l #첫째 호출 복귀 주소,12(a7) — 복귀 주소는 0x22892 의 d0/a1 저장 8B + d1 저장 4B 위
    br(0x67, "do")  # beq.s do
    op(0x3239, 0x00FF, 0x344A)  # move.w $FF344A.l,d1
    op(0x0C41, 0x0005)  # cmpi.w #5,d1
    br(0x65, "do")  # bcs.s do — 입구·부근
    op(0x3239, 0x00FF, 0x344C, 0xE249)  # move.w $FF344C.l,d1 ; lsr.w #1,d1
    op(0xB279, 0x00FF, 0x344E)  # cmp.w $FF344E.l,d1
    br(0x64, "one")  # bcc.s one
    op(0x3239, 0x00FF, 0x344E, 0xE249)  # move.w $FF344E.l,d1 ; lsr.w #1,d1
    op(0xB279, 0x00FF, 0x344C)  # cmp.w $FF344C.l,d1
    br(0x65, "do")  # bcs.s do — 방위 둘
    labels["one"] = len(code)
    op(0x7000)  # moveq #0,d0 — 방위 하나: 1칸
    labels["do"] = len(code)
    op(0x0C11, 0x0020)  # cmpi.b #$20,(a1)
    br(0x66, "go")  # bne.s go
    op(0x5289)  # addq.l #1,a1
    fix.append((len(code), "do"))
    code.extend(struct.pack(">H", 0x51C8) + b"\0\0")  # dbra d0,do (변위는 아래서)
    labels["go"] = len(code)
    op(0x4CDF, 0x0002)  # movem.l (a7)+,d1
    op(0x4EF9)
    code.extend(struct.pack(">I", WORLD_RESUME))
    out = bytearray(code)
    for pos, lab in fix:
        tgt = labels[lab]
        if out[pos] == 0x51:  # dbra — 워드 변위(확장 워드 주소 기준)
            out[pos + 2 : pos + 4] = struct.pack(">h", tgt - (pos + 2))
        else:
            d = tgt - (pos + 2)
            assert 0 <= d < 128 or -128 <= d < 0, (lab, d)
            out[pos + 1] = d & 0xFF
    return bytes(out)


def join_tramp(cs) -> bytes:
    """방위 붙임 트램펄린 — 원래 4B 복사(a2 → -4(a3))를 하고, 방위가 둘 다 남았으면 둘째(동·서) 코드를 앞 공백 짧은 변형으로 바꾼 뒤 종결자 자리로 간다."""
    out = bytearray()
    fix: list[tuple[int, str]] = []
    labels: dict[str, int] = {}

    def w(*ws: int) -> None:
        for x in ws:
            out.extend(struct.pack(">H", x))

    def bs(op: int, lab: str) -> None:
        fix.append((len(out), lab))
        out.extend(bytes([op, 0]))

    for k in range(4):  # move.b (a2)+,-4+k(a3)
        w(0x175A, (0x10000 - 4 + k) & 0xFFFF)
    w(0x0801, 0)  # btst #0,d1
    bs(0x66, "ns")  # bne.s — 남북 비트 있음
    w(0x0801, 1)  # btst #1,d1
    bs(0x67, "done")  # beq.s — 남북 없음 → 하나뿐
    labels["ns"] = len(out)
    w(0x0801, 2)  # btst #2,d1
    bs(0x66, "both")
    w(0x0801, 3)  # btst #3,d1
    bs(0x67, "done")
    labels["both"] = len(out)
    for ch in ("동", "서"):
        c0, c1 = cs.encode_char(PUA_DIR[ch])[:2]
        a0, a1 = cs.encode_char(PUA_DIR2[ch])[:2]
        nxt = f"n{ch}"
        w(0x0C2B, c0, 0xFFFE)  # cmpi.b #hi,-2(a3)
        bs(0x66, nxt)
        w(0x0C2B, c1, 0xFFFF)  # cmpi.b #lo,-1(a3)
        bs(0x66, nxt)
        w(0x177C, a0, 0xFFFE)  # move.b #hi',-2(a3)
        w(0x177C, a1, 0xFFFF)  # move.b #lo',-1(a3)
        bs(0x60, "done")
        labels[nxt] = len(out)
    labels["done"] = len(out)
    w(0x4EF9)
    out.extend(struct.pack(">I", JOIN_RESUME))
    for pos, lab in fix:
        d = labels[lab] - (pos + 2)
        assert 0 <= d < 128, (lab, d)
        out[pos + 1] = d
    return bytes(out)


def plan(cs, tramp_at: int) -> list[tuple[str, int, bytes]]:
    """`cs` 는 `hangul.Charset` — 순환 임포트를 피해 타입은 안 박는다."""
    _ensure_custom_glyphs()
    out = []
    for i, (addr, ch, _why) in enumerate(DIRECTIONS):
        out.append((f"field-hud-dir:{i}", addr, cs.encode_char(PUA_DIR[ch])))
    for i, (addr, word, _why) in enumerate(SUFFIX):
        body = b"".join(cs.encode_char(pua) for pua in PUA_SUFFIX[word])
        out.append((f"field-hud-suffix:{i}", addr, body))
    out.append(("field-hud-space-tramp", tramp_at, space_tramp(tramp_at)))
    out.append(
        (
            "field-hud-space-site",
            SPACE_SITE,
            struct.pack(">H", 0x4EF9) + struct.pack(">I", tramp_at),
        )
    )
    out.append(("field-hud-align", ALIGN_SITE, ALIGN_PATCH))
    wt = tramp_at + SPACE_TRAMP_LEN
    code = world_tramp()
    assert SPACE_TRAMP_LEN + len(code) <= WORLD_RESERVE, (SPACE_TRAMP_LEN, len(code))
    out.append(("field-hud-world-tramp", wt, code))
    jt = wt + len(code)
    jc = join_tramp(cs)
    assert SPACE_TRAMP_LEN + len(code) + len(jc) <= WORLD_RESERVE, (len(code), len(jc))
    out.append(("field-hud-join-tramp", jt, jc))
    out.append(
        (
            "field-hud-join-site",
            JOIN_SITE,
            struct.pack(">H", 0x4EF9)
            + struct.pack(">I", jt)
            + b"\x4e\x71" * ((JOIN_SITE_LEN - 6) // 2),
        )
    )
    site = struct.pack(">H", 0x4EF9) + struct.pack(">I", wt)
    out.append(
        (
            "field-hud-world-site",
            WORLD_SITE,
            site + b"\x4e\x71" * ((WORLD_SITE_LEN - len(site)) // 2),
        )
    )
    return out


def chars() -> set[str]:
    """이 패치가 쓰는 글자 — `collect_chars()` 가 다른 문안과 상관없이 늘 구워 둔다.
    실제로 굽는 건 합성 글리프(PUA)뿐이다 — `_ensure_custom_glyphs()`가 비트맵을 채워야
    `needs_glyph()`가 코드를 배정할 게 있다."""
    _ensure_custom_glyphs()
    return {p for puas in PUA_SUFFIX.values() for p in puas} | set(PUA_DIR.values()) | set(PUA_DIR2.values()) | {p for v in CONDENSED_NAMES.values() for p in v}


ORIG = {
    0x22FB4: b"\x90\xbc",  # 西
    0x22FBE: b"\x93\x8c",  # 東
    0x22FD2: b"\x96\x6b",  # 北
    0x22FDC: b"\x93\xec",  # 南
    0x2301C: b"\x96\x6b",  # 北
    0x23040: b"\x93\x8c",  # 東
    0x229F6: b"\x96\x6b",  # 北(둘째 루틴)
    0x22A02: b"\x93\xec",  # 南
    0x22A1E: b"\x90\xbc",  # 西
    0x22A2A: b"\x93\x8c",  # 東
    0x22B50: b"\x93\xfc\x8c\xfb",  # 入口(둘째 루틴 리터럴)
    0x22B54: b"\x95\x74\x8b\xdf",  # 付近
    0x23084: b"\x95\x74\x8b\xdf",  # 付近
    0x23088: b"\x93\xfc\x8c\xfb",  # 入口
    SPACE_SITE: b"\x24\x4b\x43\xf9\x00\x02\x30\x88",  # movea.l a3,a2 + lea.l $23088,a1
    ALIGN_SITE: b"\x55\x01\xe2\x09",  # subq.b #2,d1 + lsr.b #1,d1
}


def check(d: bytes) -> None:
    for addr, orig in ORIG.items():
        got = d[addr : addr + len(orig)]
        if got != orig:
            raise SystemExit(
                f"필드 HUD 자리 {addr:#x} 가 예상과 다르다: {got.hex()} ≠ {orig.hex()}"
            )
    print(f"  필드 HUD 뒷말·방위 — 여덟 자리 원본과 일치 ({len(ORIG)}곳)")


if __name__ == "__main__":
    check(common.rom())
