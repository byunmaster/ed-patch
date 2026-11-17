"""GT06000(보스 직전 맵)에서 위로 걸으며 좌표를 적는다 — 보스 이벤트가 걸리는 자리를 찾는 시험 전용 탐침.

sh scripts/capture.sh python3 tools/boss_save_walk.py <cue> <card.mcr> <출력폴더> [걸음 수] [방향]
"""

import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import debug_warp as W
import dialog_harness as D


def pos(e):
    return struct.unpack("<2H", e.peek(0x800924E6, 4))


def main():
    cue, card, out = sys.argv[1:4]
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 60
    d = sys.argv[5] if len(sys.argv) > 5 else "up"
    os.makedirs(out, exist_ok=True)
    shutil.copy(card, out + "/card.mcr")
    e = D.make_state(cue, out + "/card.mcr", out + "/base.state")
    W.warp(e, "GT06000", 0, b"\0\0\0", settle=200)
    for i in range(n):
        e.press(d, 10, 6)
        if i % 3 == 0:
            e.shot(f"{out}/s{i:03d}.png")
            print(i, pos(e), flush=True)
    e.save(out + "/end.state")


if __name__ == "__main__":
    main()
