"""그래픽 문자 — 타이틀 메뉴 「はじめから/つづきから」는 글꼴이 아니라 **16×16 셀 그림**이다.

셀 폰트 0x19ACD0: 셀 = 40B 타일 4개(160B), 타일 = 8×10 저장(윗 8행만 씀), 셀 안 타일 순서 = 열-우선
(좌상·좌하·우상·우하). 타이틀은 셀 10 부터 54개를 VRAM 0x407~ 로 복사한다(`$12AB2` → `$1B40`).
셀 10~34 = はじめから × 5(밝기·강조 변형), 35~59 = つづきから × 5.

재삽입: 낱말을 80×16 비트맵(**네오둥근모 16px** 채움 + 팽창 테두리, 가운데 정렬)으로 그려 변형마다 원본 셀의
**채움/테두리 색 인덱스**를 그대로 써 5셀에 덮는다(같은 크기, 제자리). 정본은 `textmap/names.json`
의 `title_gfx` (jp 낱말 → ours).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import os

import hangul

FORCE_FILL = int(os.environ["MD_TITLE_FILL"]) if os.environ.get("MD_TITLE_FILL") else None
# 타이틀 낱말 글꼴은 **16px · 테두리 1px** 이다(2026-09-05 유저 확정).
# ⚠ 2026-09-07 에 17px·2px 로 키워 봤다가 **유저가 「더 이상해졌다」**고 해서 되돌렸다 —
# 화소 비율은 원판에 가까워졌지만 **화면이 나빠졌다.** 유저 눈이 판정이다.
# 🔴 그때 물린 것은 **17px + 2px 한 덩이**였다 — 유저 확인: 「전체 테두리를 굵게 하는 게 아니라
#    **한쪽 방향만** 줘서 입체감을 내라. 그게 어려우면 **그림자 없이 위쪽만 안 잘리게**」(2026-09-07).
#    ⇒ **획(채움)은 절대 안 건드린다** — 「굵다」의 정체가 그것이었다.
TITLE_PX = int(os.environ.get("MD_TITLE_PX", "16"))
TITLE_RING = int(os.environ.get("MD_TITLE_RING", "1"))
# 🔴 **자리는 「잉크 첫 행 맞춤」이 정본이다**(유저 판정 2026-09-07 — 「잔여물이 생기더라도 아래쪽에
#    생기는 게 나으니 이어하기 위로 좀 올려」). 이게 **올릴 수 있는 최대치**다 — 잉크가 이미 0행에
#    닿아서, 여기서 더 올리면 **위 테두리가 칸 밖으로 밀려나 `ㅇ`·`ㅎ` 위가 끊긴다.**
#    빈 행은 **아래 한 행(15행)**뿐이다.
# `MD_TITLE_STYLE="shadow"` 는 실험 손잡이 — 아래·오른쪽 그림자 한 겹(유저: 「더 적합하긴 한데」).
TITLE_STYLE = os.environ.get("MD_TITLE_STYLE", "shadow")
# 🔴 **칸의 빈 자리는 곧 칼이다**(MD 는 색 0 이 투명). 획 둘레만 1px 두르면 글자 **위로 칼날 무늬가
#    그대로 올라온다** — 유저가 「이게 나오면 안 된다」고 짚은 것이 그것이다(2026-09-07).
#    획 굵기는 안 건드리고 **검은 자리를 넓혀** 막는다.
#      "col"  글자가 있는 **열**을 위아래 끝까지 검정으로 (톱니 실루엣 · 낱말 밖은 그대로 투명) ← 정본
#      "full" 낱말 칸 **전체**를 검정으로 — 칼이 낱말 뒤에서 **끊겨** 보인다(2026-09-07 화면 확인, 기각)
#      "ceil" 글자가 있는 열의 **첫 획 위쪽만** 검정으로 (천장) — 위로 새는 칼날만 막는다
#    ⚠ "col" 도 유저가 물렸다 — 「칼 배경에 지저분한 검정색」(2026-09-07). 원판처럼 **한쪽 그림자**로 간다.
# ⚠ 획(채움)은 한 화소도 안 바뀐다 — **투명이던 자리만** 검정이 된다.
TITLE_PLATE = os.environ.get("MD_TITLE_PLATE", "")
# 그림자 방향 — 유저 「약간 대각선으로. ㅇ 부분 그림자가 약간 남쪽인 것 같아」(2026-09-07).
#   "dr"    아래 + 오른쪽 + 대각  (ㅇ 밑에 남쪽 띠가 생긴다)
#   "diag"  대각 한 칸만 (남동)
#   "rdiag" 오른쪽 + 대각 (남쪽 순수 성분 없음)
SHADOW_DIRS = {"dr": ((1, 0), (0, 1), (1, 1)), "diag": ((1, 1),), "rdiag": ((1, 0), (1, 1))}
TITLE_SHADOW = os.environ.get("MD_TITLE_SHADOW", "diag")
CELL_BASE = 0x19ACD0
CELL_SIZE = 160
TILE_STRIDE = 40
# 칼(커서)은 30px 움직이고 낱말 칸은 32px 움직인다 — 원판부터 아랫줄 칼이 윗줄보다 2px 위다. 가나는
# 위가 빽빽해 안 드러났지만 한글은 성겨서 티가 났다. **정본 = 아랫줄 칼을 2px 내려(`$E6`→`$E8`) 두 줄의
# 칼-글자 관계를 같게 한다** — 칼끝이 칸 안 3~7행, 「처음부터」와 같다(유저 판정 2026-09-07: 「2px 이 딱이다」,
# 0·1·2px 을 한 장에 놓고 골랐다). `MD_TITLE_CURSOR` 로 되돌려 볼 수 있다(원판 e6).
# 되짚은 자리: 커서 그리기 루틴 `$13342`, 아랫줄 Y `$13362`(스프라이트 표 사본 `$FF3150` 쓰기 BP 로 잡았다).
CURSOR_Y_LO = 0x13362  # move.w #$E6,d2 (4B)
CURSOR_Y_ORIG = bytes.fromhex("343c00e6")
CURSOR_Y_NEW = bytes.fromhex(
    "343c00" + os.environ.get("MD_TITLE_CURSOR", "e8")
)  # 정본 = 원판(e6). 실험 손잡이
# 🔴 **윗줄 조각** — 셀 60~64 는 「이어하기」 칸 바로 위 한 줄(플레인 B 13행, y104~111)에 깔리는 다섯 칸으로,
#    `つづきから` 가 16행 칸을 **위로 넘친 획**(づ 의 탁점·き 의 윗획 = 흰 2px, x150~151 y111)과 그 테두리를
#    담는다 — 가나 자리가 모자라 붙인 조각이다(유저 간파 2026-09-07). 한글은 안 넘치니 **통째로 비운다.**
#    되짚은 길: 층을 하나씩 꺼 봐서 그 흰 점이 글자 판(BG1)에 있음을 잡고, 플레인 B 12~13행의 타일
#    0x4CF~0x4E2 → 셀 60~64 로 거슬러 올라갔다. 『처음부터』 위에는 이런 줄이 없다(はじめから 는 안 넘친다).
STRIP = (60, 5)  # (첫 셀, 셀 수)
WORDS = [  # (이름, 첫 셀, 셀 수, 변형 수)
    ("start", 10, 5, 5),
    ("continue", 35, 5, 5),
]


def cell_pixels(d: bytes, c: int) -> list[list[int]]:
    """셀 → 16×16 색 인덱스."""
    g = [[0] * 16 for _ in range(16)]
    for k, (tx, ty) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
        off = CELL_BASE + c * CELL_SIZE + k * TILE_STRIDE
        for y in range(8):
            for x in range(8):
                b = d[off + y * 4 + x // 2]
                g[ty * 8 + y][tx * 8 + x] = (b >> 4) if x % 2 == 0 else (b & 15)
    return g


SHINE = (
    11,
    12,
    13,
    14,
)  # 글자 채움 — 비강조 팔레트에선 전부 흰색, 강조 팔레트에선 무지개(실측 kr7 대조)
OUTLINE = 1  # 1·2 는 검정(테두리·안쪽 그림자)


def colors_of(d: bytes, cells: range) -> tuple[list[int], int]:
    """(열별 채움 색, 테두리 색). 채움은 원본 띠의 같은 열에서 가장 흔한 11~14 를 따르고(강조 무지개 무늬가
    그대로 재현된다), 없으면 열마다 11→14 를 돈다. ⚠ 1·2 는 둘 다 검정이라 채움으로 쓰면 글자가 검게 뭉개진다
    (kr9·kr11 실측)."""
    import collections

    grids = [cell_pixels(d, c) for c in cells]
    cols = []
    for ci, g in enumerate(grids):
        for x in range(16):
            col = collections.Counter(g[y][x] for y in range(16) if g[y][x] in SHINE)
            cols.append(col.most_common(1)[0][0] if col else SHINE[((ci * 16 + x) // 4) % 4])
    return cols, OUTLINE


def ink_top(d: bytes, first: int, ncell: int) -> int:
    """원판 낱말의 **잉크(획 + 검정) 첫 행**. 두 낱말 다 0 이다 — 우리가 맞춰야 하는 것은 여기다."""
    for y in range(16):
        for c in range(first, first + ncell):
            if any(v in SHINE or v in (1, 2) for v in cell_pixels(d, c)[y]):
                return y
    return 0


def render_word(word: str, ncell: int, top_row: int | None = None) -> tuple[list, list]:
    """낱말 → (채움, 테두리) 16 × (ncell·16) 비트 행렬. 가로는 칸 가운데.

    `top_row` 를 주면 **획의 첫 행을 그 행에 맞춘다.** 정본은 **원판의 잉크 첫 행 + 1**
    (`ink_top()` — 두 낱말 다 0 이므로 우리 획은 1행부터, 테두리가 0행에 선다).

    🔴 **한때 원판의 「획」 첫 행에 맞췄고 그게 틀렸다**(2026-09-07). 원판은 두 낱말 다 **잉크
    (획+검정)가 0~15** 인데 `つづきから` 만 **획**이 0행까지 온다(가나 き·か·ら 의 위 끝).
    그 획 행에 우리 획을 맞추면 **테두리가 설 자리가 없어져** `ㅇ`·`ㅎ` 위가 평평하게 끊긴다 —
    유저가 네 회차 짚은 「위가 잘린다」가 이것이다.

    ⚠ **더 올릴 수는 없다** — 잉크가 이미 0행에 닿는다. 빈 행은 **아래 한 행(15행)**뿐이고,
    그게 유저 판정이다(「잔여물이 생기더라도 아래쪽에 생기는 게 낫다」).
    """
    w = ncell * 16
    fill = [[0] * w for _ in range(16)]
    # 타이틀은 네오둥근모(유저 2026-09-05). **17px 로 그린다** — 16px 은 잉크가 13행뿐이라
    # 그려지는 픽셀이 y0~14 로 **원판보다 한 행 짧고**, 칸 아래에 칼날이 드러났다(유저 지적 2026-09-07).
    # 17px 은 잉크 y1~14 · 테두리까지 **y0~15** 로 **원판(`つづきから` y0~15)과 자국이 같다.**
    # ⚠ 획을 밀어 올리는 길은 안 된다 — 위 테두리가 잘려 `ㅇ`·`ㅎ` 윗 곡선이 평평해진다(아래 검사).
    glyphs = [hangul.neodgm_fill(ch, 16, TITLE_PX) for ch in word if ch != " "]
    pitch = 16
    total = pitch * len(glyphs)
    x0 = max(0, (w - total) // 2)
    for i, g in enumerate(glyphs):
        for y in range(16):
            for x in range(16):
                if g[y][x] and x0 + i * pitch + x < w:
                    fill[y][x0 + i * pitch + x] = 1
    if top_row is not None:
        top = next((y for y in range(16) if any(fill[y])), None)
        if top is not None and top != top_row:
            n = top - top_row
            fill = (
                fill[n:] + [[0] * w for _ in range(n)]
                if n > 0
                else [[0] * w for _ in range(-n)] + fill[:n]
            )
    ring = hangul.ring(fill)
    for _ in range(TITLE_RING - 1):  # 테두리를 한 겹씩 더 두른다(원판 밀도에 맞춘다)
        merged = [[1 if (fill[y][x] or ring[y][x]) else 0 for x in range(w)] for y in range(16)]
        more = hangul.ring(merged)
        ring = [[1 if (ring[y][x] or more[y][x]) else 0 for x in range(w)] for y in range(16)]
    if TITLE_PLATE:
        # 획은 한 화소도 안 건드린다 — **투명이던 자리만** 검정으로 채운다.
        inked = [x for x in range(w) if any(fill[y][x] for y in range(16))]
        cols = range(w) if TITLE_PLATE == "full" else inked
        for x in cols:
            for y in range(16):
                if fill[y][x]:
                    if TITLE_PLATE == "ceil":
                        break  # 천장 — 첫 획 위까지만
                    continue
                ring[y][x] = 1
        if TITLE_PLATE == "ceil" and inked:
            # 🔴 **글자 사이 틈도 잇는다** — 틈 열(획이 없는 열)은 위 루프가 안 덮어 그 1~3px 위로 칼날
            # 흰 무늬가 비쳤다(유저 2026-09-07 동그라미). 양옆 글자 열의 첫 획 행 중 **아래쪽**까지 검정.
            # 원판도 위쪽 검정이 가나 사이를 잇는다.
            top = {x: next(y for y in range(16) if fill[y][x]) for x in inked}
            for x in range(inked[0], inked[-1] + 1):
                if x in top:
                    continue
                left = max((c for c in inked if c < x), default=None)
                right = min((c for c in inked if c > x), default=None)
                t = max(top[c] for c in (left, right) if c is not None)
                for y in range(t):
                    ring[y][x] = 1
    if TITLE_STYLE == "shadow":
        # **아래·오른쪽으로만** 한 겹(입체감). 사방으로 두르면 획이 굵어 보인다(유저가 물린 자리).
        # ⚠ 원판이 실제로 그렇다 — 채움에서 이어지는 검정 둘째 겹이 위/왼 0.6 대 아래/오른 0.9 다.
        ink = [[fill[y][x] or ring[y][x] for x in range(w)] for y in range(16)]
        for y in range(15, -1, -1):
            for x in range(w - 1, -1, -1):
                if ink[y][x] or fill[y][x]:
                    continue
                if any(
                    0 <= y - dy < 16 and 0 <= x - dx < w and ink[y - dy][x - dx]
                    for dx, dy in SHADOW_DIRS[TITLE_SHADOW]
                ):
                    ring[y][x] = 1
    return fill, ring


def cells_bytes(fill, ring, fill_cols: list[int], ring_c: int, ncell: int) -> list[bytes]:
    """비트 행렬 → 셀별 160B(40B 타일 4개, 열-우선; 타일 9·10행은 0)."""
    out = []
    for c in range(ncell):
        blob = bytearray()
        for tx, ty in ((0, 0), (0, 1), (1, 0), (1, 1)):
            t = bytearray(40)
            for y in range(8):
                for x in range(8):
                    gy, gx = ty * 8 + y, c * 16 + tx * 8 + x
                    v = fill_cols[gx] if fill[gy][gx] else (ring_c if ring[gy][gx] else 0)
                    if x % 2 == 0:
                        t[y * 4 + x // 2] |= v << 4
                    else:
                        t[y * 4 + x // 2] |= v
            blob += t
        out.append(bytes(blob))
    return out


def plan(d: bytes, names: dict) -> list[tuple[str, int, bytes]]:
    """정본 → 쓰기 [(라벨, 자리, 바이트)]."""
    writes = []
    tbl = names.get("title_gfx", {})
    for i, (name, first, ncell, nvar) in enumerate(WORDS):
        ours = tbl.get(str(i), {}).get("ours", "")
        if not ours:
            continue
        # 맞출 곳은 원판의 **잉크 첫 행**(둘 다 0)이다 — 그 위에 우리 테두리가 선다.
        fill, ring = render_word(ours, ncell, ink_top(d, first, ncell) + 1)
        # 🔴 **위가 닫혀 있나** — 획이 0행까지 올라오면 그 위 테두리가 **칸 밖으로 밀려나**
        # `ㅇ`·`ㅎ` 위 곡선이 평평하게 끊긴다(12배로 봐야 눈에 띈다). 원판은 두 낱말 다 **잉크가
        # 0~15** 이고 0행에도 검정이 24~25 있다 — 우리도 **0행에 테두리가 서 있어야** 한다.
        # ⚠ 앞서 이 검사를 「획이 0행에 닿는가」로 뒀다가 **원판과 같은 꼴까지 막았고**, 그 다음엔
        # 「원판보다 많이 닿는가」로 느슨하게 뒀다가 **정작 밀려난 테두리를 못 봤다**(2026-09-07,
        # 유저가 네 회차 짚었다). ⇒ 재는 것은 **「위 테두리가 있는가」**다.
        if not any(ring[0]):
            raise SystemExit(
                f"타이틀 낱말 {ours!r} 의 0행에 테두리가 없다 — 획이 칸 끝에 닿아 위가 잘린다"
            )
        if any(fill[15]):
            raise SystemExit(f"타이틀 낱말 {ours!r} 의 획이 15행에 닿는다 — 아래 테두리가 잘린다")
        for v in range(nvar):
            cells = range(first + v * ncell, first + (v + 1) * ncell)
            cols, rc = colors_of(d, cells)
            for c, blob in zip(cells, cells_bytes(fill, ring, cols, rc, ncell), strict=True):
                writes.append((f"gfx:{name}", CELL_BASE + c * CELL_SIZE, blob))
    # 윗줄 조각(셀 60~64)을 투명으로 — 우리 낱말은 칸을 안 넘친다.
    first, n = STRIP
    for c in range(first, first + n):
        writes.append(("gfx:strip", CELL_BASE + c * CELL_SIZE, bytes(CELL_SIZE)))
    # 커서(칼) 아랫줄 Y — 원본 명령을 확인하고 나서만 쓴다(쓰기 사전조건).
    if d[CURSOR_Y_LO : CURSOR_Y_LO + 4] != CURSOR_Y_ORIG:
        raise SystemExit(
            f"커서 Y 명령이 원본과 다르다 @{CURSOR_Y_LO:#x}: {d[CURSOR_Y_LO : CURSOR_Y_LO + 4].hex()}"
        )
    if CURSOR_Y_NEW != CURSOR_Y_ORIG:  # 정본은 원판 그대로 — 실험일 때만 쓴다
        writes.append(("gfx:cursor", CURSOR_Y_LO, CURSOR_Y_NEW))
    return writes


def allowed() -> dict[str, tuple[int, int]]:
    return {
        f"gfx:{name}": (
            CELL_BASE + first * CELL_SIZE,
            CELL_BASE + (first + ncell * nvar) * CELL_SIZE,
        )
        for name, first, ncell, nvar in WORDS
    } | {
        "gfx:cursor": (CURSOR_Y_LO, CURSOR_Y_LO + 4),
        "gfx:strip": (
            CELL_BASE + STRIP[0] * CELL_SIZE,
            CELL_BASE + (STRIP[0] + STRIP[1]) * CELL_SIZE,
        ),
    }


if __name__ == "__main__":
    import common

    d = common.rom()
    for name, first, ncell, nvar in WORDS:
        for v in range(nvar):
            cells = range(first + v * ncell, first + (v + 1) * ncell)
            print(
                f"  {name} 변형 {v}: 셀 {cells.start}~{cells.stop - 1} 색(채움, 테두리) = {colors_of(d, cells)}"
            )
