"""화면 그래픽 재삽입 — PNG → **셀맵 + 타일 + 팔레트**로 쪼개 `.PAK` 에 되돌린다.

    python3 games/ss-ed3/tools/reinsert_gfx.py --check   # 들어가나 보기만
    python3 games/ss-ed3/tools/reinsert_gfx.py           # 이미지에 써넣는다(build.py 가 부른다)

`gfx.py` 의 역방향이다. 그쪽 독스트링에 형식(셀맵 4,800B · 타일 8bpp 8×8 · 팔레트 512B)과
**어떻게 알아냈는지**(실기에서 되짚었다)가 있다.

🔴 **길이 보존**이 이 재삽입의 계약이다. PAK 은 「항목 수 + BE32 오프셋 표」라 항목 하나만
커져도 뒤가 전부 밀린다. 그래서 셋 다 원래 칸에 맞춘다 — 셀맵·팔레트는 크기가 고정이고,
타일은 **남는 칸을 0 으로 채운다**(원본 65,536B = 1,024 칸 중 우리가 쓰는 건 249 개다).

⚠ **문자 번호는 2씩 뛴다.** 번호의 단위가 32 바이트인데(4bpp 기준) 8bpp 셀은 64 바이트라,
   `charno` 를 1 씩 올리면 타일이 절반씩 겹쳐 읽힌다. 원본 셀맵도 608·610·612… 였다.
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import gfx as G

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# (PAK 경로, 셀맵 항목, 타일 항목, 팔레트 항목, 우리 그림)
TARGETS = [("/SYSTEM/LDDATA.PAK", 6, 7, 8, os.path.join(GAME, "assets", "title_kr.png"))]


def to15(rgb):
    """RGB → 새턴 15bit `0BBBBBGGGGGRRRRR`."""
    r, g, b = (v >> 3 for v in rgb)
    return (b << 10) | (g << 5) | r


def pack(png, map_size, tile_size, pal_size):
    """PNG → `(셀맵, 타일, 팔레트)`. 칸을 넘기면 ValueError."""
    from PIL import Image

    im = Image.open(png).convert("RGB")
    if im.size != (G.CW * 8, G.CH * 8):
        raise ValueError(f"크기가 {im.size} 다 — {G.CW * 8}×{G.CH * 8} 이어야 한다")

    # ① 고유 타일을 모으고 번호를 준다 (2씩 뛴다)
    order, index = [], {}
    cells = []
    for cy in range(G.CH):
        for cx in range(G.CW):
            raw = im.crop((cx * 8, cy * 8, cx * 8 + 8, cy * 8 + 8)).tobytes()
            if raw not in index:
                index[raw] = len(order) * 2
                order.append(raw)
            cells.append(index[raw])
    if len(order) * 64 > tile_size:
        raise ValueError(f"고유 타일 {len(order)} 개 — 칸은 {tile_size // 64} 개다")

    # ② 색을 모아 팔레트를 만든다.
    # 🔴 **인덱스 0 은 투명이다** — 거기에 색을 넣으면 그 픽셀이 통째로 비어 화면이
    #   어둡게 뜬다(실측 2026-08-27: 배경 흰색을 0 에 넣었더니 타이틀이 먹빛이 됐다).
    #   원본도 0 을 투명으로 쓰고 배경 흰색은 인덱스 5 에 두었다. 그래서 **1 부터** 채운다.
    colors = [(255, 255, 255)]  # 자리만 차지한다(투명이라 안 보인다)
    cmap = {}
    for raw in order:
        for i in range(0, len(raw), 3):
            c = raw[i : i + 3]
            if c not in cmap:
                cmap[c] = len(colors)
                colors.append(c)
    if len(colors) > pal_size // 2:
        raise ValueError(f"색 {len(colors)} 가지(투명 자리 포함) — {pal_size // 2} 이하여야 한다")

    tiles = bytearray(tile_size)
    for n, raw in enumerate(order):
        for i in range(64):
            tiles[n * 64 + i] = cmap[raw[i * 3 : i * 3 + 3]]
    pal = bytearray(pal_size)
    for i, c in enumerate(colors):
        struct.pack_into(">H", pal, i * 2, to15(c))
    cmapbuf = bytearray(map_size)
    for i, charno in enumerate(cells):
        if i * 4 + 4 <= map_size:
            struct.pack_into(">I", cmapbuf, i * 4, charno)
    return bytes(cmapbuf), bytes(tiles), bytes(pal), len(order), len(colors)


def apply(data, check_only=False):
    """PAK bytes → 새 bytes. `(새 데이터, [보고])`."""
    segs = G.items(data)
    offs = [0]
    for s in segs:
        offs.append(offs[-1] + len(s))
    notes = []
    out = bytearray(data)
    for _path, mi, ti, pi, png in TARGETS:
        if not os.path.exists(png):
            notes.append(f"{os.path.basename(png)} 가 없다 — 건너뜀")
            continue
        cmapbuf, tiles, pal, ntile, ncol = pack(png, len(segs[mi]), len(segs[ti]), len(segs[pi]))
        notes.append(f"{os.path.basename(png)} — 타일 {ntile} · 색 {ncol}")
        if check_only:
            continue
        for idx, buf in ((mi, cmapbuf), (ti, tiles), (pi, pal)):
            # 오프셋 표는 그대로 둔다 — 길이가 같으니 자리만 덮어쓴다
            at = struct.unpack(">I", data[4 + idx * 4 : 8 + idx * 4])[0]
            assert len(buf) == len(segs[idx]), (idx, len(buf), len(segs[idx]))
            out[at : at + len(buf)] = buf
    return bytes(out), notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.parse_args()
    with C.open_disc(1) as d:
        for n, l, s in d.files():
            if n == TARGETS[0][0]:
                data = d.read_extent(l, s)
                break
    _, notes = apply(data, check_only=True)
    for x in notes:
        print("  " + x)
    print("  ✅ 길이 보존으로 들어간다" if notes else "  대상이 없다")


if __name__ == "__main__":
    main()
