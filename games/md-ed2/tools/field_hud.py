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
PITCH = 12

PUA_SUFFIX = {"부근": ["", ""], "입구": ["", ""]}
PUA_DIR = {"동": "", "서": "", "남": "", "북": ""}

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
        hangul.CUSTOM_GLYPHS[pua] = _slice_single(_condensed_strip(ch, SPACE_PX))
    _registered = True


def space_tramp(at: int) -> bytes:
    """트램펄린 본체 — 원래 명령 둘(공백 쓰기는 이제 없다), 그리고 원래 흐름으로 복귀."""
    b = bytearray()
    b += struct.pack(">H", 0x244B)  # movea.l a3,a2
    b += struct.pack(">H", 0x43F9) + struct.pack(">I", SPACE_A1)  # lea.l $1ED10.l,a1
    b += struct.pack(">H", 0x4EF9) + struct.pack(">I", SPACE_RESUME)  # jmp $1EC72.l
    assert len(b) == SPACE_TRAMP_LEN, len(b)
    return bytes(b)


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
    return out


def chars() -> set[str]:
    """이 패치가 쓰는 글자 — `collect_chars()` 가 다른 문안과 상관없이 늘 구워 둔다.
    실제로 굽는 건 합성 글리프(PUA)뿐이다 — `_ensure_custom_glyphs()`가 비트맵을 채워야
    `needs_glyph()`가 코드를 배정할 게 있다."""
    _ensure_custom_glyphs()
    return {p for puas in PUA_SUFFIX.values() for p in puas} | set(PUA_DIR.values())


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
