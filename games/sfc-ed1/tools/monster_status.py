"""몬스터 상태 라벨(전투 화면 몬스터 HP 숫자 아래 빨간 글자) — 가나 스프라이트 타일을 한글 8×8 로 다시 굽는다.

파티 HUD 의 상태 라벨(`hud_status`)과 **다른 길**이다 — 몬스터 쪽은 BG 가 아니라 **스프라이트 4개**(8×8, 팔레트 7)로 그린다
(2026-10-18 마스터 「몬스터 상태 표시가 일본어(ちんもく)」, 라이브 OAM·VRAM 덤프로 확인 — `tools/lua/battle_sweep.lua BT_DUMPAT`).

  상태 번호 → 타일 번호 네 개: `$00:9D49` 부터 4바이트씩 여덟(`txa·asl·asl·tax·lda $009D49,x` → `$190A~$190D`)
  타일 번호 = (시트 줄 << 4) | 0xE  — 라벨용 스프라이트 시트 `$0C:8004`(4bpp 32B 타일, 줄 0~15)가 VRAM 스프라이트 열 E 로 올라간다.
  `AF` = 빈 타일(시트 밖).  번호별 원본 라벨(가나는 여기에만): 1 どく · 2 ねる · 3 こんらん · 4 ちんもく · 5 かえす · 6 まもる.

한글은 한 글자가 한 타일이라 낱말 둘이면 두 칸이다 — 한 글자 라벨은 둘째 칸, 두 글자 라벨은 둘째·셋째 칸(네 칸 가운데).
색: 원본 타일은 플레인0=검은 테두리 · 플레인1=빨간 속(팔레트 7: 1=검정 · 2=빨강) — 한글도 속은 빨강, 테두리는 한 칸 두른 검정.
도안은 파티 HUD 와 같은 `textmap/hud_status_8x8.txt` 를 쓴다(같은 낱말 · 같은 모양).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import hud_status

TABLE = 0x009D49
TABLE_ENTRIES = 8
SHEET = 0x0C8004
SHEET_ROWS = 16
BLANK = 0xAF
# 상태 번호 → 한글 라벨(원본 가나는 모듈 설명에만)
LABELS = {1: "독", 2: "잠", 3: "혼란", 4: "침묵", 5: "반사", 6: "방어"}
ORIG_TABLE = bytes.fromhex("afafafaf" "af8eaf9e" "af3eaf4e" "aebecebe" "febeee9e" "af5e6e7e" "afdeee4e" "afafafaf")  # fmt: skip
ORIG_ROW9 = bytes.fromhex(
    "0a041408281050205020281014080a0400000000000000000000000000000000"
)  # 시트 줄 9(원본 「く」) — 자리 확인용


def syllables() -> list[str]:
    out: list[str] = []
    for kr in LABELS.values():
        for c in kr:
            if c not in out:
                out.append(c)
    return out


def row_of(c: str) -> int:
    return syllables().index(c)


def tile_id(row: int) -> int:
    return (row << 4) | 0x0E


def new_table() -> bytes:
    t = bytearray(ORIG_TABLE)
    for n, kr in LABELS.items():
        ids = [BLANK] * 4
        for i, c in enumerate(kr):  # 한 글자: 둘째 칸 · 두 글자: 둘째·셋째 칸
            ids[1 + i] = tile_id(row_of(c))
        t[4 * n : 4 * n + 4] = bytes(ids)
    return bytes(t)


def tile_4bpp(rows: list[str]) -> bytes:
    """도안(8줄 × 8칸, `#`=글자) → 4bpp 32B. 플레인0=검은 테두리(한 칸 두른 둘레) · 플레인1=빨간 속 · 플레인2~3=0."""
    g = [sum(1 << (7 - x) for x, ch in enumerate(r) if ch == "#") for r in rows]
    out = bytearray()
    for y in range(8):
        near = 0
        for yy in (y - 1, y, y + 1):
            if 0 <= yy < 8:
                v = g[yy]
                near |= v | (v << 1) | (v >> 1)
        outline = near & ~g[y] & 0xFF
        out += bytes([outline, g[y]])
    return bytes(out) + bytes(16)


def bake(out: bytearray, rom: bytes) -> dict:
    to = common.snes2off(TABLE)
    if bytes(rom[to : to + 4 * TABLE_ENTRIES]) != ORIG_TABLE:
        raise SystemExit(
            f"몬스터 상태 표 `$00:9D49` 가 예상과 다르다: {bytes(rom[to : to + 32]).hex()}"
        )
    so = common.snes2off(SHEET)
    if bytes(rom[so + 9 * 32 : so + 10 * 32]) != ORIG_ROW9:
        raise SystemExit("몬스터 상태 시트 `$0C:8004` 줄 9 가 예상과 다르다")
    dots = hud_status.load()
    for c in syllables():
        r = row_of(c)
        out[so + r * 32 : so + r * 32 + 32] = tile_4bpp(dots[c])
    out[to : to + 4 * TABLE_ENTRIES] = new_table()
    return {"라벨": list(LABELS.values()), "글자": len(syllables())}


def patch_ranges() -> list[tuple[int, int]]:
    to = common.snes2off(TABLE)
    so = common.snes2off(SHEET)
    return [(to, to + 4 * TABLE_ENTRIES), (so, so + 32 * len(syllables()))]
