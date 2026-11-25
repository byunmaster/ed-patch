"""**ED1 HUD 지명(우하단 상자) 실화면 전수** — HUD 그리기 함수(`ED.BIN` 0x0607968C)를 씬 헤더 이름마다 직접 불러(공유 버퍼 0x060BF3E0 에 이름을 쓰고) 좌·우 여백을 잰다(걷기 없음·이미지 안 고침).

    python3 tools/ss_hud_call.py --out <폴더> [--state <ED1 필드 스테이트>]

상자 안쪽 x=208~313(106px) · 잉크 = 흰 화소. ED2 는 씬 불러오기(`ss_banner_shots.py --all`)로 같은 상자를 잰다.
"""

import argparse
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import ss_battle_sweep as B
import ss_headless as H
import ss_scene_sweep as S

FUNC, BUF = 0x0607968C, 0x060BF3E0
X0, X1, Y0, Y1 = 208, 313, 211, 224


def measure(frame):
    sub = frame[Y0 : Y1 + 1, X0 : X1 + 1].astype(int)
    cols = np.where((sub > 200).all(axis=2).any(axis=0))[0]
    return (int(cols.min()), int(X1 - X0 - cols.max())) if len(cols) else None


def headers():
    f, mm = common.open_image(glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))[0])
    out = {}
    try:
        for p, lba, s in common.iso_files(mm):
            if p.startswith("/BIN/ED1SCN"):
                raw = common.read_extent(mm, lba, s)[:16].split(b"\0")[0]
                if raw:
                    out.setdefault(raw, p)
    finally:
        mm.close()
        f.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--state", default=None)
    a = ap.parse_args()
    cue = os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue")
    S.configure("ed1")
    st = a.state or os.path.join(H.CACHE, "beetle-saturn", f"ed1_field_{B.image_key(cue)}.state")
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
    rows = []
    for raw, path in sorted(headers().items(), key=lambda kv: kv[1]):
        h.load(snap)
        h.run(2)
        h.poke(BUF, raw + b"\0" * 6)
        S.p32(h, S.MB + 4, 0)
        S.p32(h, S.MB + 12, 0)
        S.p32(h, S.MB, FUNC)
        h.run(10)
        m = measure(h.frame)
        Image.fromarray(h.frame[203:230, 204:318]).save(os.path.join(a.out, f"h_{raw.hex()}.png"))
        rows.append(
            {"path": path, "hex": raw.hex(), "n": len(raw), "L": m and m[0], "R": m and m[1]}
        )
        print(path, raw.hex(), m, flush=True)
    with open(os.path.join(a.out, "hud.json"), "w", encoding="utf-8") as jf:
        json.dump(rows, jf, ensure_ascii=False, indent=1)
    os.remove(snap)


if __name__ == "__main__":
    main()
