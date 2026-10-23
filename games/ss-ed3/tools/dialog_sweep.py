#!/usr/bin/env python3
"""전 씬 대사 보기 — 맵 블록을 **실제 대사 창**으로 띄워 찍는다(헤드리스 새턴, 롬·세이브 불변).

    sh scripts/heavy.sh timeout 1200 python3 games/ss-ed3/tools/dialog_sweep.py \\
        <이미지.cue> <기준상태> <출력폴더> [--maps MAP001,MAP003 | --all] [--limit N] [--resume]

방법(10-19 실측): 필드가 한가할 때(스크립트 PC 전역 `0x0609408C` = 0) 그 값에 스크립트 주소를 쓰면 엔진이 그 스크립트를 돈다.
  ① **맵 파일째 갈아 끼운다** — 구운 이미지의 `MAPnnn.BIN` 바이트를 `0x00200000` 에 통째로 쓴다(맵 이동 없이 그 맵의 이름표 표·대사를 쓴다.
     배경 그림은 옛 맵 그대로다 — 글만 본다).
  ② 맵 파일 안의 0 런에 **짧은 스크립트**(`FF 02 00 00` 창 설정 · `FF 00` 창 열기 · 블록 머리+본문+종결)를 쓰고 PC 를 거기에 둔다.
  ③ 창이 뜨면 창 영역만 잘라 저장하고 `c` 로 쪽을 넘기며 닫힐 때까지 반복한다.
🔴 상태·RAM 쓰기는 **내비게이션·조작용**이다 — 문안은 이 화면 캡처로만 판정한다(CLAUDE.md).
산출: <출력폴더>/<MAP>/<키>_p<쪽>.png · index.jsonl(맵·키·쪽 수·기대 쪽 수·창 떴나) · 맵마다 시트(sheet_<MAP>_NN.png).
"""

import json
import os
import re
import struct
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import check_build_discs as B
import common as C
import mapfile as M
import ss_headless as H

PC = 0x0609408C
LWRAM = 0x00200000
SETUP = bytes.fromhex("ff020000")  # 창 설정(아래 창) — 맵에서 가장 흔한 값
OPEN = bytes.fromhex("ff00")
TAIL = bytes.fromhex("0009ffffffff")
WIN_BOTTOM = (150, 240)  # 창이 놓이는 세로 구간(원 크기 240행 기준)
WIN_TOP = (0, 90)
MAX_PAGES = 24


def patches(b, blk):
    """블록 제자리에서 앞·뒤만 고치는 쓰기 목록 `(맵 오프셋, 바이트)` 와 진입 오프셋.

    🔴 맵 안 0 런에 짧은 스크립트를 따로 쓰던 첫 판은 MAP006·007 에서 PC 가 안 돌았다(10-19 실측 — 스크립트 구역 밖이면 엔진이 무시하는 듯).
    그래서 **블록 바로 앞 6B 에 창 설정(+창 열기)** 을, **종결 바이트 뒤에 끝맺음**을 덮어쓴다 — 상태를 블록마다 되돌리니 이웃을 망가뜨려도 된다."""
    o = blk["off"]
    e = o + len(blk["body"])
    if blk["head"] == "ff00":  # 머리가 곧 `FF 00` — 앞엔 창 설정만
        return [(o - 2 - len(SETUP), SETUP), (e + 1, TAIL)], o - 2 - len(SETUP)
    return [(o - 2 - len(SETUP) - len(OPEN), SETUP + OPEN), (e + 1, TAIL)], o - 2 - len(SETUP) - len(OPEN)


def mini(b, blk):
    """(옛 방식 — 시험용) 블록 하나를 띄우는 짧은 스크립트 바이트."""
    o = blk["off"]
    e = o + len(blk["body"])
    seg = b[o - 2 : e + 1]  # 머리 2B + 본문 + 종결 1B
    pre = SETUP if blk["head"] == "ff00" else SETUP + OPEN
    return pre + seg + TAIL


def zero_run(b, need):
    """맵 파일 안 0 런(≥ need B) 시작 오프셋 — 짧은 스크립트를 쓸 자리. 없으면 None."""
    for m in re.finditer(b"\x00{%d,}" % (need + 8), b):
        return m.start() + 4
    return None


def region_diff(a, b):
    return int(np.abs(a.astype(np.int16) - b.astype(np.int16)).sum(axis=2).astype(bool).sum())


