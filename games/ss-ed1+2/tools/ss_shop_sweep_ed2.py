#!/usr/bin/env python3
"""ED2 **마을 NPC 일괄(파렌 한 곳)** — ED2 필드 스테이트(프롤로그, 맵 0·구역 1)에서 위 키를 길게 눌러 파렌 마을(맵 1·구역 1)로 들어간 뒤,
마을 NPC 표를 돌며 옆 칸으로 순간이동해 말을 걸고 대화창·목록 창이 뜬 화면을 모두 찍는다(헤드리스 하네스, 롬·이미지 안 고침).

    python3 tools/ss_shop_sweep_ed2.py --out <폴더>

🔴 **입구 표가 아니다** — 이 스테이트는 프롤로그 스크립트 안이라 **임의 좌표에서 위 키를 60~70프레임 누르면** 같은 마을로 들어간다(좌표 입구 시험에서
확인, 2026-11-06). 그래서 이 길로 얻는 마을은 파렌 하나뿐이다. 다른 마을은 프롤로그를 끝낸 월드맵 상태가 있어야 한다.
NPC 표(실측 2026-11-06): 레코드 0x14 바이트, 첫 칸 `0x0609E40C`, 칸마다 `+5` 종류 · `+8` x(u32) · `+12` y(u32) · `+16` 플래그. `+4 == 0x80` 이거나
종류가 0 이면 끝. 주인공 좌표는 `0x0609E3F4`(x u32) · `+4`(y u32).
"""

import argparse
import json
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import ss_battle_sweep as B
import ss_headless as H

HERO = 0x0609E3F4
NPC0 = 0x0609E40C
STRIDE = 0x14
DIRS = (("down", 0, -24), ("up", 0, 24), ("left", 24, 0), ("right", -24, 0))  # (누르는 키, 오프셋) — NPC 위에서 누르면 아래를 보고 말을 건다
PANEL = np.array([0, 0, 128])
DLG = (148, 208, 14, 208)
TOP = (8, 100, 14, 200)


def panel(frame, box):
    y0, y1, x0, x1 = box
    return float((frame[y0:y1, x0:x1] == PANEL).all(axis=2).mean())


def state_of(frame):
    return panel(frame, DLG) > 0.30, panel(frame, TOP) > 0.03


def npcs(h):
    out = []
    for k in range(0, 24):
        r = h.peek(NPC0 + STRIDE * k, STRIDE)
        if r[4] == 0x80 or r[5] == 0:
            break
        out.append({"k": k, "type": r[5], "x": struct.unpack(">i", r[8:12])[0], "y": struct.unpack(">i", r[12:16])[0], "fl": r[16:20].hex()})
    return out


def place(h, x, y):
    h.poke(HERO, struct.pack(">ii", x, y))


def talk_all(h, town, n, tag, max_steps=40):
    for key, dx, dy in DIRS:
        h.load(town)
        place(h, n["x"] + dx, n["y"] + dy)
        h.run(70)
        h.press(key, 12, 70)
        dlg, top = state_of(h.frame)
        if not dlg:
            continue
        kept = calm = 0
        for i in range(max_steps):
            dlg, top = state_of(h.frame)
            if dlg or top:
                h.shot(f"{tag}_{key}_{i:02d}")
                kept += 1
                calm = 0
            else:
                calm += 1
                if calm >= 6:
                    break
            h.press("c", 12, 60)
        return {"key": key, "frames": kept}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=None)
    a = ap.parse_args()
    cue = a.cue or os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue")
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, cue, a.out, bkr=B.DEFAULT_BKR)
    nav = os.path.join(H.CACHE, "beetle-saturn", f"ed2_field_{B.image_key(cue)}.state")
    if not os.path.exists(nav):
        B.boot_to_field(h)
        h.save(nav)
    h.load(nav)
    h.run(5)
    h.held = {H.BTN["up"]}
    h.run(90)
    h.held = set()
    h.run(300)
    assert h.peek(0x060A0804, 2) == b"\x01\x01", "파렌 마을에 못 들어갔다"
    town = os.path.join(a.out, "paren.state")
    h.save(town)
    lst = npcs(h)
    print("NPC", len(lst), flush=True)
    index = {"map": 1, "sec": 1, "npcs": []}
    for n in lst:
        r = talk_all(h, town, n, f"npc{n['k']:02d}")
        index["npcs"].append({**n, "result": r})
        print("npc", n["k"], r, flush=True)
        with open(os.path.join(a.out, "index.json"), "w") as f:
            json.dump(index, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
