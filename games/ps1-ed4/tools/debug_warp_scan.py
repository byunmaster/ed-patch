"""디버그 이동 — 입구 조합(방향·인자)마다 플레이어가 **조작되는지** 잰다(시험 전용). 이동 입력 두 번에 화면이 크게 바뀌면 조작 가능.
sh scripts/capture.sh python3 tools/debug_warp_scan.py <cue> <card.mcr> <출력.tsv>
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import debug_warp as W
import dialog_harness as D
import numpy as np
import PIL.Image as I


def g(p):
    return np.asarray(I.open(p).convert("L")).astype(int)


def main():
    cue, card, out = sys.argv[1:4]
    done = set()
    if os.path.exists(out):
        done = {ln.split("\t")[0] + ln.split("\t")[1] + ln.split("\t")[2] for ln in open(out)}  # noqa: SIM115
    _, cnt = W.census()
    tmp = out + ".tmp"
    base = out + ".state"
    e = D.make_state(cue, card, base)
    f = open(out, "a")  # noqa: SIM115
    for name in cnt:
        for (d, a), _n in cnt[name].most_common():
            if name + str(d) + a.hex() in done:
                continue
            e.load(base)
            e.run(1)
            W.warp(e, name, d, a, tries=6, settle=120)
            e.shot(tmp + "0.png")
            A = g(tmp + "0.png")
            r = []
            for mv in ("up", "left"):
                e.press(mv, 40, 5)
                e.shot(tmp + "1.png")
                B = g(tmp + "1.png")
                r.append(round(float(np.abs(A - B).mean()), 1))
                A = B
            f.write(f"{name}\t{d}\t{a.hex()}\t{max(r)}\n")
            f.flush()


if __name__ == "__main__":
    main()
