"""세이브 정식 로드 증명(시험 전용) — 새로 띄워 타이틀에서 메모리카드를 불러 첫 화면을 찍는다.

sh scripts/capture.sh python3 tools/boss_save_load.py <cue> <card.mcr> <출력폴더> [키열]
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness  # noqa: F401  (경로·drc 설정)
import headless_ps1 as H


def main():
    cue, card, out = sys.argv[1:4]
    keys = [k for k in (sys.argv[4] if len(sys.argv) > 4 else "").split(",") if k]
    os.makedirs(out, exist_ok=True)
    shutil.copy(card, out + "/card.mcr")
    e = H.Emu(cue, card=out + "/card.mcr")
    e.run(600)
    e.shot(out + "/t00.png")
    for i, k in enumerate(keys):
        e.press(k, 8, 60)
        e.run(120)
        e.shot(f"{out}/t{i + 1:02d}_{k}.png")


if __name__ == "__main__":
    main()
