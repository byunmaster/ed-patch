"""보스 직전 세이브(마스터 카드 페이지 2 슬롯 1)를 불러 필드에서 입력 열을 먹이며 쪽마다 찍는다(시험 전용) — 필드 메뉴 안쪽 화면(마법 설명 등) 도달용.

   sh scripts/capture.sh python3 tools/menu_keys.py <cue> <card.mcr> <출력폴더> <키열(쉼표)>
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness  # noqa: F401
import headless_ps1 as H


def main():
    cue, card, out, keys = sys.argv[1:5]
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
    e.run(200)
    if os.environ.get("POKE"):  # POKE=오프셋,값 — 파티 첫 칸(0x8007BA30) 상태 후보 바이트에 값을 쓴다
        off, val = (int(v, 0) for v in os.environ["POKE"].split(","))
        e.poke(0x8007BA30 + off, bytes([val]))
    for i, k in enumerate(keys.split(",")):
        e.press(k, 8, 40)
        e.run(40)
        e.shot(f"{out}/k{i:02d}_{k}.png")


if __name__ == "__main__":
    main()
