"""**ED1 월드맵 HUD 지명 + 방향 접미(입구·부근·방위) 조합 실화면** — 접미 조립 루틴(`ED.BIN` 0x0606CBE8, 원판·우리 같은 자리)에 월드 좌표를 넣어 부르고,
조립된 글을 HUD 그리기 함수(0x0607968C)로 그려 좌·우 여백을 잰다(걷기 없음·이미지 안 고침).

    python3 tools/ss_hud_suffix.py --out <폴더> [--cue <이미지>] [--towns 0-47] [--probe]

좌표: `0x060B8A04`(x)·`0x060B8A08`(y) = 타일×8 (루틴이 (좌표+4)>>3 으로 타일을 얻는다). 마을 표 `0x060AC6A2`(4B: x,y 타일) · 이름 표 `0x060AC762`+색인×14.
"""

import argparse
import json
import os
import struct
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import ss_battle_sweep as B
import ss_headless as H
import ss_scene_sweep as S
from ss_hud_call import BUF, FUNC, measure

COMPOSE = 0x0606CBE8
POS = 0x060F7400  # 루틴이 읽는 월드 좌표 구조(원래 0x060B8A00 — 게임이 틱마다 덮어 쓴다) — 루틴의 리터럴(0x0606CE50)을 이 사본으로 돌려 쓴다
POS_LIT = 0x0606CE50
TOWNS = 0x060AC6A2
OUTBUF = S.MB + 0x300


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=None)
    ap.add_argument("--towns", default="0-47")
    ap.add_argument(
        "--offsets", default="0,0;1,0;-1,0;0,1;0,-1;2,2;-2,-2;3,0;-3,0;0,3;0,-3;5,5;-5,-5"
    )
    a = ap.parse_args()
    cue = a.cue or os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue")
    S.configure("ed1")
    st = os.path.join(H.CACHE, "beetle-saturn", f"ed1_field_{B.image_key(cue)}.state")
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, cue, a.out, bkr=B.DEFAULT_BKR)
    if not os.path.exists(st):
        S.boot_to_field_ed1(h)
        h.save(st)
    code, _ = S.build_stub()
    h.load(st)
    h.run(5)
    h.poke(S.HOOK, code)
    for q in range(0, 0x20, 4):
        S.p32(h, S.MB + q, 0)
    h.poke(S.TICK, S.hook_patch())
    h.run(30)
    snap = os.path.join(a.out, "_snap.state")
    h.save(snap)
    lo, hi = (int(x) for x in a.towns.split("-"))
    offs = [tuple(int(v) for v in p.split(",")) for p in a.offsets.split(";")]
    rows = []
    for t in range(lo, hi + 1):
        tx, ty = struct.unpack(">hh", h.peek(TOWNS + 4 * t, 4))
        for ox, oy in offs:
            h.load(snap)
            h.run(2)
            S.p32(h, POS_LIT, POS)
            S.p32(h, POS + 4, (tx + ox) * 8)
            S.p32(h, POS + 8, (ty + oy) * 8)
            h.poke(OUTBUF, b"\0" * 40)
            S.p32(h, S.MB + 4, OUTBUF)
            S.p32(h, S.MB + 12, 0)
            S.p32(h, S.MB, COMPOSE)
            h.run(1)
            raw = h.peek(OUTBUF, 40).split(b"\0")[0]
            h.poke(BUF, raw + b"\0" * 8)
            S.p32(h, S.MB + 4, 0)
            S.p32(h, S.MB, FUNC)
            h.run(10)
            m = measure(h.frame)
            key = f"t{t:02d}_{ox}_{oy}"
            Image.fromarray(h.frame[203:230, 204:318]).save(os.path.join(a.out, f"{key}.png"))
            rows.append(
                {
                    "town": t,
                    "ox": ox,
                    "oy": oy,
                    "hex": raw.hex(),
                    "n": len(raw),
                    "L": m and m[0],
                    "R": m and m[1],
                }
            )
            print(key, raw.hex(), m, flush=True)
    with open(os.path.join(a.out, "suffix.json"), "w", encoding="utf-8") as jf:
        json.dump(rows, jf, ensure_ascii=False, indent=1)
    os.remove(snap)


if __name__ == "__main__":
    main()
