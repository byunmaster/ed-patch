"""보스에게 직접 걸어 가 본다 — 상태에서 방향 열(예: right*5,up*2)을 한 걸음마다 찍고 마지막에 공격(○ → 공격 → 대상)을 시도한다(시험 전용)."""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness as D


def main():
    cue, card, st, out, seq = sys.argv[1:6]
    os.makedirs(out, exist_ok=True)
    e = D.make_state(cue, card, out + "/base.state")
    e.load(st)
    e.run(1)
    k = 0
    for _ in range(10):
        e.press("cross", 6, 20)
    e.run(60)
    for tok in seq.split(","):
        d, n = tok.split("*")
        for _ in range(int(n)):
            e.poke(0x801FF81A, struct.pack("<H", 9999))
            e.press(d, 12, 30)
            e.run(30)
            e.shot(f"{out}/m{k:03d}.png")
            k += 1
    for _ in range(4):
        e.press("circle", 8, 40)
        e.run(40)
        e.shot(f"{out}/m{k:03d}.png")
        k += 1
    for _ in range(40):
        e.run(30)
        e.shot(f"{out}/m{k:03d}.png")
        k += 1


if __name__ == "__main__":
    main()
