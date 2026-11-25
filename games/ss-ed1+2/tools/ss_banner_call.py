"""**ED2 입장 배너 실화면 전수** — 배너 그리기 함수(`0x06058D78`, r4 = 이름 포인터)를 지명마다 직접 불러 상자·글을 게임 자신의 경로로 그리고 좌·우 여백을 잰다(걷기 없음·이미지 안 고침).

    python3 tools/ss_banner_call.py --state <ED2 필드 스테이트> --out <폴더> [--cue …]

상자 안쪽 x=64~153(90px, ED1 배너와 같은 틀), 글 잉크(흰 화소)의 왼·오른 끝에서 좌·우 여백을 잰다. 지명은 빌드 이미지의 `/BIN/ED2SCN*.BIN` 헤더(맨 앞 16B).
"""

import argparse
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import ss_battle_sweep as B
import ss_headless as H
import ss_scene_sweep as S
import ss_town_sweep_ed2 as T

BIN = {"ed1": "/ED.BIN", "ed2": "/ED2.BIN"}
ED1_BIN = b""
FUNC = 0x06058D78  # ED2.BIN — ED1 은 0x0607AD60 (ED.BIN)
BOX_X0, BOX_X1 = 64, 153  # 상자 안쪽(파랑)
BOX_Y0, BOX_Y1 = 59, 77


def measure(frame):
    sub = frame[BOX_Y0 : BOX_Y1 + 1, BOX_X0 : BOX_X1 + 1].astype(int)
    white = (sub > 200).all(axis=2)
    cols = np.where(white.any(axis=0))[0]
    if len(cols) == 0:
        return None
    return int(cols.min()), int(BOX_X1 - BOX_X0 - cols.max())


def table_names(game="ed1", long=False):
    """ED1 지명 표(`ED/지명`) — 배너가 표 이름을 쓴다(트레일링 전각공백 포함). → {바이트: 자리}"""
    import check_place_fields as P

    img = glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))[0]
    f, mm = common.open_image(img)
    out = {}
    try:
        files = {p: (lba, s) for p, lba, s in common.iso_files(mm)}
        d = common.read_extent(mm, *files[BIN[game]])
        for path, at, room, _kr, where in P.targets():
            if path == BIN[game] and ("/지명 긴꼴[" if long else "/지명[") in where:
                z = d.find(b"\0", at, at + room)
                out.setdefault(d[at : z if z >= 0 else at + room], where)
    finally:
        mm.close()
        f.close()
    return out


def banner_names(game="ed1"):
    """배너 전용 표(`patch_ui.BANNER_TABLES`)의 행 — 빌드의 호출부 리터럴을 따라 읽는다. → {바이트: 자리}"""
    import struct

    import patch_ui

    img = glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))[0]
    f, mm = common.open_image(img)
    out = {}
    try:
        files = {p: (lba, s) for p, lba, s in common.iso_files(mm)}
        path = BIN[game]
        c = patch_ui.BANNER_TABLES[path]
        d = common.read_extent(mm, *files[path])
        start = (
            struct.unpack(">I", d[c["ptrs"][0] : c["ptrs"][0] + 4])[0]
            + c["lead"]
            - patch_ui.ptr_base(path)
        )
        for i in range(48):
            row = d[start + i * c["stride"] : start + (i + 1) * c["stride"]]
            z = row.find(b"\0")
            row = row[: z if z >= 0 else len(row)]
            if row:
                out.setdefault(row, f"banner[{i}]")
    finally:
        mm.close()
        f.close()
    return out


def write_dx(game, rows):
    """측정(좌−우 d, 지금 보정 dx 가 이미 들어 있다)으로 칸별 보정을 다시 낸다: d0 = d − 2·dx, 새 dx = (−d0)//2 — 좌−우를 {−1, 0} 으로(최근접·동점 왼쪽)."""
    import patch_ui

    key = "ED1" if game == "ed1" else "ED2"
    cur = patch_ui.banner_dx()
    n = 48 if game == "ed1" else 36
    by = {r["hex"]: r["L"] - r["R"] for r in rows if r["L"] is not None}
    new = [0] * n
    for i, hx in table_index(game).items():
        d = by[hx]
        d0 = d - 2 * cur[key][i]
        new[i] = (-d0) // 2
    cur[key] = new
    with open(os.path.join(common.GAME_DIR, "script", "banner_dx.json"), "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=1)
    print("banner_dx", key, new)


def table_index(game):
    """색인 → 이름 바이트(hex) — 같은 이름이 여러 칸이어도 칸마다."""
    import struct

    import patch_ui

    img = glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))[0]
    f, mm = common.open_image(img)
    out = {}
    try:
        files = {p: (lba, s) for p, lba, s in common.iso_files(mm)}
        path = BIN[game]
        d = common.read_extent(mm, *files[path])
        if game == "ed1":
            c = patch_ui.BANNER_TABLES[path]
            start = struct.unpack(">I", d[c["ptrs"][0] : c["ptrs"][0] + 4])[0] + c["lead"] - patch_ui.ptr_base(path)
            stride, n = c["stride"], 48
        else:
            start, stride, n = patch_ui.ED2_LONG_TBL - 0x06028000, 16, 36
        for i in range(n):
            row = d[start + i * stride : start + (i + 1) * stride]
            z = row.find(b"\0")
            row = row[: z if z >= 0 else len(row)]
            if row:
                out[i] = row.hex()
    finally:
        mm.close()
        f.close()
    return out


