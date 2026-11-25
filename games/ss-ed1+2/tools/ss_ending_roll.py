#!/usr/bin/env python3
"""엔딩 연출(낭독 · 스태프롤)을 끝까지 훑어 일정 간격으로 화면을 저장한다 — **`patch_title.py --apply --entry-swap` 시험 이미지 전용**.

    ED_BUILD_TAG=test-oe-entry python3 tools/patch_title.py --apply --entry-swap      # 타이틀에서 선택하면 엔딩 루틴이 돈다(오프닝 아님)
    python3 tools/ss_ending_roll.py --game ed1 --out <폴더> [--every 150 --frames 30000]

🔴 배포 롬에는 이 진입이 없다 — 제품 롬과 TITLE.BIN 4B 차이(진입 리터럴)·KANJI.FON 동일을 대조한 시험 이미지로만 본다. 롬은 안 고친다.
ED1 은 `start` → `c`, ED2 는 `start` → `right` → `c` 로 고른다(타이틀 입력은 `ss_battle_sweep.boot_to_field` 와 같다).
"""

import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ss_battle_sweep as B
import ss_headless as H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", choices=("ed1", "ed2"), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=None)
    ap.add_argument("--every", type=int, default=150)
    ap.add_argument("--frames", type=int, default=30000)
    ap.add_argument("--start", type=int, default=0, help="선택 뒤 이 프레임부터 저장한다(앞부분 낭독을 건너뛴다)")
    a = ap.parse_args()
    import common

    cue = a.cue or os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue")
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, cue, a.out, bkr=B.DEFAULT_BKR)
    h.run(2500)
    h.press("start", 6, 120)
    if a.game == "ed2":
        h.press("right", 5, 20)
    h.press("c", 5, 10)
    t, last = 0, None
    while t < a.frames:
        h.run(a.every)
        t += a.every
        fr = h.frame
        if t >= a.start:
            Image.fromarray(fr).save(os.path.join(a.out, f"t{t:05d}.png"))
        key = fr.tobytes()
        if key == last:
            print(f"[{t}] 화면이 안 바뀐다 — 끝났거나 멈췄다", flush=True)
        last = key
    print("끝", t, flush=True)


if __name__ == "__main__":
    main()
