"""보스 HP 칸(0x801FF81A, u16 — boss_hp_diff 로 찾은 단조 감소 칸)을 1 로 쓰고 승리·후속 화면을 찍는다(시험 전용).

python3 tools/boss_kill.py <cue> <card.mcr> <상태> <출력폴더> [HP 값=1]   (BUFF=250 REBUFF=1)
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness as D
import ending_run as R

HP = 0x801FF81A


def main():
    cue, card, st, out = sys.argv[1:5]
    val = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    os.makedirs(out, exist_ok=True)
    e = D.make_state(cue, card, out + "/base.state")
    e.load(st)
    e.run(1)
    print("전", struct.unpack("<H", e.peek(HP, 2))[0], flush=True)
    e.poke(HP, struct.pack("<H", val))
    st = {"n": 0, "armed": False}
    run0 = e.run

    def run(n):  # 쓰러뜨린 뒤엔 20프레임마다 찍는다 — 승리 직후 화면을 놓치지 않으려고
        if not st["armed"] and struct.unpack("<H", e.peek(HP, 2))[0] == 0:
            st["armed"] = True
        if st["armed"] and st["n"] < 400:
            while n > 0:
                c = min(20, n)
                run0(c)
                n -= c
                e.shot(f"{out}/w{st['n']:03d}.png")
                st["n"] += 1
        else:
            run0(n)

    e.run = run
    for t in range(12):
        R.auto_turns(e, out, 1)
        os.replace(out + "/t000.png", f"{out}/k{t:03d}.png")
        print(t, "HP", struct.unpack("<H", e.peek(HP, 2))[0], flush=True)
    for i in range(200):
        e.press("circle", 6, 50)
        if i % 4 == 0:
            e.shot(f"{out}/v{i // 4:03d}.png")


if __name__ == "__main__":
    main()
