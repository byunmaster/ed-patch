#!/usr/bin/env python3
"""ED1 **마을 가게 일괄** — 월드맵 진입 코드의 구역 값을 바꿔 마을 모듈을 고르고, 마을 NPC 표에서 NPC 마다
옆 칸으로 순간이동해 말을 걸어 인사 · 목록 · 구입·판매 확인 화면을 찍는다(헤드리스 하네스 `ss_headless.py`, 롬·이미지 안 고침).

    python3 tools/ss_shop_sweep.py --make-world <bkr> --out <폴더>              # 월드맵(크루즈 출구) 스테이트를 만든다
    python3 tools/ss_shop_sweep.py --maps 5 --secs 1-3 --out <폴더>             # 마을(씬 파일 번호) · 구역 지정
    python3 tools/ss_shop_sweep.py --all --out <폴더>                           # 가게 대사가 있는 모든 (씬 파일 · 구역)

산출: `<out>/m05s3/npcK_<x>_<y>_b0_00.png …`(b0=기본 경로 · b1=두 번째 메뉴 항목 경로) + `<out>/index.json`
(마을 · 구역 · NPC 표 · 대화 화면 수 · 목록 창 여부).

## 구조 (2026-11-05 실측 — devlog 「네리아항구 무기점 화면」)
- 월드맵에서 마을 입구 칸에 서서 **마을 쪽(위)으로 한 번 더** 길게 눌러야 들어간다. 입구 코드(ED.BIN `0x06032AC4~`)는
  `0x060BF39E`(씬 파일 번호) · `0x060BF39F`(구역 1~5)를 즉시값(`e2NN` · `e1NN`)으로 쓴다 — 네리아 진입 코드의 두 명령
  (`0x06032AE2` · `0x06032AEC`)을 RAM 에서 덮으면 아무 마을·구역이나 올라온다.
- 월드맵 주인공 항목 `0x060B8A06`(x u16 · y u16 @+4) + 카메라 `0x060BC56C/E`(= 주인공 − (0x24,0x54)). 마을 안에서도 주인공
  좌표 쓰기가 먹는다(카메라는 늦게 따라온다).
- NPC 표: 주인공 항목에서 0x14 칸 단위. 한 칸 = 타입 바이트(+7) · x u16(+12) · y u16(+16) · 플래그(+18,+19). 표 끝은 +6 이 0x80.
- NPC 한 칸(0x20) 옆으로 순간이동해 그쪽으로 방향키를 누르면 말이 걸린다. 가게 주인은 카운터 뒤라 아래칸에서 위로 건다.
- 🔴 이 도구의 화면은 **디버그 이동**(순간이동 · 구역 값 조작)을 쓴 것이다 — 보고에 그렇게 적는다.
"""

import argparse
import json
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import ss_headless as H  # noqa: E402
from ss_battle_sweep import image_key  # noqa: E402