def stable(h, steps=6, cap=200):
    """창 글자가 다 그려질 때까지 — 조금씩 돌려 영역이 `steps` 번 연속 같으면 끝."""
    prev, same, n = None, 0, 0
    while n < cap:
        h.run(4)
        n += 4
        cur = h.frame[150:240].copy()
        if prev is not None and region_diff(prev, cur) == 0:
            same += 1
            if same >= steps:
                return True
        else:
            same = 0
        prev = cur
    return False


def sheet(outdir, stem, items, idx):
    """한 시트 = 크롭 여러 장을 세로로 쌓고 키 라벨을 단다."""
    ims = [(k, Image.open(os.path.join(outdir, stem, f"{k}.png")).convert("RGB")) for k in items]
    w = max(i.size[0] for _, i in ims)
    hh = sum(i.size[1] + 12 for _, i in ims)
    s = Image.new("RGB", (w, hh), (30, 30, 30))
    d = ImageDraw.Draw(s)
    y = 0
    for k, im in ims:
        d.text((2, y), k, fill=(255, 220, 80))
        s.paste(im, (0, y + 12))
        y += im.size[1] + 12
    s.save(os.path.join(outdir, f"sheet_{stem}_{idx:02d}.png"))


def ink(frame_crop):
    """창 안쪽 **글자 잉크** 픽셀 수 — 밝은(R·G·B 모두 ≥ 170) 점. 테두리·얼굴 바깥 모서리를 피해 가운데 영역만 본다. 6 미만이면 「글자 없는 쪽」."""
    a = np.asarray(frame_crop)
    h, w = a.shape[:2]
    inner = a[int(h * 0.18) : int(h * 0.9), int(w * 0.2) : int(w * 0.88)]
    return int(((inner >= 170).all(axis=2)).sum())


def var_start(body):
    """본문이 런타임 주입 토큰(`01 <번호>`)으로 시작하나 — 변수 버퍼가 비면 쪽이 비는 부류(sfc-ed2 10-20)."""
    return len(body) >= 2 and body[0] == M.CTRL_INJECT


GOOD = {}  # 정상 동작이 확인된 맵(MAP001) — 범인 구간을 가를 때 바탕으로 쓴다: {"data": 구운 바이트, "blk": 시험 블록}


def works(h, base, data, blk):
    """`data` 를 맵으로 쓰고 `blk` 를 띄웠을 때 스크립트가 돈다(PC 가 0 으로 돌아온다)."""
    h.restore(base)
    h.run(2)
    h.poke(LWRAM, data)
    h.run(30)
    ws, entry = patches(data, blk)
    for at, b in ws:
        h.poke(LWRAM + at, b)
    h.poke(PC, (LWRAM + entry).to_bytes(4, "big"))
    h.run(30)
    return int.from_bytes(h.peek(PC, 4), "big") == 0


def culprit(h, base, tgt):
    """MAP001 바탕에 `tgt` 의 구간을 바꿔 넣으며 **스크립트가 안 도는 최소 구간** `(a, e)` 를 이분 탐색한다.

    🔴 10-19 실측: 맵마다 「자동으로 도는 이벤트 표」 같은 구간이 있어, 그 맵 바이트를 통째로 넣으면 엔진이 PC 쓰기를 무시한다(MAP006·007 은
    `0x16af0` 둘레 — 4B 포인터 표). 그 구간만 중화하면 대사를 띄울 수 있다."""
    g, gb = GOOD["data"], GOOD["blk"]
    n = max(len(g), len(tgt))
    t = tgt.ljust(n, b"\0")
    o = gb["off"]
    keep = (o - 12, o + len(gb["body"]) + 8)

    def hybrid(a, b):
        x = bytearray(g.ljust(n, b"\0"))
        x[a:b] = t[a:b]
        x[keep[0] : keep[1]] = g[keep[0] : keep[1]]
        return bytes(x)

    lo = 0x400
    if works(h, base, hybrid(lo, n), gb):
        return None
    a, b = lo, n
    while b - a > 0x100:
        m = (a + b) // 2
        if works(h, base, hybrid(lo, m), gb):
            a = m
        else:
            b = m
    e = b
    a, b = lo, e
    while b - a > 0x40:
        m = (a + b) // 2
        if works(h, base, hybrid(m, e), gb):
            b = m
        else:
            a = m
    return a, e


