"""엔딩 도달 시험 — 디버그 이동으로 맵에 선 뒤 ○ 를 이어 누르며 진행을 찍는다(시험 전용, 제품 롬 불변).

   sh scripts/capture.sh python3 tools/ending_run.py <cue> <card.mcr> <맵:방향> <출력폴더> [반복 수] [찍는 간격]
맵 이동 연산으로 서고(`debug_warp.warp`), ○ 를 누르며 `간격` 번마다 한 장 찍는다. 같은 화면이 오래 이어지면 「정지」로 센다.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import debug_warp as W
import dialog_harness as D
import numpy as np
from PIL import Image


def find(a):
    """영웅(붉은 머리 색)·적(옅은 초록 흰색) 화면 위치 — `sweep-1031/battle/auto_battle.py` 와 같은 색 기준."""
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


def buff(e):
    """파티 구조체 강화(HP·MP 9999 · 능력치 바이트) — 긴 전투에선 매 턴 다시 쓴다(안 쓰면 영웅이 쓰러져 타이틀로 돌아간다)."""
    import struct

    for i in range(6):
        b = 0x8007BA30 + 40 * i
        e.poke(b + 2, struct.pack("<4H", 9999, 9999, 9999, 9999))
        e.poke(b + 10, bytes([int(os.environ["BUFF"])] * 8))


def auto_turns(e, out, turns):
    """전투 자동 입력 — 영웅이 적에게 다가가 「공격」(`auto_battle.py` 와 같은 순서)."""
    shot = out + "/_a.png"

    def snap():
        e.shot(shot)
        return np.asarray(Image.open(shot).convert("RGB")).astype(int)

    for t in range(turns):
        if (
            os.environ.get("SAVE_EVERY") and t % int(os.environ["SAVE_EVERY"]) == 0
        ):  # 긴 전투 — 중간 상태를 남겨 거기서 RAM 탐색·재개한다
            e.save(f"{out}/s{t:04d}.state")
        if os.environ.get("REBUFF"):
            buff(e)
        h, en = find(snap())
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
            e.shot(f"{out}/t{t:03d}.png")
            continue
        e.press("cross", 8, 30)
        e.press("circle", 8, 40)
        e.run(20)
        for _ in range(3):
            e.press("up", 8, 20)
        e.press("circle", 8, 40)
        e.run(240)
        e.shot(f"{out}/t{t:03d}.png")


def main():
    cue, card, spec, out = sys.argv[1:5]
    n = int(sys.argv[5]) if len(sys.argv) > 5 else 300
    every = int(sys.argv[6]) if len(sys.argv) > 6 else 10
    os.makedirs(out, exist_ok=True)
    name, d = spec.split(":")
    e = D.make_state(cue, card, out + "/base.state")
    if os.environ.get("RESUME"):  # 저장해 둔 중간 상태에서 이어 간다(워프·강화·대사 건너뛰기 생략)
        e.load(os.environ["RESUME"])
        e.run(1)
        auto_turns(e, out, int(os.environ.get("AUTO_TURNS", "40")))
        return
    W.warp(e, name, int(d), b"\0\0\0", settle=120)
    if os.environ.get(
        "BUFF"
    ):  # 파티 구조체(0x8007BA30 부터 40B 간격 6칸): +2 HP · +4 MP · +6 최대 HP · +8 최대 MP · +10~17 능력치 바이트 — 보스전 시험용 강화
        import struct

        for i in range(6):
            b = 0x8007BA30 + 40 * i
            e.poke(b + 2, struct.pack("<4H", 9999, 9999, 9999, 9999))
            e.poke(b + 10, bytes([int(os.environ["BUFF"])] * 8))
    if os.environ.get("AUTO_AFTER"):  # 처음 N 번 ○ 로 대사를 넘긴 뒤 전투 자동 입력으로 바꾼다
        for _ in range(int(os.environ["AUTO_AFTER"])):
            e.press("circle", 6, 50)
        auto_turns(e, out, int(os.environ.get("AUTO_TURNS", "40")))
    prev, still, k = None, 0, 0
    for i in range(n):
        pat = [
            x for x in os.environ.get("PATTERN", "circle").split(",") if x
        ]  # 입력 순환 — 전투에서 적 쪽으로 이동 뒤 「공격」을 누르는 열
        e.press(pat[i % len(pat)], 6, 50)
        if i % every == 0:
            p = f"{out}/r{k:03d}.png"
            e.shot(p)
            cur = np.asarray(Image.open(p).convert("L")).astype(int)
            if prev is not None and float(np.abs(cur - prev).mean()) < 0.3:
                still += 1
            else:
                still = 0
            prev = cur
            print(i, "정지" if still else "", still, flush=True)
            k += 1
    print("끝", k, "장", flush=True)


if __name__ == "__main__":
    main()
