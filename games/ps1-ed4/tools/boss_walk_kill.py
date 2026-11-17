"""보스 곁까지 걸어가 보스 HP 칸(0x801FF9AA u16 — 유닛 배열 1번(0x801FF9A0~)의 현재 HP, boss_walk_diff 로 찾음)을 1 로 쓰고 공격 → 승리 이후 화면을 20프레임마다 찍는다(시험 전용).

python3 tools/boss_walk_kill.py <cue> <card> <상태> <출력폴더> <걸음 열> [HP=1]
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness as D

BOSS = 0x801FF9AA
HERO = 0x801FF81A


def main():
    cue, card, st, out, seq = sys.argv[1:6]
    val = int(sys.argv[6]) if len(sys.argv) > 6 else 1
    os.makedirs(out, exist_ok=True)
    e = D.make_state(cue, card, out + "/base.state")
    e.load(st)
    e.run(1)
    for _ in range(10):
        e.press("cross", 6, 20)
    e.run(60)
    print("보스 HP 전", struct.unpack("<H", e.peek(BOSS, 2))[0], flush=True)
    for tok in seq.split(","):
        d, m = tok.split("*")
        for _ in range(int(m)):
            e.poke(HERO, struct.pack("<H", 9999))
            e.press(d, 12, 30)
            e.run(30)
    e.poke(BOSS, struct.pack("<H", val))
    k = 0
    for c in range(3):
        for _ in range(2):
            e.poke(HERO, struct.pack("<H", 9999))
            e.press("circle", 8, 40)
            e.run(40)
        for _ in range(30):
            e.poke(HERO, struct.pack("<H", 9999))
            e.run(20)
            e.shot(f"{out}/z{k:04d}.png")
            k += 1
        print("사이클", c, "보스 HP", struct.unpack("<H", e.peek(BOSS, 2))[0], flush=True)
    for i in range(int(os.environ.get("POST", "300"))):
        e.press("circle", 6, 50)
        if i % int(os.environ.get("EVERY", "3")) == 0:
            e.shot(f"{out}/z{k:04d}.png")
            k += 1


if __name__ == "__main__":
    main()
