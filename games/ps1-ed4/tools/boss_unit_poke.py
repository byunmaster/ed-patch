"""전투 유닛 배열(0x801FF9A0 부터 50B 간격: +0 0xC000 · +2 번호 · +6 HP …)의 HP 를 바꿔 보는 시험 — 변형마다 상태를 다시 불러 20프레임마다 찍는다.

python3 tools/boss_unit_poke.py <cue> <card> <상태> <출력폴더> <변형들: "1:0,2:0" 처럼 번호:HP 를 쉼표로, 변형은 공백으로>
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness as D

BASE, STRIDE = 0x801FF9A0, 50


def main():
    cue, card, st, out = sys.argv[1:5]
    os.makedirs(out, exist_ok=True)
    e = D.make_state(cue, card, out + "/base.state")
    for vi, var in enumerate(sys.argv[5:]):
        e.load(st)
        e.run(1)
        e.poke(0x801FF81A, struct.pack("<H", 9999))
        for kv in var.split(","):
            n, hp = (int(x) for x in kv.split(":"))
            a = BASE + STRIDE * (n - 1) + 6
            print(vi, var, hex(a), struct.unpack("<H", e.peek(a, 2))[0], "->", hp, flush=True)
            e.poke(a, struct.pack("<H", hp))
        for k in range(20):
            e.press("circle", 8, 40)
            e.run(20)
            e.shot(f"{out}/v{vi}_{k:02d}.png")


if __name__ == "__main__":
    main()
