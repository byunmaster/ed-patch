"""보스 HP 칸 탐색 — 저장 상태에서 자동 턴을 이어 가며 턴마다 RAM(2MB)을 뜨고, 단조 감소하는 워드를 후보로 낸다(시험 전용).

python3 tools/boss_hp_diff.py <cue> <card.mcr> <상태> <출력폴더> [턴 수]   (BUFF=250 REBUFF=1 환경)
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness as D
import ending_run as R
import numpy as np


def main():
    cue, card, st, out = sys.argv[1:5]
    n = int(sys.argv[5]) if len(sys.argv) > 5 else 40
    os.makedirs(out, exist_ok=True)
    e = D.make_state(cue, card, out + "/base.state")
    e.load(st)
    e.run(1)
    dumps = []
    for t in range(n):
        e.poke(
            0x801FF81A, struct.pack("<H", 9999)
        )  # 영웅 전투 중 HP 칸 — 쓰러지면 타이틀로 돌아간다
        R.auto_turns(e, out, 1)
        os.replace(out + "/t000.png", f"{out}/h{t:03d}.png")
        dumps.append(np.frombuffer(e.peek(0x80000000, 0x200000), dtype="<u2").copy())
        print(t, flush=True)
    A = np.stack(dumps).astype(np.int32)
    np.save(out + "/dumps.npy", A.astype(np.uint16))
    d = np.diff(A, axis=0)
    mono = (d <= 0).all(axis=0) & (d < 0).sum(axis=0).__ge__(1) & (A[-1] > 0) & (A[0] < 30000)
    idx = np.nonzero(mono)[0]
    print("후보", len(idx))
    for i in idx[:60]:
        print(hex(0x80000000 + 2 * int(i)), A[:, i].tolist())
    with open(out + "/cands.txt", "w") as f:
        f.write("\n".join(f"{0x80000000 + 2 * int(i):#x} {A[:, i].tolist()}" for i in idx))


if __name__ == "__main__":
    main()
