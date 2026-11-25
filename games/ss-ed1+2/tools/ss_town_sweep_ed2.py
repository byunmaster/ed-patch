#!/usr/bin/env python3
"""ED2 **마을 일괄(전 마을)** — 맵·구역 쌍을 직접 써서 마을을 불러 놓고, NPC 마다 이벤트 핸들러를 불러 대사 화면을 모두 찍는다(헤드리스 하네스, 롬·이미지 안 고침).

    python3 tools/ss_town_sweep_ed2.py --out <폴더> [--towns 2-1 5-2 …] [--grid-only]

🔴 **마을을 부르는 법(2026-11-06 실측 — emucap 실행 BP 로 로더를 찾은 결과)**
  1. 맵 `0x060A0804`·구역 `+1` 에 목표 쌍을 쓴다(맵만 쓰면 장면 번호 워드가 안 바뀌어 로드가 안 된다).
  2. 틱 스텁(`ss_scene_sweep`)으로 **장면 세션 함수 `0x0602AC1C`** 를 부른다 — 첫 호출이 로더 `0x06030FEC`(쌍 → 장면 번호 → 현재 번호 워드
     `0x060A0B30` 와 다르면 `ED2SCN%02d.BIN` 을 `0x060B8000` 에 읽는다)이고 뒤따라 장면 초기화까지 이어진다. 300프레임 뒤 마을이 깨끗이 뜬다.
  3. 시작 스테이트는 아무 필드 상태면 된다(여기선 루디아 성 — 프롤로그 `c`×19).
🔴 **NPC 에게 말 거는 법** — 좌표 순간이동은 ED2 에서 먹지 않는다(위치 변수가 화면·충돌과 따로다). 대신 **이벤트 핸들러(`0x060A0800` 이 가리키는 함수)를
  `핸들러(NPC 번호)` 로 부르면** 그 NPC 의 대사창이 뜬다. 대사가 끝나면 돌아오고, 선택지(예/아니오)에서는 창이 안 뜨고 멈춘다(알려진 한계).
NPC 표: 레코드 0x14 바이트, 첫 칸 `0x0609E40C`(`ss_shop_sweep_ed2.npcs`).
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import ss_battle_sweep as B
import ss_headless as H
import ss_scene_sweep as S
import ss_shop_sweep_ed2 as E

E.PANEL = np.array([0, 0, 127])  # 대화창 바탕색(ED2 새턴판은 127)
SESSION = 0x0602AC1C  # 장면 세션 함수 — 로더 0x06030FEC 를 첫 호출로 갖는다
MAP_VAR = 0x060A0804
SCENE_WORD = 0x060A0B30
HANDLER_PTR = 0x060A0800
MAPS = range(0, 18)
SECS = range(1, 9)


def castle_state(path):
    """시작 스테이트 — 필드에서 자유 이동이 되는 아무 ED2 스테이트(성 알현 이벤트가 끝난 루디아 성 상태를 썼다).
    🔴 프롤로그를 `c` 로 밀어 만든 스테이트는 이벤트 도중(대화창)에 저장되기 쉽다 — 자유 이동이 되는지(골드 3000) 눈으로 확인하고 쓴다."""
    assert os.path.exists(path), f"시작 스테이트가 없다: {path} (--state)"
    return path


def go(h, nav, code, mp, sec):
    """스테이트 → 스텁 설치 → 목표 쌍을 쓰고 세션 함수 호출 → 300프레임."""
    h.load(nav)
    h.run(5)
    h.poke(S.HOOK, code)
    for q in range(0, 0x20, 4):
        S.p32(h, S.MB + q, 0)
    h.poke(S.TICK, S.hook_patch())
    h.run(30)
    h.poke(MAP_VAR, bytes([mp, sec]))
    S.p32(h, S.MB + 4, 0)
    S.p32(h, S.MB + 12, 0)
    S.p32(h, S.MB, SESSION)
    h.run(300)


def text_px(frame):
    """대사창(바탕 0,0,127 이 절반 넘는 위·아래 창) 안의 흰 글자 화소 수 — 빈 창은 0 에 가깝다."""
    best = 0
    for y0, y1 in ((16, 98), (150, 204)):
        reg = frame[y0:y1, 16:200]
        if (reg == E.PANEL).all(axis=2).mean() > 0.5:
            best = max(best, int((reg > 200).all(axis=2).sum()))
    return best


def talk(h, st, fn, k, tag, max_steps=40):
    """→ (글자 있는 장 수, 빈 창만 찍은 장 수). 빈 창은 원판에서도 같은 연출 NPC(카메라 이동 이벤트 등)다 — `kept` 는 앞 값."""
    h.load(st)
    h.run(2)
    S.p32(h, S.MB + 4, k)
    S.p32(h, S.MB + 12, 0)
    S.p32(h, S.MB, fn)
    h.run(200)
    kept = blank = calm = 0
    for i in range(max_steps):
        dlg, top = E.state_of(h.frame)
        if dlg or top:
            h.shot(f"{tag}_{i:02d}")
            if text_px(h.frame) >= 20:
                kept += 1
            else:
                blank += 1
            calm = 0
        else:
            calm += 1
            if calm >= 6:
                break
        h.press("c", 12, 60)
    return kept, blank


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=None)
    ap.add_argument("--state", required=True, help="ED2 필드 스테이트(자유 이동 상태)")
    ap.add_argument(
        "--towns",
        nargs="*",
        default=[],
        help="맵-구역 쌍(예 2-1). 없으면 격자 전체에서 서로 다른 NPC 표 하나씩",
    )
    ap.add_argument(
        "--grid-only",
        action="store_true",
        help="격자(맵 0~17 × 구역 1~8)의 장면 번호·NPC 표만 뽑는다",
    )
    a = ap.parse_args()
    cue = a.cue or os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue")
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, cue, a.out, bkr=B.DEFAULT_BKR)
    nav = castle_state(a.state)
    code, body = S.build_stub()
    S.verify_stub(code, body)

    grid_path = os.path.join(a.out, "grid.json")
    if os.path.exists(grid_path):
        grid = json.load(open(grid_path))
    else:
        grid = {}
        for mp in MAPS:
            for sec in SECS:
                go(h, nav, code, mp, sec)
                scn = h.peek(SCENE_WORD, 2).hex()
                grid[f"{mp}-{sec}"] = {"scn": scn, "npcs": E.npcs(h) if scn != "0006" else []}
                print("grid", mp, sec, scn, len(grid[f"{mp}-{sec}"]["npcs"]), flush=True)
        json.dump(grid, open(grid_path, "w"), ensure_ascii=False)
    if a.grid_only:
        return

    sig = {}
    for k, v in grid.items():
        if v["npcs"]:
            sig.setdefault((v["scn"], tuple((n["type"], n["x"], n["y"]) for n in v["npcs"])), k)
    idx = {}
    for key, k in sig.items():
        if a.towns and k not in a.towns:
            continue
        mp, sec = map(int, k.split("-"))
        go(h, nav, code, mp, sec)
        fn = int.from_bytes(h.peek(HANDLER_PTR, 4), "big")
        st = os.path.join(a.out, f"town_{k}.state")
        h.save(st)
        n = len(key[1])
        idx[k] = {"scn": key[0], "handler": hex(fn), "kept": []}
        for q in range(n):
            kept, blank = talk(h, st, fn, q, f"t{mp:02d}s{sec}_n{q:02d}")
            idx[k]["kept"].append(kept)
            idx[k].setdefault("blank", []).append(blank)
            print(k, q, kept, blank, flush=True)
        os.remove(st)
        json.dump(idx, open(os.path.join(a.out, "index.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
