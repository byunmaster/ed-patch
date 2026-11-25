"""GT4000 안 2 시험 — 새 게임 → 챕터 6 시작 맵 → GT4000 이동 뒤 정지·크래시 여부와 화면을 찍는다(시험 빌드 `ED_GT4000=1` 전용).

  sh scripts/capture.sh python3 games/ps1-ed3/tools/gt4000_probe.py --cue <cue> --out <폴더>
"""

import argparse
import os
import sys

import dialog_harness as D
import headless_ps1 as H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cue", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--map", default="GT4000")
    ap.add_argument("--chapter", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    emu = H.Emu(a.cue)
    D.boot(emu, os.path.join(a.out, "_boot.state"), a.cue)
    D.inject_jump(emu, bytes([0x14, 0x02, 0xFF, a.chapter]) + bytes(4))
    D.wait_map(emu)
    emu.shot(os.path.join(a.out, "0_chapter_start.png"))
    D.inject_jump(emu, bytes([0x14, 0x02, 0x06]) + a.map.encode("ascii") + bytes(4))
    prev = None
    for k in range(10):
        emu.run(150)
        p = os.path.join(a.out, f"1_{a.map}_{k}.png")
        emu.shot(p)
        cur = emu.peek(0x80000000 + 0x200000 - 0x10000, 0x10000) if False else None
    print("map name buf:", emu.peek(0x801D65F8, 8))
    for i, b in enumerate(["right", "up", "left", "down"]):
        emu.press(b, 30, 30)
        emu.shot(os.path.join(a.out, f"2_walk_{i}_{b}.png"))
    for i in range(6):
        emu.press("circle", 6, 60)
        emu.shot(os.path.join(a.out, f"3_talk_{i}.png"))
    print("done")


if __name__ == "__main__":
    sys.exit(main())
