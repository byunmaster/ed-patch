"""전투 명령창에서 입력별 화면을 찍는다(시험 전용) — 몬스터 정보창 찾기.
   sh scripts/capture.sh python3 tools/btl_info_probe.py <cue> <card.mcr> <맵:방향> <출력폴더>"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import debug_warp as W
import dialog_harness as D


def main():
    cue, card, spec, out = sys.argv[1:5]
    os.makedirs(out, exist_ok=True)
    name, d = spec.split(":")
    e = D.make_state(cue, card, out + "/base.state")
    W.warp(e, name, int(d), b"\0\0\0", settle=120)
    for i in range(6):
        b = 0x8007BA30 + 40 * i
        e.poke(b + 2, struct.pack("<4H", 9999, 9999, 9999, 9999))
        e.poke(b + 10, bytes([250] * 8))
    for _ in range(6):
        e.press("circle", 6, 50)
    e.run(120)
    e.shot(out + "/00.png")
    for k, seq in enumerate(["triangle", "square", "select", "start", "cross", "r1", "l1", "r2", "l2"], 1):
        e.press(seq, 8, 40)
        e.run(60)
        e.shot(f"{out}/{k:02d}_{seq}.png")
    e.save(out + "/btl.state")


if __name__ == "__main__":
    main()
