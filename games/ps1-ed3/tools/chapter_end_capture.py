"""장 끝 항해 연출(`*V0` 맵)의 띠 두 상태 — 「…おわり」(끝) · 「次章…」(예고) — 를 맵마다 찍는다(헤드리스 하네스).

  sh scripts/capture.sh python3 games/ps1-ed3/tools/chapter_end_capture.py --cue <cue> --out <폴더> [--maps MT70V0,…] [--frames 1000,2700]

한 맵마다 새 게임 상태에서 이동하고(다른 챕터면 먼저 `14 02 FF n`) 지정 프레임에서 한 장씩 찍는다 — 위치는 원본 320×240 그대로.
"""

import argparse
import os
import sys

import dialog_harness as D
import headless_ps1 as H
import warp_table

V0 = ["MT70V0", "MR43V0", "AT09V0", "CT22V0", "OT12V0", "ST12V0", "GT42V0"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cue", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--maps", default=",".join(V0))
    ap.add_argument("--frames", default="1000,2700")
    ap.add_argument("--state")
    a = ap.parse_args()
    frames = [int(x) for x in a.frames.split(",")]
    table = {n: ch for n, ch, _p, _a in warp_table.table("ed3")}
    os.makedirs(a.out, exist_ok=True)
    emu = H.Emu(a.cue)
    state = a.state or os.path.join(a.out, "_boot.state")
    D.boot(emu, state, a.cue)
    for name in a.maps.split(","):
        emu.load(state)
        emu.run(30)
        if table[name][0]:
            D.inject_jump(emu, bytes([0x14, 0x02, 0xFF, table[name][0]]) + bytes(4))
            D.wait_map(emu)
        D.inject_jump(emu, bytes([0x14, 0x02, 0x06]) + name.encode("ascii") + bytes(4))
        t = 0
        for f in frames:
            emu.run(f - t)
            t = f
            emu.shot(os.path.join(a.out, f"{name}_{f:05d}.png"))
        print(name, flush=True)


if __name__ == "__main__":
    sys.exit(main())