def prepare(h, base, got, blocks):
    """맵 바이트를 **띄울 수 있는 꼴**로 — 그대로 되면 그대로, 아니면 범인 구간을 정상 맵(MAP001)의 같은 구간 값으로 바꾼다. `(바이트, 메모)`.

    🔴 이분 탐색이 가리키는 구간은 그 맵의 결함이 아니라 **엔진이 기준 상태(MAP001)에서 런타임 구조로 쓰고 있는 자리**로 보인다(MAP006·007 이 같은 구간
    `0x16aa5~0x16aff` 를 가리켰다). 거기만 기준 값으로 두면 나머지는 그 맵 것을 써도 된다."""
    probe = next((b for b in blocks if b["head"][:2] == "02"), None)
    if probe is None:
        return got, "02 머리 블록 없음 — 시험 못 함"
    if works(h, base, got, probe):
        return got, ""
    cur, notes = bytearray(got), []
    for _ in range(4):
        r = culprit(h, base, bytes(cur))
        if r is None:
            break
        a, e = r
        g = GOOD["data"].ljust(len(cur), b"\0")
        cur[a:e] = g[a:e]  # 🔴 0 이 아니라 **정상 맵(MAP001)의 같은 구간**을 쓴다 — 0 으로 덮으면 여전히 안 돈다(첫 판 실패, 10-19)
        notes.append(f"{a:#x}~{e:#x} 를 MAP001 값으로")
        if works(h, base, bytes(cur), probe):
            return bytes(cur), " · ".join(notes)
    return got, "중화 실패 — " + " · ".join(notes)


NAMES = int(os.environ.get("SWEEP_NAMES", "0x400"), 0)  # 이름표 표를 옮길 길이(이름 칸 32B × 32 — 머리 인자가 32 이상인 블록은 기준 맵 값을 읽는다)
KEYS = os.environ.get("SWEEP_KEYS")  # "224-233" — 그 번호 구간만 찍는다(시험용)


