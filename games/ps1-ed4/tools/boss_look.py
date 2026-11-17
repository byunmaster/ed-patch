"""보스전 한 턴을 20프레임마다 찍는다(시험 전용) — python3 boss_look.py <cue> <card> <상태> <출력폴더> [턴]"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness as D
import ending_run as R


def main():
    cue, card, st, out = sys.argv[1:5]
    n = int(sys.argv[5]) if len(sys.argv) > 5 else 3
    os.makedirs(out, exist_ok=True)
    e = D.make_state(cue, card, out + "/base.state")
    e.load(st)
    e.run(1)
    k = [0]
    run0 = e.run

    def run(m):
        while m > 0:
            c = min(20, m)
            run0(c)
            m -= c
            e.shot(f"{out}/f{k[0]:04d}.png")
            k[0] += 1

    e.run = run
    for _ in range(n):
        e.poke(0x801FF81A, struct.pack("<H", 9999))
        R.auto_turns(e, out, 1)


if __name__ == "__main__":
    main()
