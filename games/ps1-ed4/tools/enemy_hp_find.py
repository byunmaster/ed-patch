"""전투 중 적 HP 후보 찾기(시험 전용) — 턴마다 RAM 을 떠서 계속 줄어드는 u16 을 뽑는다.
sh scripts/capture.sh python3 tools/enemy_hp_find.py <cue> <card.mcr> <맵:방향> <출력폴더> [턴 수]"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import debug_warp as W
import dialog_harness as D
import ending_run as R
import numpy as np


def dump(e):
    return np.frombuffer(bytes(e.peek(0x80000000, 0x200000)), dtype="<u2").copy()


def main():
    cue, card, spec, out = sys.argv[1:5]
    turns = int(sys.argv[5]) if len(sys.argv) > 5 else 4
    os.makedirs(out, exist_ok=True)
    name, d = spec.split(":")
    e = D.make_state(cue, card, out + "/base.state")
    W.warp(e, name, int(d), b"\0\0\0", settle=120)
    for i in range(6):
        b = 0x8007BA30 + 40 * i
        e.poke(b + 2, struct.pack("<4H", 9999, 9999, 9999, 9999))
        e.poke(b + 10, bytes([250] * 8))
    for _ in range(6):
        e.press("circle", 6, 50)
    snaps = [dump(e)]
    for t in range(turns):
        R.auto_turns(e, out, 1)
        snaps.append(dump(e))
        e.shot(f"{out}/k{t}.png")
    np.save(out + "/snaps.npy", np.stack(snaps))
    s = np.stack(snaps).astype(int)
    dec = np.all(s[1:] <= s[:-1], axis=0) & (s[-1] < s[0]) & (s[0] >= 100) & (s[0] < 60000)
    idx = np.nonzero(dec)[0]
    print("후보", len(idx))
    for i in idx[:80]:
        print(hex(0x80000000 + 2 * int(i)), s[:, i].tolist())
    print("rc ok", flush=True)


if __name__ == "__main__":
    main()
