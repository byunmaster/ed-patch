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
CELL_BASE = 0x19ACD0
CELL_SIZE = 160
TILE_STRIDE = 40
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


def render_word(word: str, ncell: int) -> tuple[list[list[int]], list[list[int]]]:
    """낱말 → (채움, 테두리) 16 × (ncell·16) 비트 행렬, 가운데 정렬. 글리프는 hangul.glyph_fill(14×14 셀)."""
    w = ncell * 16
    fill = [[0] * w for _ in range(16)]
    glyphs = [
        hangul.neodgm_fill(ch) for ch in word if ch != " "
    ]  # 타이틀은 네오둥근모 16px(유저 2026-09-05)
    pitch = 16
    total = pitch * len(glyphs)
    x0 = max(0, (w - total) // 2)
    for i, g in enumerate(glyphs):
        for y in range(16):
            for x in range(16):
                if g[y][x] and x0 + i * pitch + x < w:
                    fill[y][x0 + i * pitch + x] = 1
    return fill, hangul.ring(fill)


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
        fill, ring = render_word(ours, ncell)
        for v in range(nvar):
            cells = range(first + v * ncell, first + (v + 1) * ncell)
            cols, rc = colors_of(d, cells)
            for c, blob in zip(cells, cells_bytes(fill, ring, cols, rc, ncell), strict=True):
                writes.append((f"gfx:{name}", CELL_BASE + c * CELL_SIZE, blob))
    return writes


def allowed() -> dict[str, tuple[int, int]]:
    return {
        f"gfx:{name}": (
            CELL_BASE + first * CELL_SIZE,
            CELL_BASE + (first + ncell * nvar) * CELL_SIZE,
        )
        for name, first, ncell, nvar in WORDS
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
