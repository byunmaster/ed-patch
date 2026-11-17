"""보스 직전 세이브 → 오크툼 전투 → 공격 입력 열 시험(시험 전용). 페이지2 슬롯1 로드 후 위로 걸어 전투가 시작되면 보스 HP 를 1 로 쓰고 입력 열(SEQ, 쉼표)을 돌며 화면을 찍는다.

   sh scripts/capture.sh python3 tools/boss_save_attack.py <cue> <card.mcr> <출력폴더>
환경: SEQ(기본 circle,circle) · REP(열 반복 수) · HP
"""

import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness  # noqa: F401
import headless_ps1 as H

BOSS = 0x801FF9AA
HERO = 0x801FF81A


def main():
    cue, card, out = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    shutil.copy(card, out + "/card.mcr")
    e = H.Emu(cue, card=out + "/card.mcr")
    e.run(600)
    for j in range(12):
        e.press("circle", 8, 60)
        e.run(120)
        if j == 5:
            e.press("down", 8, 60)
            e.run(120)
    for _ in range(8):
        e.press("up", 10, 6)
    for i in range(400):  # noqa: B007 — 끝난 번호를 아래에서 쓴다
        e.press("circle", 6, 50)
        hd, uid = struct.unpack("<2H", e.peek(0x801FF9A0, 4))
        if hd == 0xC000 and uid == 1:
            break
    print("전투", i, flush=True)
    for _ in range(10):
        e.press("cross", 6, 20)
    e.run(60)
    e.poke(BOSS, struct.pack("<H", int(os.environ.get("HP", "1"))))
    k = 0
    seq = os.environ.get("SEQ", "circle,circle").split(",")
    for r in range(int(os.environ.get("REP", "6"))):
        for s in seq:
            e.poke(HERO, struct.pack("<H", 9999))
            e.press(s, 8, 40)
            e.run(int(os.environ.get("GAP", "40")))
            e.shot(f"{out}/s{k:03d}_{s}.png")
            k += 1
        print(r, struct.unpack("<H", e.peek(BOSS, 2))[0], flush=True)


if __name__ == "__main__":
    main()
