"""장 전환 도착 맵 시험(시험 전용) — 장이 갈리는 맵 이동 연산(`14 방향 07 이름`)의 **도착 맵**마다 디버그 이동으로 서서 그 장 폴더에서 맵·이벤트가 뜨고 ○ 를 이어 눌러 진행되는지 본다.

   sh scripts/capture.sh python3 tools/chapter_warp.py <cue> <card.mcr> <출력폴더> <맵:방향,…> [○ 수]
화면 두 장(서자마자 · ○ n번 뒤)을 찍고 검은 화면·정지를 센다.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import debug_warp as W
import dialog_harness as D
import numpy as np
from PIL import Image


def main():
    cue, card, out, maps = sys.argv[1:5]
    n = int(sys.argv[5]) if len(sys.argv) > 5 else 60
    os.makedirs(out, exist_ok=True)
    e = D.make_state(cue, card, out + "/base.state")
    base = out + "/b.state"
    e.save(base)
    for spec in maps.split(","):
        name, d = spec.split(":")
        e.load(base)
        e.run(1)
        W.warp(e, name, int(d), b"\0\0\0", settle=120)
        p0 = f"{out}/{name}_0.png"
        e.shot(p0)
        for _ in range(n):
            e.press("circle", 6, 40)
        p1 = f"{out}/{name}_1.png"
        e.shot(p1)
        a, b = (np.asarray(Image.open(p).convert("L")).astype(int) for p in (p0, p1))
        print(
            name,
            "검음" if a.mean() < 3 else "",
            "변화",
            round(float(np.abs(a - b).mean()), 1),
            flush=True,
        )


if __name__ == "__main__":
    main()
