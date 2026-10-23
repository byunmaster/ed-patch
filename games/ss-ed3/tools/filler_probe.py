#!/usr/bin/env python3
"""글 모드 한복판에 놓아도 **화면에 안 나오고 흐름도 안 바꾸는 한 바이트**가 있나 — 대사 보기 하네스로 후보를 하나씩 시험한다.

    python3 games/ss-ed3/tools/filler_probe.py <이미지.cue> <기준상태> <출력폴더> --bkr <.bkr>

왜: `0E`(키 대기 뒤 **같은 글 모드가 이어진다**) 로 끝나는 블록 뒤엔 `FF FF` 무동작을 못 둔다(글자 코드로 읽힌다).
재조판으로 글이 짧아지면 남는 바이트를 **길이 보존** 때문에(맵 안 포인터가 블록 시작을 가리키고 뒤 데이터가 맞붙어 있다) 줄 끝 공백으로만 흡수해야 하는데 자리가 모자란 블록이 있다.
후보 `b` 를 본문 한가운데에 k 개 넣은 블록을 이식해 띄우고, 기준(0 개)과 **픽셀이 같고** 스크립트가 정상 종료하면 「무동작」으로 본다.
"""

import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import check_build_discs as B
import common as C
import dialog_sweep as D
import hangul_map as H
import mapfile as M
import ss_headless as S


def shoot(h, snap, zr, seg):
    """`seg`(머리+본문+종결) 를 이식해 띄우고 `(쪽 그림 목록, 정상 종료 여부)`."""
    h.restore(snap)
    h.poke(D.LWRAM + zr, D.SETUP + D.OPEN + seg + D.TAIL)
    h.poke(D.PC, (D.LWRAM + zr).to_bytes(4, "big"))
    shots, ok = [], False
    for _ in range(6):
        if not D.stable(h):
            break
        shots.append(h.frame[150:240].copy())
        h.press("c", 4, 22)
        if int.from_bytes(h.peek(D.PC, 4), "big") == 0:
            ok = True
            break
    return shots, ok


def main():
    a = sys.argv[1:]
    cue, statep, outdir = a[0], a[1], a[2]
    bkr = a[a.index("--bkr") + 1] if "--bkr" in a else None
    core = os.path.join(S.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    h = S.Harness(core, cue, outdir, bkr=bkr)
    h.load(statep)
    h.run(2)
    img = build.out_paths(1)[0]
    files = {n: (l, s) for n, l, s, *_ in build.patched(1)}
    got = B.read_extent(img, *files["/MAP/MAP001.BIN"])
    with C.open_disc(1) as d:
        src = d.read("/MAP/MAP001.BIN")
    blk = M.blocks(src)[33]
    head = got[blk["off"] - 2 : blk["off"]]
    zr = D.zero_run(got, 400)
    h.poke(D.LWRAM, got[:0])
    snap = h.snap()
    table = H.load()
    t1 = H.encode_kr("시험 문장이다.", table)
    t2 = H.encode_kr("두 번째 줄이다.", table)
    NL = b"\x0d"
    base_seg = head + t1 + NL + t2 + b"\x10"
    base, ok0 = shoot(h, snap, zr, base_seg)
    print(f"기준: 쪽 {len(base)} · 정상 종료 {ok0}")
    os.makedirs(outdir, exist_ok=True)
    Image.fromarray(base[0]).save(os.path.join(outdir, "base.png"))
    res = {}
    for b in range(0x01, 0x20):
        if b in (0x02, 0x0D, 0x0E, 0x0F, 0x10):
            continue
        out = {}
        for where, seg in (
            ("끝", head + t1 + NL + t2 + bytes([b]) * 4 + b"\x10"),
            ("줄 사이", head + t1 + bytes([b]) * 4 + NL + t2 + b"\x10"),
        ):
            shots, ok = shoot(h, snap, zr, seg)
            same = ok and len(shots) == len(base) and all((x == y).all() for x, y in zip(shots, base, strict=True))
            out[where] = "같음" if same else ("종료 이상" if not ok else "다름")
        res[b] = out
        print(f"  {b:#04x}: {out}", flush=True)
    good = [b for b, o in res.items() if all(v == "같음" for v in o.values())]
    print("무동작 후보:", [f"{b:#04x}" for b in good])


if __name__ == "__main__":
    main()
