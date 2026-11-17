"""전투 승리 때 창·글 그리기 호출을 잡는다(시험 전용) — `battle_msg_probe` 의 적 HP 0 처치 + `wintrace` 덫.

   sh scripts/capture.sh python3 tools/battle_wt_probe.py <cue> <card.mcr> <슬롯 내림> <출력폴더>
환경: EXP(무술 경험)
"""

import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import battle_msg_probe as B
import replay
import wintrace as WT


def main():
    cue, card, slot, out = sys.argv[1:5]
    os.makedirs(out, exist_ok=True)
    shutil.copy(card, out + "/card.mcr")
    e = replay.boot(cue, out + "/card.mcr", int(slot))
    if os.environ.get("EXP"):
        e.poke(0x8007BA44, struct.pack("<H", int(os.environ["EXP"])))
    seq = ["right"] * 3 + ["down"] * 3 + ["right"] * 3 + ["up"] * 3
    for i in range(13):
        e.press(seq[i % 12], 45, 4)
    for _ in range(12):
        e.press("down", 100, 4)
        e.run(120)
        if B.units(e):
            break
    WT.install(e)
    for a, *_ in B.units(e):
        e.poke(a + 10, struct.pack("<H", 0))
    for _t in range(14):
        e.press("up", 6, 10)
        e.press("circle", 6, 10)
        e.run(60)
    for ev in WT.drain(e):
        tag, a0, a1, a2, a3, ra, x, y, c, r, codes, _hx = ev
        print(tag, hex(a0), hex(a1), hex(ra), (x, y, c, r), codes[:8] if codes else None, flush=True)


if __name__ == "__main__":
    main()
