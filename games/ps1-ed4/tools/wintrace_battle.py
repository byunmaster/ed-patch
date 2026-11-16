"""전투 순회 덫 — `sweep-1031/battle/auto_battle.py` 와 같은 입력(영웅이 적에게 다가가 공격)을 돌리며 `wintrace` 로 창 호출을 모은다(시험 전용).

   sh scripts/capture.sh python3 tools/wintrace_battle.py <cue> <card.mcr> <슬롯 내림 횟수> <출력.json> [턴 수]
환경: WT_EXTRA(다른 그리기 경로 입구, 쉼표 hex).
"""

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import replay  # noqa: E402
import wintrace  # noqa: E402
from PIL import Image  # noqa: E402


def find(a):
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    hero = (r > 150) & (g < 100) & (b < 80) & (r - g > 60)
    hero[170:, :] = False
    hero[:, 270:] = False
    en = (r > 215) & (g > 215) & (b > 170) & (b < 225) & (abs(r - g) < 14)
    en[170:, :] = False

    def cen(m):
        ys, xs = np.nonzero(m)
        return (xs.mean(), ys.mean(), len(xs)) if len(xs) >= 4 else None

    return cen(hero), cen(en)


def main():
    cue, card, slot, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    turns = int(sys.argv[5]) if len(sys.argv) > 5 else 30
    tmp = out + ".card.mcr"
    shutil.copy(card, tmp)
    e = replay.boot(cue, tmp, slot)
    seq = ["right"] * 3 + ["down"] * 3 + ["right"] * 3 + ["up"] * 3
    for k in range(13):
        e.press(seq[k % 12], 45, 4)
    for _ in range(1, 9):
        e.press("down", 100, 4)
    wintrace.install(e)
    allev = []
    shot = out + ".png"

    def snap():
        e.shot(shot)
        return np.asarray(Image.open(shot).convert("RGB")).astype(int)

    for turn in range(turns):
        a = snap()
        h, en = find(a)
        print(turn, h, en, flush=True)
        if h and en:
            dx, dy = en[0] - h[0], en[1] - h[1]
            for _ in range(3):
                if abs(dx) > abs(dy):
                    d = "right" if dx > 0 else "left"
                else:
                    d = "down" if dy > 0 else "up"
                e.press(d, 12, 30)
                if d in ("right", "left"):
                    dx -= 24 * (1 if dx > 0 else -1)
                else:
                    dy -= 24 * (1 if dy > 0 else -1)
        e.press("circle", 8, 40)
        e.run(20)
        b0 = snap()
        e.press("circle", 8, 40)
        e.run(60)
        b1 = snap()
        if np.abs(b1 - b0).mean() > 8:
            for _ in range(12):
                e.run(40)
            for _ in range(2):
                e.press("circle", 8, 40)
                e.run(60)
            allev += wintrace.drain(e)
            continue
        e.press("cross", 8, 30)
        e.press("circle", 8, 40)
        e.run(20)
        for _ in range(3):
            e.press("up", 8, 20)
        e.press("circle", 8, 40)
        e.run(240)
        allev += wintrace.drain(e)
    allev += wintrace.drain(e)
    json.dump(allev, open(out, "w"))
    print("이벤트", len(allev), "열기", sum(1 for x in allev if x[0] == 1))


if __name__ == "__main__":
    main()
