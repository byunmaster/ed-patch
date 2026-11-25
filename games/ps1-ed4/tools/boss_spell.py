"""보스에게 공격 마법 — 저장 상태에서 메뉴 마법 → 첫 주문 → 대상 확정을 입력하고 20프레임마다 찍는다(시험 전용)."""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness as D


def main():
    cue, card, st, out = sys.argv[1:5]
    os.makedirs(out, exist_ok=True)
    e = D.make_state(cue, card, out + "/base.state")
    e.load(st)
    e.run(1)
    k = [0]

    def shot(n=1):
        for _ in range(n):
            e.run(20)
            e.shot(f"{out}/f{k[0]:03d}.png")
            k[0] += 1

    e.poke(0x801FF81A, struct.pack("<H", 9999))
    shot(10)  # 메뉴가 뜨길 기다린다
    e.press("down", 8, 20)
    shot(2)
    e.press("circle", 8, 40)  # 마법
    shot(3)
    e.press("circle", 8, 40)  # 첫 주문
    shot(3)
    for _i in range(6):  # 대상 커서 — 확인
        e.press("circle", 8, 40)
        shot(4)
    shot(40)


if __name__ == "__main__":
    main()
