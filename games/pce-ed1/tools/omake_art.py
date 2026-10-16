"""오마케의 큰 그림 둘 — 첫 메뉴 제목(BG 타일)과 도감 간판(스프라이트) — 마스터 도트판 도안을 그대로 굽는다.

    python3 tools/omake_art.py --check <ed1.iso>    # 구운 이미지를 되읽어 도안 텍스트와 대조

둘 다 **rel 642~673 VRAM 덩어리**(64KB, 모듈이 시작할 때 VRAM 에 통째로 올린다) 안에 있다 — 메뉴 라벨(omake_font)과 같은 덩어리.
- 제목 = BAT 행 6~15 × 열 5~27(23×10칸, 184×80px), 팔레트 0 · 글자 색 4(노랑) · 바탕 색 2. 장식이 걸친 **잠금 칸 10곳**은 원판 그대로.
  칸마다 새 8×8 을 만들어 같은 모양은 한 타일로 합친다 — 타일은 원래 제목 전용 타일(공용 0x236 · 통째 글자 0x137 제외)을 먼저 쓰고,
  모자라면 메뉴 라벨 다음의 빈 타일(0x237~0x27F)을 쓴다.
- 간판 = 스프라이트 패턴 6장(32×64, 팔레트 12) 96×128 시트, 패턴 번호 0x180·0x1A0·0x1C0(위) / 0x190·0x1B0·0x1D0(아래).
  글자 자리를 나무색 12 로 깨끗이 비우고(`_sign_clean`) 마스터 도안(34×27, 시트 x6~39·y5~31)을 색 14 로 얹는다.
도안 텍스트 = `assets/graphics/omake_title.txt` · `omake_sign.txt`(정본, `#` 줄은 설명). 다듬지 않고 그대로 굽는다.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import omake_font as O

ART = common.GAME_DIR / "assets" / "graphics"
TITLE_TXT, SIGN_TXT = ART / "omake_title.txt", ART / "omake_sign.txt"

TITLE_AT = (6, 5, 10, 23)  # BAT (행, 열, 행 수, 열 수)
TITLE_LOCKED = {(0, 14), (0, 15), (8, 5), (8, 6), (8, 7), (8, 22), (9, 5), (9, 6), (9, 7), (9, 22)}
T_BG, T_INK = 2, 4
T_ALL_INK, T_ALL_BG = 0x137, 0x236  # 공용 통째 타일
SPARE_END = 0x280  # 0x237~0x27F 까지만 비어 있다(원본 VRAM 에서 확인)

SIGN_SPRITES = [
    (0x180, 0, 0),
    (0x1A0, 32, 0),
    (0x1C0, 64, 0),
    (0x190, 0, 64),
    (0x1B0, 32, 64),
    (0x1D0, 64, 64),
]
SIGN_AT = (6, 5, 34, 27)  # 시트 (x, y, 폭, 높이)
S_INK, S_WOOD = 14, 12
S_RGB = {
    0: None,
    1: (180, 108, 72),
    2: (0, 0, 108),
    3: (144, 72, 36),
    4: (180, 144, 0),
    5: (180, 72, 0),
    6: (144, 0, 0),
    7: (72, 0, 0),
    8: (72, 36, 144),
    9: (72, 144, 180),
    10: (36, 72, 72),
    11: (36, 72, 180),
    12: (144, 72, 36),
    13: (72, 36, 0),
    14: (0, 0, 0),
    15: (180, 180, 144),
}


def read_art(path: Path, w: int, h: int) -> list[str]:
    rows = [
        ln for ln in path.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")
    ]
    assert len(rows) == h and all(len(r) == w and set(r) <= {"#", "."} for r in rows), (
        f"{path.name}: {w}×{h} 의 #/. 이어야 한다"
    )
    return rows


# ── 제목 ───────────────────────────────────────────────────────────────────
def title_grid(w: list[int]) -> list[list[int]]:
    """VRAM(워드) → 184×80 색 번호 격자."""
    r0, c0, nr, nc = TITLE_AT
    g = [[0] * (nc * 8) for _ in range(nr * 8)]
    for r in range(nr):
        for c in range(nc):
            px = O._tile_decode(w, w[(r0 + r) * 64 + c0 + c] & 0xFFF)
            for y in range(8):
                g[r * 8 + y][c * 8 : c * 8 + 8] = px[y]
    return g


def title_edits(vram: bytes, spare0: int) -> list[tuple[int, bytes]]:
    w = list(struct.unpack("<32768H", vram))
    r0, c0, nr, nc = TITLE_AT
    ink = read_art(TITLE_TXT, nc * 8, nr * 8)
    g = title_grid(w)
    free: list[int] = []  # 원래 제목 전용 타일 — 새 모양에 다시 쓴다
    for r in range(nr):
        for c in range(nc):
            t = w[(r0 + r) * 64 + c0 + c] & 0xFFF
            if (r, c) not in TITLE_LOCKED and t not in (T_ALL_INK, T_ALL_BG) and t not in free:
                free.append(t)
    for r in range(64):  # 제목 밖에서도 쓰는 타일은 못 건드린다
        for c in range(64):
            inside = r0 <= r < r0 + nr and c0 <= c < c0 + nc
            if not inside:
                assert (w[r * 64 + c] & 0xFFF) not in free, (
                    f"제목 타일 0x{w[r * 64 + c] & 0xFFF:X} 를 밖에서도 쓴다"
                )
    spares = list(range(spare0, SPARE_END))
    pool = free + [t for t in spares if t not in free]
    seen: dict[bytes, int] = {}
    edits: list[tuple[int, bytes]] = []
    used = 0
    for r in range(nr):
        for c in range(nc):
            if (r, c) in TITLE_LOCKED:
                continue
            blk = []
            for y in range(8):
                row = []
                for x in range(8):
                    old = g[r * 8 + y][c * 8 + x]
                    row.append(
                        T_INK
                        if ink[r * 8 + y][c * 8 + x] == "#"
                        else (T_BG if old == T_INK else old)
                    )
                blk.append(row)
            flat = {v for line in blk for v in line}
            if flat == {T_INK}:
                t = T_ALL_INK
            elif flat == {T_BG}:
                t = T_ALL_BG
            else:
                key = b"".join(bytes(line) for line in blk)
                if key not in seen:
                    assert used < len(pool), (
                        f"제목 글자·바탕 혼합 칸이 {used + 1}종 — 타일 {len(pool)}장을 넘는다"
                    )
                    seen[key] = pool[used]
                    used += 1
                    edits.append(
                        (
                            seen[key] * 32,
                            b"".join(v.to_bytes(2, "little") for v in O._tile_encode(blk)),
                        )
                    )
                t = seen[key]
            old_e = w[(r0 + r) * 64 + c0 + c]
            if (old_e & 0xFFF) != t:
                edits.append(
                    (((r0 + r) * 64 + c0 + c) * 2, ((old_e & 0xF000) | t).to_bytes(2, "little"))
                )
    return edits


# ── 간판 ───────────────────────────────────────────────────────────────────
def sign_sheet(w) -> list[list[int]]:
    idx = [[0] * 96 for _ in range(128)]
    for p, ox, oy in SIGN_SPRITES:
        for k in range(8):
            bx, by = k & 1, k >> 1
            for y in range(16):
                ws = [w[p * 32 + k * 64 + pl * 16 + y] for pl in range(4)]
                for x in range(16):
                    idx[oy + by * 16 + y][ox + bx * 16 + x] = sum(
                        ((ws[pl] >> (15 - x)) & 1) << pl for pl in range(4)
                    )
    return idx


def _sign_clean(idx: list[list[int]]) -> list[list[int]]:
    """옛 글자·무늬를 나무색 12 로 지운 판 — 나무 안쪽을 씨앗에서 번지게 채우고, 테두리 검정선·주황 장식·위 하이라이트는 막는다."""
    H, W = 128, 96

    def col(x, y):
        return S_RGB.get(idx[y][x], (255, 0, 255))

    orn = {(180, 72, 0), (180, 144, 0)}
    inside_ok = {(144, 72, 36), (72, 36, 0), (144, 0, 0), (72, 0, 0), (0, 0, 0)}

    def near_bg(x, y, r=2):
        return any(
            0 <= y + dy < H and 0 <= x + dx < W and col(x + dx, y + dy) == (0, 0, 108)
            for dy in range(-r, r + 1)
            for dx in range(-r, r + 1)
        )

    def near_orn(x, y, r=2):
        return any(
            0 <= y + dy < H and 0 <= x + dx < W and col(x + dx, y + dy) in orn
            for dy in range(-r, r + 1)
            for dx in range(-r, r + 1)
        )

    def passable(x, y):
        c = col(x, y)
        if near_orn(x, y):
            return False
        if c == (180, 108, 72):
            return False
        if c == (0, 0, 0) and near_bg(x, y):
            return False
        return c in inside_ok

    X0, X1, Y0, Y1 = 4, 39, 6, 33
    seen: set[tuple[int, int]] = set()
    st = [(20, 18)]
    while st:
        x, y = st.pop()
        if (x, y) in seen or not (X0 <= x <= X1 and Y0 <= y <= Y1) or not passable(x, y):
            continue
        seen.add((x, y))
        st += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    assert len(seen) > 500, f"나무 안쪽을 못 찾았다({len(seen)}px)"
    out = [row[:] for row in idx]
    for x, y in seen:
        out[y][x] = S_WOOD
    return out


def sign_expected(w) -> list[list[int]]:
    x0, y0, sw, sh = SIGN_AT
    ink = read_art(SIGN_TXT, sw, sh)
    out = _sign_clean(sign_sheet(w))
    for y in range(sh):
        for x in range(sw):
            if ink[y][x] == "#":
                out[y0 + y][x0 + x] = S_INK
    return out


def sign_edits(vram: bytes) -> list[tuple[int, bytes]]:
    w = struct.unpack("<32768H", vram)
    old, new = sign_sheet(w), sign_expected(w)
    edits = []
    for p, ox, oy in SIGN_SPRITES:
        for k in range(8):
            bx, by = k & 1, k >> 1
            cells = [
                [new[oy + by * 16 + y][ox + bx * 16 + x] for x in range(16)] for y in range(16)
            ]
            was = [[old[oy + by * 16 + y][ox + bx * 16 + x] for x in range(16)] for y in range(16)]
            if cells == was:
                continue
            words = [0] * 64
            for y in range(16):
                for x in range(16):
                    v = cells[y][x]
                    for pl in range(4):
                        words[pl * 16 + y] |= ((v >> pl) & 1) << (15 - x)
            edits.append(((p * 32 + k * 64) * 2, b"".join(v.to_bytes(2, "little") for v in words)))
    return edits


def edits(vram: bytes, spare0: int) -> list[tuple[int, bytes]]:
    return title_edits(vram, spare0) + sign_edits(vram)


# ── 되읽기 ─────────────────────────────────────────────────────────────────
def check_vram(vram: bytes) -> str:
    """바뀐 VRAM 덩어리가 도안 텍스트와 픽셀까지 같은지 — 제목(잠금 칸 제외)·간판(34×27 안 전부 + 나무판 지움)."""
    w = list(struct.unpack("<32768H", vram))
    _, _, nr, nc = TITLE_AT
    ink = read_art(TITLE_TXT, nc * 8, nr * 8)
    g = title_grid(w)
    bad = []
    for y in range(nr * 8):
        for x in range(nc * 8):
            if (y // 8, x // 8) in TITLE_LOCKED:
                continue
            if (g[y][x] == T_INK) != (ink[y][x] == "#"):
                bad.append((x, y))
    assert not bad, f"제목이 도안과 다르다 {len(bad)}px {bad[:10]}"
    x0, y0, sw, sh = SIGN_AT
    sink = read_art(SIGN_TXT, sw, sh)
    sh_ = sign_sheet(w)
    bad = [
        (x, y)
        for y in range(sh)
        for x in range(sw)
        if sink[y][x] == "#" and sh_[y0 + y][x0 + x] != S_INK
    ]
    assert not bad, f"간판 글자가 도안과 다르다 {len(bad)}px {bad[:10]}"
    # 글자 밖은 옛 글자를 지운 판(원판에서 만든 기대값)과 시트 전체가 같아야 한다 — 테두리·장식이 안 변했다
    orig_w = struct.unpack("<32768H", common.track_data(O.VRAM_IMG_REL, O.VRAM_IMG_SECTORS))
    exp = sign_expected(orig_w)
    diff = [(x, y) for y in range(128) for x in range(96) if sh_[y][x] != exp[y][x]]
    assert not diff, f"간판 시트가 기대와 다르다 {len(diff)}px {diff[:10]}"
    return f"제목 {nc * 8}×{nr * 8}(잠금 칸 {len(TITLE_LOCKED)} 제외) · 간판 {sw}×{sh} 도안과 일치"


def verify_iso(iso: Path) -> str:
    """구운 이미지에서 rel 642~673 을 읽어 도안과 대조한다(빌드 되읽기)."""
    with open(iso, "rb") as f:
        out = []
        for i in range(O.VRAM_IMG_SECTORS):
            f.seek((common.T2_SECTOR + O.VRAM_IMG_REL + i) * common.RAW + common.USER_OFF)
            out.append(f.read(common.USER))
    return check_vram(b"".join(out))


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        print(verify_iso(Path(sys.argv[2])))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