CORE = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
HERO = 0x060B8A06
CAM = 0x060BC56C
CUR_FILE = 0x060C42D0  # 지금 올라온 씬 파일 번호(u16)
MAP_IMM = 0x06032AE2  # `mov #맵,r2`
SEC_IMM = 0x06032AEC  # `mov #구역,r1`
ENTRY = (0x744, 0x3E4)  # 네리아 항구 입구 칸 — 이 칸의 진입 코드를 덮어 쓴다
DIRS = [(k, dx * m // 0x20, dy * m // 0x20) for m in (0x20, 0x10) for k, dx, dy in (("up", 0, 0x20), ("down", 0, -0x20), ("right", -0x20, 0), ("left", 0x20, 0))]  # (키, dx, dy) 키 방향의 반대쪽에 선다 — 한 칸(0x20) 다음 반 칸(0x10)


def u16(v):
    return struct.pack(">H", v & 0xFFFF)


def default_cue():
    return os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue")


def make_world(h, out, h_cue):
    """크루즈 세이브(백업 RAM 주입)로 부팅 → 불러오기 → 마을 남쪽 출구로 나가 월드맵에서 저장."""
    p = lambda b, hold=5, after=200: h.press(b, hold, after)  # noqa: E731
    h.run(1500)
    p("start", 5, 1500)
    p("c", 5, 200)
    p("start", 5, 200)
    p("c", 5, 300)
    p("start", 5, 300)
    p("c", 5, 1500)
    p("start", 5, 2100)
    p("right", 14, 60)
    p("c", 14, 90)
    p("c", 14, 120)
    p("c", 14, 200)
    p("c", 14, 450)
    p("down", 30, 300)
    h.save(os.path.join(out, "ed1_world_cruise.state"))
    with open(os.path.join(out, "ed1_world_cruise.state.key"), "w") as f:
        f.write(image_key(h_cue))


def enter(h, world, mapid, sec):
    h.load(world)
    h.run(5)
    # 🔴 월드맵 스테이트는 마지막 마을의 씬 파일을 RAM 에 든 채 저장돼 있고, 엔진은 「지금 파일 번호 == 요청 번호」면 다시 안 읽는다
    #    (`0x060C42D0`) — 그 마을이 **스테이트 속 옛 문안**으로 뜬다(크루즈 도구점이 일본어로 찍힌 오진, 2026-11-05). 번호를 0 으로 지워 늘 새로 읽게 한다.
    h.poke(CUR_FILE, b"\0\0")
    h.poke(MAP_IMM, bytes([0xE2, mapid]))
    h.poke(SEC_IMM, bytes([0xE1, sec]))
    x, y = ENTRY
    h.poke(HERO, u16(x) + b"\0\0" + u16(y))
    h.poke(CAM, u16(x - 0x24) + u16(y - 0x54))
    h.press("up", 1, 60)
    h.press("up", 30, 500)


def npcs(h):
    raw = h.peek(HERO, 0x14 * 20)
    out = []
    for k in range(1, 20):
        r = raw[k * 0x14 : (k + 1) * 0x14]
        if r[6] == 0x80 or r[7] == 0:
            break
        out.append({"k": k, "type": r[7], "x": struct.unpack(">H", r[12:14])[0], "y": struct.unpack(">H", r[16:18])[0], "fl": r[18:20].hex()})
    return out


PANEL = np.array([0, 0, 128])
DLG = (148, 208, 14, 208)
TOP = (8, 100, 14, 200)
MENU = (8, 70, 14, 90)


def panel(frame, box):
    """상자 안쪽 색(0,0,128)이 영역을 차지하는 비율 — 대화창 · 목록 · 메뉴 판정."""
    y0, y1, x0, x1 = box
    return float((frame[y0:y1, x0:x1] == PANEL).all(axis=2).mean())


def state_of(frame):
    """→ (대화창, 위쪽 창(목록·삽니다/팝니다·예/아니오))."""
    return panel(frame, DLG) > 0.30, panel(frame, TOP) > 0.03


def converse(h, frames, branch):
    """이미 말이 걸린 상태(frames[0])에서 대화를 끝까지 진행하며 화면을 모은다."""
    if branch == 1:
        h.press("down", 12, 20)
        h.press("c", 12, 60)
        frames.append(h.frame.copy())
    tops = 0
    for _ in range(10):
        dlg, top = state_of(frames[-1])
        if not (dlg or top):
            frames.pop()
            break
        if top:
            tops += 1
        if tops >= 3:
            h.press("b", 12, 60)
            frames.append(h.frame.copy())
            break
        h.press("c", 12, 60)
        frames.append(h.frame.copy())
    return frames


def talk(h, town, n, tag):
    """NPC n 에게 말 걸어 화면을 찍는다. 목록·메뉴 창이 뜨는 NPC(= 가게·여관·교회 …)의 화면만 남긴다.
    → {"key": 말 건 방향, "b0": 화면 수, "b1": 화면 수, "shop": 여부} 또는 None(말이 안 걸림)."""
    for key, dx, dy in DIRS:
        h.load(town)
        h.poke(HERO, u16(n["x"] + dx) + b"\0\0" + u16(n["y"] + dy))
        h.run(70)
        h.press(key, 12, 70)
        dlg, top = state_of(h.frame)
        if not dlg:
            continue
        res = {"key": key, "b0": 0, "b1": 0, "shop": False}
        first = h.frame.copy()
        runs = {0: converse(h, [first], 0)}
        res["shop"] = any(state_of(f)[1] for f in runs[0])
        if res["shop"] and panel(first, MENU) > 0.12:
            h.load(town)
            h.poke(HERO, u16(n["x"] + dx) + b"\0\0" + u16(n["y"] + dy))
            h.run(70)
            h.press(key, 12, 70)
            runs[1] = converse(h, [h.frame.copy()], 1)
        if res["shop"]:
            for br, frames in runs.items():
                for i, f in enumerate(frames):
                    h.frame = f
                    h.shot(f"{tag}_{key}_b{br}_{i:02d}")
                res[f"b{br}"] = len(frames)
        return res
    return None


def talk_all(h, town, n, tag, max_steps=40):
    """NPC 한 명과의 대화를 필드로 돌아올 때까지(최대 `max_steps`) `c` 로 끝까지 밀며 대화창이 뜬 화면을 모두 남긴다.
    가게가 아닌 NPC(이벤트 · 합류 · 보스 앞 대사)도 찍는 모드 — 전투가 걸리면 자동 전투를 `c` 로 밀고 가므로 이긴 뒤 이어지는 이벤트까지 간다."""
    for key, dx, dy in DIRS:
        h.load(town)
        h.poke(HERO, u16(n["x"] + dx) + b"\0\0" + u16(n["y"] + dy))
        h.run(70)
        h.press(key, 12, 70)
        dlg, top = state_of(h.frame)
        if not dlg:
            continue
        kept = 0
        calm = 0
        for i in range(max_steps):
            dlg, top = state_of(h.frame)
            if dlg or top:
                h.shot(f"{tag}_{key}_{i:02d}")
                kept += 1
                calm = 0
            else:
                calm += 1
                if calm >= 6:  # 대화창이 한동안 없다 = 필드로 돌아왔다(전투·연출 중이면 계속 민다)
                    break
            h.press("c", 12, 60)
        return {"key": key, "frames": kept}
    return None


def sweep_town(h, world, mapid, sec, out, everything=False):
    enter(h, world, mapid, sec)
    h.run(300)
    if h.peek(0x060BF39E, 1)[0] != mapid:
        return {"map": mapid, "sec": sec, "error": "진입 실패(월드맵에 남음)"}
    sub = os.path.join(out, f"m{mapid:02d}s{sec}")
    os.makedirs(sub, exist_ok=True)
    h.out = sub
    h.shot("town")
    tfile = os.path.join(sub, "town.state")
    h.save(tfile)
    lst = npcs(h)
    res = {"map": mapid, "sec": sec, "npcs": []}
    for n in lst:
        tag = f"npc{n['k']:02d}_{n['x']:03x}_{n['y']:03x}"
        r = talk_all(h, tfile, n, tag) if everything else talk(h, tfile, n, tag)
        res["npcs"].append({**n, "result": r})
    os.remove(tfile)
    return res


def all_towns():
    """씬 파일마다 지역 모듈(지명 헤더) 수 → [(씬 번호, 구역 1~n)] — 씬 파일 번호 = 맵 번호(월드맵 입구 코드의 `0x060BF39E`)."""
    import re

    import patch_ui

    f, mm = common.open_image()
    try:
        cnt = {}
        for r in patch_ui.scn_rows(mm):
            m = re.search(r"ED1SCN(\d+)\.BIN", r[0])
            if m and "헤더" in f"{r[0]}":
                pass
            if m:
                cnt.setdefault(int(m.group(1)), set()).add(r[3])
    finally:
        mm.close()
        f.close()
    return [(m, k) for m in sorted(cnt) for k in range(1, min(len(cnt[m]), 5) + 1)]


def ranges(s):
    out = []
    for part in s.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def world_fresh(world, cue):
    """월드 스테이트 옆 `.key`(만든 때의 이미지 지문)가 지금 이미지와 같은가 — 없으면 거짓."""
    try:
        with open(world + ".key") as f:
            return f.read().strip() == image_key(cue)
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cue", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--make-world", metavar="BKR")
    ap.add_argument("--maps", default=None)
    ap.add_argument("--secs", default="1")
    ap.add_argument("--world", default=None)
    ap.add_argument("--all", action="store_true", help="모든 씬 파일 × 구역")
    ap.add_argument("--everything", action="store_true", help="가게만이 아니라 모든 NPC 의 대화를 끝까지 찍는다")
    ap.add_argument("--timeout", type=int, default=900, help="마을 하나당 제한(초)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(CORE, a.cue or default_cue(), a.out, bkr=a.make_world)
    if a.make_world:
        make_world(h, a.out, a.cue or default_cue())
        return
    world = a.world or os.path.join(a.out, "ed1_world_cruise.state")
    # 🔴 스테이트는 만든 때의 **코드(ED.BIN)까지** 되살린다 — 이미지가 바뀌면(예: 조사 훅이 들어가기 전 이미지) 화면의 조사·문안이
    #    옛 코드 것이 된다(마스쿤 전투 「세리오스은(는)」 오진, 2026-11-05: 상태 RAM 의 훅 자리가 0). 이미지 지문이 다르면 멈춘다.
    if not world_fresh(world, a.cue or default_cue()):
        sys.exit(f"월드 스테이트가 지금 이미지의 것이 아니다({world}) — --make-world BKR 로 다시 만든다")
    import signal

    def boom(*_):
        raise TimeoutError

    signal.signal(signal.SIGALRM, boom)
    if a.all:
        keep = set(ranges(a.maps)) if a.maps else None
        pairs = [(m, k) for m, k in all_towns() if keep is None or m in keep]
    else:
        pairs = [(m, s) for m in ranges(a.maps or "5") for s in ranges(a.secs)]
    index = []
    for m, s in pairs:
        signal.alarm(a.timeout)
        try:
            index.append(sweep_town(h, world, m, s, a.out, a.everything))
        except TimeoutError:
            index.append({"map": m, "sec": s, "error": "timeout"})
        signal.alarm(0)
        json.dump(index, open(os.path.join(a.out, "index.json"), "w"), ensure_ascii=False, indent=1)
        print("done", m, s, flush=True)


if __name__ == "__main__":
    main()
