"""보스전 직전 세이브 만들기(시험 전용, 제품 롬 불변) — GT06000(보스 직전 맵)으로 이동 → 파티 강화(RAM) → 보스 이벤트 몇 걸음 앞으로 순간이동 → 게임 자체 세이브 메뉴로 저장 → 메모리카드를 `.mcr` 로 읽어 낸다.

   sh scripts/capture.sh python3 tools/boss_save_make.py <cue> <card.mcr> <출력.mcr> <출력폴더> [키열]
키열 = 세이브 메뉴 조작(쉼표 목록, 화면 확인으로 맞춘다). 카드는 사본에서 쓴다. 환경: BUFF(능력치 바이트, 기본 120) · X,Y(순간이동 타일, 기본 45,17).
"""

import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import debug_warp as W
import debug_warp_npc as N
import dialog_harness as D
from make_shop_save import card_bytes


def main():
    cue, card, outmcr, out = sys.argv[1:5]
    keys = [k for k in (sys.argv[5] if len(sys.argv) > 5 else "triangle").split(",") if k]
    os.makedirs(out, exist_ok=True)
    shutil.copy(card, out + "/card.mcr")
    e = D.make_state(cue, out + "/card.mcr", out + "/base.state")
    W.warp(e, "GT06000", 0, b"\0\0\0", settle=200)
    for i in range(6):
        b = 0x8007BA30 + 40 * i
        e.poke(b + 2, struct.pack("<4H", 9999, 9999, 9999, 9999))
        e.poke(b + 10, bytes([int(os.environ.get("BUFF", "120"))] * 8))
    N.teleport(e, int(os.environ.get("X", "45")), int(os.environ.get("Y", "17")))
    e.run(40)
    e.shot(out + "/pos.png")
    before = card_bytes(e)
    for i, k in enumerate(keys):
        e.press(k, 8, 40)
        e.run(int(os.environ.get("WAIT", "30")))
        e.shot(f"{out}/k{i:02d}_{k}.png")
    e.run(600)
    e.shot(out + "/after.png")
    after = card_bytes(e)
    print(
        "카드 바뀐 바이트",
        sum(1 for p, q in zip(before, after, strict=False) if p != q),
        flush=True,
    )
    with open(outmcr, "wb") as f:
        f.write(after)
    e.save(out + "/end.state")


if __name__ == "__main__":
    main()
