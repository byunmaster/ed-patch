"""ED2 **입장 배너·HUD 실화면** — 맵·구역을 직접 써서 마을을 부르며 로드 직후 프레임을 10프레임마다 저장한다(걷기 없음, 롬·이미지 안 고침).

python3 tools/ss_banner_shots.py --state <ED2 필드 스테이트> --out <폴더> --towns 2-1 5-2 [--cue <이미지>]
"""

import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import ss_battle_sweep as B
import ss_headless as H
import ss_scene_sweep as S
import ss_town_sweep_ed2 as T


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=None)
    ap.add_argument("--state", required=True)
    ap.add_argument("--towns", nargs="*", default=[])
    ap.add_argument(
        "--all",
        action="store_true",
        help="맵 0~17 × 구역 1~8 전부 — 마지막 프레임 한 장 + 장면 번호(index.json)",
    )
    ap.add_argument("--step", type=int, default=10)
    ap.add_argument("--frames", type=int, default=360)
    a = ap.parse_args()
    cue = a.cue or os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue")
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, cue, a.out, bkr=B.DEFAULT_BKR)
    code, _body = S.build_stub()
    import json

    towns = [f"{m}-{c}" for m in T.MAPS for c in T.SECS] if a.all else a.towns
    idx = {}
    for k in towns:
        mp, sec = map(int, k.split("-"))
        h.load(a.state)
        h.run(5)
        h.poke(S.HOOK, code)
        for q in range(0, 0x20, 4):
            S.p32(h, S.MB + q, 0)
        h.poke(S.TICK, S.hook_patch())
        h.run(30)
        h.poke(T.MAP_VAR, bytes([mp, sec]))
        S.p32(h, S.MB + 4, 0)
        S.p32(h, S.MB + 12, 0)
        S.p32(h, S.MB, T.SESSION)
        if a.all:
            h.run(300)
            scn = h.peek(T.SCENE_WORD, 2).hex()
            idx[k] = scn
            if scn != "0006":
                Image.fromarray(h.frame).save(os.path.join(a.out, f"t{mp:02d}s{sec}_{scn}.png"))
            with open(os.path.join(a.out, "index.json"), "w") as jf:
                json.dump(idx, jf)
            print("완료", k, scn, flush=True)
            continue
        for t in range(0, a.frames, a.step):
            h.run(a.step)
            Image.fromarray(h.frame).save(
                os.path.join(a.out, f"t{mp:02d}s{sec}_{t + a.step:03d}.png")
            )
        print("완료", k, flush=True)


if __name__ == "__main__":
    main()
