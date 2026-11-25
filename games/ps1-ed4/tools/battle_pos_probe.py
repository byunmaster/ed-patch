"""전투 중 영웅 이동 전후 램 차분으로 유닛 좌표 칸을 찾는다(시험 전용).

   sh scripts/capture.sh python3 tools/battle_pos_probe.py <cue> <card.mcr> <슬롯 내림> <출력폴더> [방향]
"""

import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import battle_msg_probe as B
import replay


def snap(e):
    return e.peek(0x801F0000, 0x10000)


def main():
    cue, card, slot, out = sys.argv[1:5]
    d = sys.argv[5] if len(sys.argv) > 5 else "right"
    os.makedirs(out, exist_ok=True)
    shutil.copy(card, out + "/card.mcr")
    e = replay.boot(cue, out + "/card.mcr", int(slot))
    seq = ["right"] * 3 + ["down"] * 3 + ["right"] * 3 + ["up"] * 3
    for i in range(13):
        e.press(seq[i % 12], 45, 4)
    for _ in range(12):
        e.press("down", 100, 4)
        e.run(120)
        if B.units(e):
            break
    print("적", B.units(e), flush=True)
    for _ in range(4):
        e.press("cross", 6, 20)
    e.run(60)
    e.shot(out + "/before.png")
    a = snap(e)
    e.press(d, 14, 30)
    e.run(90)
    e.shot(out + "/after.png")
    b = snap(e)
    diffs = []
    for o in range(0, len(a) - 1, 2):
        va, vb = struct.unpack_from("<H", a, o)[0], struct.unpack_from("<H", b, o)[0]
        if va != vb and abs(va - vb) <= 64:
            diffs.append((0x801F0000 + o, va, vb))
    print(len(diffs), flush=True)
    for x in diffs[:80]:
        print(hex(x[0]), x[1], "→", x[2], flush=True)


if __name__ == "__main__":
    main()