def headers(game="ed2"):
    img = glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))[0]
    f, mm = common.open_image(img)
    out = {}
    try:
        for p, lba, s in common.iso_files(mm):
            if p.startswith(f"/BIN/{game.upper()}SCN"):
                d = common.read_extent(mm, lba, s)
                raw = d[:16].split(b"\0")[0]
                out.setdefault(raw, p)
    finally:
        mm.close()
        f.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=None)
    ap.add_argument("--state", required=True)
    ap.add_argument("--game", choices=("ed1", "ed2"), default="ed2")
    ap.add_argument("--write-dx", action="store_true", help="측정으로 x 보정(`script/banner_dx.json`)을 갱신한다(kind banner·table-long 만)")
    ap.add_argument("--kind", choices=("header", "table", "table-long", "banner"), default="header")
    a = ap.parse_args()
    cue = a.cue or os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue")
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, cue, a.out, bkr=B.DEFAULT_BKR)
    global FUNC
    S.configure(a.game)
    if a.game == "ed1":
        FUNC = 0x0607AD60
    global ED1_BIN
    if a.game == "ed1":
        _i = glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))[0]
        _f, _mm = common.open_image(_i)
        _fs = {p: (lba, sz) for p, lba, sz in common.iso_files(_mm)}
        ED1_BIN = common.read_extent(_mm, *_fs["/ED.BIN"])
        _mm.close()
        _f.close()
    code, _ = S.build_stub()
    if not os.path.exists(
        a.state
    ):  # 이미지 지문 칸이 없으면 부팅해서 만든다(ss_scene_sweep 과 같은 길)
        (S.boot_to_field_ed1 if a.game == "ed1" else B.boot_to_field)(h)
        h.save(a.state)
    h.load(a.state)
    h.run(5)
    h.poke(S.HOOK, code)
    for q in range(0, 0x20, 4):
        S.p32(h, S.MB + q, 0)
    h.poke(S.TICK, S.hook_patch())
    h.run(30)
    if a.game == "ed2":
        h.poke(T.MAP_VAR, bytes([3, 1]))  # 마을 하나 — 배경이 단순한 곳
        S.p32(h, S.MB + 4, 0)
        S.p32(h, S.MB + 12, 0)
        S.p32(h, S.MB, T.SESSION)
        h.run(300)
    snap = os.path.join(a.out, "_snap.state")
    h.save(snap)
    rows = []
    src = (
        banner_names(a.game)
        if a.kind == "banner"
        else table_names(a.game, a.kind == "table-long")
        if a.kind.startswith("table")
        else headers(a.game)
    )
    for raw, path in sorted(src.items(), key=lambda kv: kv[1]):
        h.load(snap)
        h.run(2)
        if a.game == "ed1" and a.kind == "banner":
            import re
            import struct

            import patch_ui

            c = patch_ui.BANNER_TABLES["/ED.BIN"]
            lit = struct.unpack(">I", ED1_BIN[c["ptrs"][0] : c["ptrs"][0] + 4])[0]
            ptr = lit + c["lead"] + c["stride"] * int(re.search(r"\[(\d+)\]", path).group(1))
        elif a.game == "ed2" and a.kind == "table-long":
            # 끼움 루틴은 포인터가 긴꼴 표 칸일 때만 일한다 — 실제 칸 주소로 부른다
            import re

            import patch_ui

            ptr = patch_ui.ED2_LONG_TBL + 16 * int(re.search(r"\[(\d+)\]", path).group(1))
        else:
            h.poke(S.MB + 0x100, raw + b"\0")
            ptr = S.MB + 0x100
        S.p32(h, S.MB + 4, ptr)
        S.p32(h, S.MB + 12, 0)
        S.p32(h, S.MB, FUNC)
        h.run(8)
        m = measure(h.frame)
        Image.fromarray(h.frame[52:84, 56:162]).save(os.path.join(a.out, f"b_{raw.hex()}.png"))
        rows.append(
            {"path": path, "hex": raw.hex(), "n": len(raw), "L": m and m[0], "R": m and m[1]}
        )
        print(path, raw.hex(), m, flush=True)
    if a.write_dx:
        write_dx(a.game, rows)
    with open(os.path.join(a.out, "banner.json"), "w", encoding="utf-8") as jf:
        json.dump(rows, jf, ensure_ascii=False, indent=1)
    os.remove(snap)


if __name__ == "__main__":
    main()
