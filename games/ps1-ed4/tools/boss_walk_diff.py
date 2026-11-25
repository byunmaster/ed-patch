"""보스 곁까지 걸어가(boss_walk 와 같은 열) 공격을 되풀이하며 사이클마다 RAM 을 떠, 줄어드는 칸(보스 HP 후보)을 낸다(시험 전용).

python3 tools/boss_walk_diff.py <cue> <card> <상태> <출력폴더> <걸음 열> [사이클 수]
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness as D
import numpy as np


def main():
    cue, card, st, out, seq = sys.argv[1:6]
    n = int(sys.argv[6]) if len(sys.argv) > 6 else 8
    os.makedirs(out, exist_ok=True)
    e = D.make_state(cue, card, out + "/base.state")
    e.load(st)
    e.run(1)
    for _ in range(10):
        e.press("cross", 6, 20)
    e.run(60)
    hp = lambda: e.poke(0x801FF81A, struct.pack("<H", 9999))
    for tok in seq.split(","):
        d, m = tok.split("*")
        for _ in range(int(m)):
            hp()
            e.press(d, 12, 30)
            e.run(30)
    dumps = []
    for c in range(n):
        for _ in range(2):
            hp()
            e.press("circle", 8, 40)
            e.run(40)
        for _ in range(30):
            hp()
            e.run(30)
        e.shot(f"{out}/c{c:02d}.png")
        dumps.append(np.frombuffer(e.peek(0x80000000, 0x200000), dtype="<u2").copy())
        e.save(f"{out}/c{c:02d}.state")
        print("사이클", c, flush=True)
    A = np.stack(dumps).astype(np.int64)
    np.save(out + "/dumps.npy", A.astype(np.uint16))
    d = np.diff(A, axis=0)
    ch = (d != 0).sum(axis=0)
    mono = (d <= 0).all(axis=0) & (d < 0).sum(axis=0).__ge__(1) & (A[-1] > 0)
    print("후보", int(mono.sum()))
    for i in np.nonzero(mono)[0][:80]:
        print(hex(0x80000000 + 2 * int(i)), A[:, i].tolist(), int(ch[i]))


if __name__ == "__main__":
    main()