def run_map(h, base, img, files, orig, stem, outdir, limit, idxf, deadline):
    """🔴 **이식 방식**(10-19, 기본): 기준 맵(MAP001)을 그대로 두고 **이름표 표만** 그 맵 것으로 갈아 끼운 뒤, 맵 안 0 런에 블록을 이식해 띄운다.

    맵 파일째 갈아 끼우던 첫 판은 MAP006·007 에서 안 됐다 — 엔진이 맵 영역 안 여러 곳(`0x16aa5` `0x16bca` `0x1735f` …)을 런타임 구조로 쓰고 있어
    그 맵의 바이트가 덮으면 스크립트가 안 돈다(구간 중화로도 못 풀었다). 이식 방식은 맵 영역을 안 건드려 **모든 맵에 같다**."""
    name = f"/MAP/{stem}.BIN"
    lba, size = files[name]
    got = B.read_extent(img, lba, size)
    src = orig[name]
    blocks = M.blocks(src)
    g = GOOD["data"]
    h_t = struct.unpack(">37I", got[0x10 : 0x10 + 148])
    h_g = struct.unpack(">37I", g[0x10 : 0x10 + 148])
    zr = zero_run(g, 200 + max((len(b["body"]) for b in blocks), default=0))
    if zr is None:
        idxf.write(json.dumps({"map": stem, "err": "기준 맵에 0 런이 모자란다"}, ensure_ascii=False) + "\n")
        return 0
    os.makedirs(os.path.join(outdir, stem), exist_ok=True)
    h.restore(base)
    h.run(2)
    nt, ng = h_t[2] - LWRAM, h_g[2] - LWRAM  # 이름표 표 위치(헤더 3번째 포인터)
    h.poke(LWRAM + ng, got[nt : nt + NAMES])
    snap = h.snap()
    h.run(1)
    base_win = h.frame.copy()
    shots, done = [], 0
    for i, blk in enumerate(blocks[:limit]):
        if time.time() > deadline:
            return done
        if KEYS and not (int(KEYS.split("-")[0]) <= i <= int(KEYS.split("-")[-1])):
            continue
        key = f"{i:04d}"
        h.restore(snap)
        o = blk["off"]
        e = o + len(blk["body"])
        pre = SETUP if blk["head"] == "ff00" else SETUP + OPEN
        h.poke(LWRAM + zr, pre + got[o - 2 : e + 1] + TAIL)
        h.poke(PC, (LWRAM + zr).to_bytes(4, "big"))
        pages, shown, inks = 0, False, []
        for _ in range(MAX_PAGES):
            if not stable(h):
                break
            if region_diff(base_win[150:240], h.frame[150:240]) < 300 and region_diff(base_win[0:90], h.frame[0:90]) < 300:
                break
            shown = True
            pages += 1
            inks.append(ink(h.frame[150:240]))
            crop = Image.fromarray(h.frame[150:240]).convert("P", palette=Image.ADAPTIVE, colors=48)
            crop.save(os.path.join(outdir, stem, f"{key}_p{pages}.png"), optimize=True)
            shots.append(f"{key}_p{pages}")
            h.press("c", 4, 22)
            if int.from_bytes(h.peek(PC, 4), "big") == 0:
                break
        idxf.write(
            json.dumps(
                {"map": stem, "key": i, "head": blk["head"], "pages": pages, "expect": len(M_PAGES(blk)), "shown": shown,
                 "ink": inks, "blank_pages": sum(1 for x in inks if x < 6), "var_start": var_start(blk["body"])}
            )
            + "\n"
        )
        done += 1
    for n in range(0, len(shots), 10):
        sheet(outdir, stem, shots[n : n + 10], n // 10)
    idxf.write(json.dumps({"map": stem, "complete": done == len(blocks[:limit]), "blocks": done}) + "\n")
    return done


def run_map_swap(h, base, img, files, orig, stem, outdir, limit, idxf, deadline):
    """(옛 방식 — 맵 파일째 갈아 끼움. MAP000~010 은 이걸로 찍었다)"""
    name = f"/MAP/{stem}.BIN"
    lba, size = files[name]
    got = B.read_extent(img, lba, size)
    src = orig[name]
    blocks = M.blocks(src)
    os.makedirs(os.path.join(outdir, stem), exist_ok=True)
    got, note = prepare(h, base, got, blocks)
    if note:
        idxf.write(json.dumps({"map": stem, "prep": note}, ensure_ascii=False) + "\n")
    h.restore(base)
    h.run(2)
    h.poke(LWRAM, got)
    snap = h.snap()
    h.run(1)
    base_win = h.frame.copy()
    shots, done = [], 0
    for i, blk in enumerate(blocks[:limit]):
        if time.time() > deadline:
            return done
        key = f"{i:04d}"
        h.restore(snap)
        ws, entry = patches(got, blk)
        for at, data in ws:
            h.poke(LWRAM + at, data)
        h.poke(PC, (LWRAM + entry).to_bytes(4, "big"))
        pages, shown = 0, False
        for _ in range(MAX_PAGES):
            if not stable(h):
                break
            if region_diff(base_win[150:240], h.frame[150:240]) < 300 and region_diff(base_win[0:90], h.frame[0:90]) < 300:
                break  # 창이 없다(안 떴거나 닫혔다)
            shown = True
            pages += 1
            crop = Image.fromarray(h.frame[150:240]).convert("P", palette=Image.ADAPTIVE, colors=48)
            crop.save(os.path.join(outdir, stem, f"{key}_p{pages}.png"), optimize=True)
            shots.append(f"{key}_p{pages}")
            h.press("c", 4, 22)
            if int.from_bytes(h.peek(PC, 4), "big") == 0:
                break  # 마지막 쪽을 넘겼다 — 스크립트가 끝났다(닫히는 빈 화면은 안 찍는다)
        exp = len(M_PAGES(blk))
        idxf.write(json.dumps({"map": stem, "key": i, "head": blk["head"], "pages": pages, "expect": exp, "shown": shown}) + "\n")
        done += 1
    for n in range(0, len(shots), 10):
        sheet(outdir, stem, shots[n : n + 10], n // 10)
    idxf.write(json.dumps({"map": stem, "complete": done == len(blocks[:limit]), "blocks": done}) + "\n")
    return done


STATE_KEYS = ("/SYSTEM/KANJI12.FON", "/SYSTEM/ASCII.FON", "/0.BIN")


def rom_key(img, files):
    """상태 파일이 품고 있는 RAM(글리프 표·글꼴·엔진 코드)의 출처 — 이 롬의 해당 파일 sha1.

    🔴 상태 파일은 롬을 바꿔도 **옛 RAM 을 되살린다**(ps1-ed3 10-20: 새 롬으로 찍었는데 옛 글리프 표라 「줄」이 「앗」으로 나왔다).
    그래서 상태 옆에 이 값을 적어 두고, 다르면 쓰지 않는다."""
    import hashlib

    h = hashlib.sha1()
    for n in STATE_KEYS:
        h.update(n.encode() + b"\0" + B.read_extent(img, *files[n]))
    return h.hexdigest()


def M_PAGES(blk):
    """기대 쪽 수 — 본문 안 `0F`(쪽 넘김) 수 + 1."""
    return [0] * (blk["body"].count(b"\x0f") + 1)


BOOT = [  # 타이틀 → 이어하기 → 슬롯 1(쥬리오 집) → 엄마 곁 필드 — 10-19 실측 입력 열(결정적)
    ("run", 1800), ("press", "start", 6, 200), ("press", "c", 6, 200), ("press", "c", 6, 200),
    ("press", "start", 6, 120), ("press", "c", 6, 120), ("press", "c", 6, 120), ("run", 300),
    ("press", "c", 6, 60), ("press", "up+left", 120, 30), ("run", 200), ("press", "c", 6, 200),
    ("run", 120), ("press", "c", 6, 40),
]  # fmt: skip


def boot(h):
    for s in BOOT:
        if s[0] == "run":
            h.run(s[1])
        else:
            h.press(s[1], s[2], s[3])
    h.run(60)


def main():
    a = sys.argv[1:]
    cue, statep, outdir = a[0], a[1], a[2]
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d  # noqa: E731
    deadline = time.time() + float(opt("--budget", 1100))
    limit = int(opt("--limit", 10**9))
    core = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    bkr = opt("--bkr")
    h = H.Harness(core, cue, outdir, bkr=bkr)
    img = build.out_paths(1)[0]
    files = {n: (l, s) for n, l, s, *_ in build.patched(1)}
    key = rom_key(img, files)
    if statep == "-":  # 상태 파일이 없으면 부팅 열로 만든다 — 만든 롬의 열쇠를 옆에 적는다
        boot(h)
        h.save(os.path.join(outdir, "base.state"))
        with open(os.path.join(outdir, "base.state.rom"), "w") as f:
            f.write(key + "\n")
    else:
        side = statep + ".rom"
        got = open(side).read().strip() if os.path.exists(side) else None
        if got != key and "--force-state" not in a:
            sys.exit(
                f"🔴 상태 파일 {statep} 은 지금 롬의 것이 아니다(옆 .rom: {got or '없음'} · 지금 {key[:12]}…) — "
                "옛 글리프 표·엔진이 되살아난다. `-` 로 부팅 열에서 다시 만든다."
            )
        h.load(statep)
        h.run(2)
    base = h.snap()
    with C.open_disc(1) as d:
        g_src = d.read("/MAP/MAP001.BIN")
    GOOD["data"] = B.read_extent(img, *files["/MAP/MAP001.BIN"])
    GOOD["blk"] = M.blocks(g_src)[33]
    orig = {}
    with C.open_disc(1) as d:
        for n, *_ in d.files():
            ok, stem = C.is_map_file(n)
            if ok:
                orig[n] = d.read(n)
    stems = sorted(os.path.basename(n)[:-4] for n in orig)
    if opt("--maps"):
        stems = opt("--maps").split(",")
    doneset = set()
    ip = os.path.join(outdir, "index.jsonl")
    if "--resume" in a and os.path.exists(ip):
        doneset = {json.loads(x)["map"] for x in open(ip, encoding="utf-8") if '"complete": true' in x}
    with open(ip, "a", encoding="utf-8") as idxf:
        for stem in stems:
            if stem in doneset:
                continue
            n = run_map(h, base, img, files, orig, stem, outdir, limit, idxf, deadline)
            idxf.flush()
            print(stem, n, flush=True)
            if time.time() > deadline:
                break
    fin = {json.loads(x)["map"] for x in open(ip, encoding="utf-8") if '"complete": true' in x}
    if set(stems) <= fin:
        print("ALLDONE", len(fin), flush=True)


if __name__ == "__main__":
    main()
