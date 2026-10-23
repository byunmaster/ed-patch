#!/usr/bin/env python3
"""꼬리로 옮긴 세션(`_wide` 화자 대사)을 **대사 창에 실제로 띄운다** — 트램펄린 몸(꼬리 본문)이 엔진에서 읽히는지.

    sh scripts/capture.sh --fix python3 games/ss-ed3/tools/tail_view.py <이미지.cue> <기준상태> <출력폴더> MAP030:28 MAP022:363

`dialog_sweep` 은 기준 맵(MAP001)을 두고 원본 블록을 0 런에 베껴 띄우므로 **옮긴 꼬리는 안 지난다**. 여기서는 구운 맵의
`FD 00 <꼬리>` 가 가리키는 꼬리 본문(세션 머리 `FF 00` ~ 돌아오는 `FD 00` 앞)을 같은 0 런에 그대로 써서 띄운다.
⚠ `FD 00` 점프 한 번(원 자리 → 꼬리)은 이 방법이 밟지 않는다 — 그 옵코드는 MAP066#35 실제 맵 시험에서 확인한 것이다.
"""

import json
import os
import struct
import sys
import time

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import check_build_discs as B
import check_structure as K
import common as C
import dialog_sweep as D
import mapfile as M
import ss_headless as H


def main():
    a = sys.argv[1:]
    cue, statep, outdir, targets = a[0], a[1], a[2], a[3:]
    os.makedirs(outdir, exist_ok=True)
    core = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    h = H.Harness(core, cue, outdir)
    img = build.out_paths(1)[0]
    files = {n: (l, s) for n, l, s, *_ in build.patched(1)}
    h.load(statep)
    h.run(2)
    base = h.snap()
    with C.open_disc(1) as d:
        g_src = d.read("/MAP/MAP001.BIN")
        orig = {n: d.read(n) for n, *_ in d.files() if C.is_map_file(n)[0]}
    good = B.read_extent(img, *files["/MAP/MAP001.BIN"])
    zr = D.zero_run(good, 1200)
    for tg in targets:
        stem, key = tg.split(":")
        name = f"/MAP/{stem}.BIN"
        got = B.read_extent(img, *files[name])
        src = orig[name]
        tr = K.trampolines(src, got)
        hits = [x for x in tr if x[0] <= M.blocks(src)[int(key)]["off"] < x[2]]
        assert hits, f"{tg}: 이 블록을 덮는 트램펄린이 없다"
        p, t, r, g = hits[0]
        body = got[t:g]
        if os.environ.get("TAIL_ORIG"):
            body = src[p:r]  # 대조 — 원본 세션 그대로
        h_t = struct.unpack(">37I", got[0x10 : 0x10 + 148])
        h_g = struct.unpack(">37I", good[0x10 : 0x10 + 148])
        h.restore(base)
        h.run(2)
        h.poke(D.LWRAM + h_g[2] - D.LWRAM, got[h_t[2] - D.LWRAM : h_t[2] - D.LWRAM + D.NAMES])
        snap = h.snap()
        h.run(1)
        base_win = h.frame.copy()
        pre = D.SETUP
        if os.environ.get("TAIL_LAST"):
            #   멀티 쪽 세션은 이 하네스에서 첫 쪽 뒤에 멈춘다(원본도 같다) — 마지막 화자 블록(`0E 09 00 02 xx` 뒤)만 띄운다
            i = body.rindex(b"\x0e\x09\x00\x02")
            body, pre = body[i + 3 :], D.SETUP + D.OPEN
        h.poke(D.LWRAM + zr, pre + body + D.TAIL)
        h.poke(D.PC, (D.LWRAM + zr).to_bytes(4, "big"))
        pages = 0
        for _ in range(D.MAX_PAGES):
            if not D.stable(h):
                break
            if D.region_diff(base_win[150:240], h.frame[150:240]) < 300 and D.region_diff(base_win[0:90], h.frame[0:90]) < 300:
                break
            pages += 1
            Image.fromarray(h.frame[150:240]).save(os.path.join(outdir, f"{stem}_{key}_p{pages}.png"))
            h.press("c", 4, 22)
            pc = int.from_bytes(h.peek(D.PC, 4), "big")
            print("  쪽", pages, "PC", hex(pc), flush=True)
            if pc == 0:
                break
        back = int.from_bytes(h.peek(D.PC, 4), "big") == 0
        print(tg, "쪽", pages, "끝까지 돌아왔다" if back else "PC 가 0 이 아니다", flush=True)


if __name__ == "__main__":
    main()
