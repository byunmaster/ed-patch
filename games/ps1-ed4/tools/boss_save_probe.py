"""보스전 직전 세이브 만들기 탐침(시험 전용) — GT07000 으로 이동한 뒤 단계마다 화면을 찍는다.

sh scripts/capture.sh python3 tools/boss_save_probe.py <cue> <card.mcr> <출력폴더> [○ 횟수]
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import debug_warp as W
import dialog_harness as D


def main():
    cue, card, out = sys.argv[1:4]
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    os.makedirs(out, exist_ok=True)
    shutil.copy(card, out + "/card.mcr")
    e = D.make_state(cue, out + "/card.mcr", out + "/base.state")
    W.warp(
        e,
        os.environ.get("MAP", "GT07000"),
        int(os.environ.get("DIR", "0")),
        bytes.fromhex(os.environ.get("ARGS", "000000")),
        settle=200,
    )
    e.shot(out + "/w00.png")
    for i in range(n):
        e.press("triangle" if False else "circle", 6, 50)
        e.run(30)
        e.shot(f"{out}/w{i + 1:02d}.png")
    e.save(out + "/pre.state")


if __name__ == "__main__":
    main()
