"""디버그 이동 뒤 걷기 — 현재 맵 이름(RAM 0x801EFCA0)을 기록하며 문을 통한 게임 자체 전환으로 건물에 들어가고, 창·메뉴가 뜨면 찍는다(시험 전용, 「디버그 이동」 표기).
sh scripts/capture.sh python3 tools/debug_warp_walk2.py <cue> <card.mcr> <맵:방향:인자hex> <출력폴더> [걸음] [시드]
"""

import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import debug_warp as W
import dialog_harness as D
import numpy as np
import PIL.Image as I

MAPNAME = 0x801EFCA0


def mapname(e):
    return bytes(e.peek(MAPNAME, 7)).decode("ascii", "replace")


def green(p):
    a = np.asarray(I.open(p).convert("RGB")).astype(int)
    return int(
        ((abs(a[..., 0] - 16) < 6) & (abs(a[..., 1] - 56) < 8) & (abs(a[..., 2] - 32) < 6)).sum()
    )


def main():
    cue, card, spec, out = sys.argv[1:5]
    steps = int(sys.argv[5]) if len(sys.argv) > 5 else 400
    random.seed(int(sys.argv[6]) if len(sys.argv) > 6 else 1)
    name, d, a = spec.split(":")
    os.makedirs(out, exist_ok=True)
    e = D.make_state(cue, card, out + "/base.state")
    W.warp(e, name, int(d), bytes.fromhex(a), settle=200)
    open(out + "/INDEX.txt", "w").write(  # noqa: SIM115
        f"디버그 이동 — {spec} 에서 걷기(맵 이름 기록) (제품 롬 아님)\n"
    )
    cur = mapname(e)
    seen = {cur}
    print("map", cur, flush=True)
    for k in range(steps):
        mv = random.choice(["up", "down", "left", "right"])
        e.press(mv, random.choice([20, 40, 70]), 4)
        if random.random() < 0.5:
            e.press("circle", 6, 30)
        if k % 12 == 11:
            e.press("cross", 6, 30)
        m = mapname(e)
        p = f"{out}/f{k:04d}.png"
        e.shot(p)
        keep = False
        if m != cur:
            print(k, "map", cur, "->", m, flush=True)
            cur = m
            if m not in seen:
                seen.add(m)
                keep = True
        if green(p) > 800 or D.window_open(e):
            print(k, "ui", m, green(p), flush=True)
            keep = True
        if not keep:
            os.remove(p)


if __name__ == "__main__":
    main()
