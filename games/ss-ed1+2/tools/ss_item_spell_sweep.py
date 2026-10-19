#!/usr/bin/env python3
"""ED2 **도구·주문 일괄** — 전투(그룹 1, 약한 몬스터)에서 아군이 도구 전부·주문 전부를 한 번씩 써서 나오는 메시지를 캡처한다
(헤드리스 새턴 하네스 `ss_headless.py` · 조우 강제는 `ss_battle_sweep.py` 와 같다).

    .venv/bin/python tools/ss_item_spell_sweep.py --cue <이미지.cue> --items 1-119 --spells 1-33 --out <폴더>

## RAM (2026-10-19 실측, 전투 중 · 한 칸씩 쓰고 메뉴로 확인)
- 소지품 = **바이트 배열 `0x0609E1E0`** (아이템 번호 1바이트씩, 0 = 빈 칸, 24B 칸). 「사용」 목록이 이걸 그대로 보여 준다.
- 주문 = 파티 레코드(`0x0609E210 + 108×인덱스`, 넷 복사 `PARTY_COPIES`) **`+0x31` 부터 (주문 번호, 0x0F) 쌍**, 빈 칸은 `FF 00`.
  주문 번호 1~33, 이름표는 `0x0609E838 + 36×(번호-1)` 의 `+8`(16B). 전투 목록엔 **전투용 주문만** 뜬다(필드용은 안 뜬다).
- MP 로 보이는 칸 `+0x0C`·`+0x10`(레코드 앞쪽) 을 크게 채운다. 한 번에 한 항목만 목록 맨 위에 두고 쓴다 → 커서 이동이 필요 없다.
- 메뉴: 3×3(공격 주문 방어 / 사용 무기 자동 / 강함 · 도망). 🔴 **버튼은 2프레임만 눌러야 한 칸 간다**(4프레임이면 두 칸).
🔴 스테이트·RAM 쓰기는 조작용이다 — 문안은 이 캡처의 **화면**으로만 판정한다(CLAUDE.md).
"""

import argparse
import hashlib
import json
import os
import struct
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ss_battle_sweep as S
import ss_headless as H
import ss_scene_sweep as X

INV = 0x0609E1E0
INV_LEN = 24
SPELL_TAB, SPELL_STRIDE = 0x0609E838, 36
ITEM_TAB, ITEM_STRIDE = 0x0609F870, 32
LIST_BOX = (15, 135, 95, 195)  # y0 y1 x0 x1 — 목록 창(위쪽 오른쪽)


def decode(raw, inv):
    raw = raw.split(b"\x00")[0]
    txt, i = "", 0
    while i < len(raw):
        two = raw[i : i + 2]
        if len(two) == 2 and two in inv:
            txt += inv[two]
            i += 2
            continue
        try:
            txt += two.decode("cp932")
            i += 2
        except UnicodeDecodeError:
            txt += "?"
            i += 1
    return txt.replace("?", " ").strip()


def white(frame, box):
    y0, y1, x0, x1 = box
    c = frame[y0:y1, x0:x1].astype(int)
    return int(((c[:, :, 0] > 200) & (c[:, :, 1] > 200) & (c[:, :, 2] > 200)).sum())


def to_menu(h, limit=3000):
    n = 0
    while not S.is_menu(h.frame) and n < limit:
        for pc in S.PARTY_COPIES:
            h.poke(pc + 4, h.peek(pc + 8, 4))
        pin_monsters(h)
        h.run(3)
        n += 3
    h.run(20)
    return S.is_menu(h.frame)


def pin_monsters(h):
    for i in range(4):
        a = S.MON + S.STRIDE_MON * i + 0x1C
        if S.be32(h.peek(a, 4)):
            h.poke(a, struct.pack(">I", 0x7FFF))


def set_party(h, spell=None, item=None, half_hp=False):
    for pc in S.PARTY_COPIES:
        h.poke(pc + 0xC, struct.pack(">I", 999))
        h.poke(pc + 0x10, struct.pack(">I", 999))
        pairs = bytes([spell, 0x0F]) if spell else b"\xff\x00"
        h.poke(pc + 0x31, pairs + b"\xff\x00" * 6)
        if half_hp:
            mx = S.be32(h.peek(pc + 8, 4))
            h.poke(pc + 4, struct.pack(">I", mx // 2))
        else:
            h.poke(pc + 4, h.peek(pc + 8, 4))
    h.poke(INV, bytes([item or 0]) + bytes(INV_LEN - 1))


def cast(h, kind, ident, gdir, half_hp=True):
    """메뉴 첫 칸을 골라 쓰고 다음 메뉴가 뜰 때까지의 새 메시지를 캡처한다. 반환 {list, caps}."""
    os.makedirs(gdir, exist_ok=True)
    if not to_menu(h):
        return {"status": "메뉴 안 뜸"}
    set_party(h, spell=ident if kind == "spell" else None, item=ident if kind == "item" else None)
    h.run(3)
    for b in ("up", "up", "left", "left"):
        h.press(b, 2, 8)
    h.press("right" if kind == "spell" else "down", 2, 12)
    h.press("c", 3, 40)
    h.run(30)
    listed = white(h.frame, LIST_BOX) > 40
    Image.fromarray(h.frame).save(os.path.join(gdir, "list.png"))
    set_party(h, spell=ident if kind == "spell" else None, item=ident if kind == "item" else None,
              half_hp=half_hp)  # fmt: skip
    seen, caps, t, calm = set(), 0, 0, 0
    if listed:
        h.press("c", 3, 20)
    while t < 1500:
        pin_monsters(h)
        if t > 500 or not half_hp:
            for pc in S.PARTY_COPIES:
                h.poke(pc + 4, h.peek(pc + 8, 4))
        h.run(3)
        t += 3
        fr = h.frame
        if t > 90 and S.is_menu(fr):
            calm += 1
            if calm > 4:
                break
            continue
        calm = 0
        if t % 45 == 0:
            h.press("c", 2, 0)
        if t % 9 == 0:
            crop = S.msg_crop(fr)
            if S.has_text(crop):
                key = hashlib.md5(crop.tobytes()).hexdigest()
                if key not in seen:
                    seen.add(key)
                    caps += 1
                    Image.fromarray(fr).save(os.path.join(gdir, f"m{caps:02d}.png"))
    return {"status": "ok", "listed": listed, "captures": caps, "frames": t}


def field_cast(h, nav, kind, ident, gdir):
    """**필드 시스템 메뉴**(c → 주문/사용) 로 쓴다 — 필드용 문안(회복·워프 등). 번호마다 필드 상태에서 새로 시작한다."""
    os.makedirs(gdir, exist_ok=True)
    h.load(nav)
    h.run(5)
    set_party(h, spell=ident if kind == "spell" else None, item=ident if kind == "item" else None,
              half_hp=True)  # fmt: skip
    h.poke(0x0609ECF0, bytes([ident if kind == "item" else 0]) + bytes(INV_LEN - 1))  # 필드 쪽 소지품 사본
    h.press("start", 3, 40)  # 첫 입력은 배너를 넘긴다 — 이 순서가 실측으로 메뉴를 연다
    h.press("b", 3, 30)
    h.press("c", 3, 40)  # 메뉴가 열린다(기타 부속 창에서)
    h.press("b", 3, 30)  # 부속 창을 닫고 본 목록(주문 사용 장비 버린다 상태 기타)
    for _ in range(8):  # 맨 위(주문)까지 — 25프레임 간격이 아니면 입력이 빠진다(실측), 맨 위에서 멈춘다
        h.press("up", 2, 25)
    if kind == "item":
        h.press("down", 2, 25)
    h.press("c", 3, 40)
    h.run(30)
    Image.fromarray(h.frame).save(os.path.join(gdir, "list.png"))
    seen, caps = set(), 0
    for t in range(0, 900, 3):
        h.run(3)
        if t % 60 == 30:
            h.press("c", 2, 0)
        if t % 9 == 0:
            fr = h.frame
            key = hashlib.md5(fr[100:236, 10:206].tobytes()).hexdigest()
            if key not in seen and t % 18 == 0:
                seen.add(key)
                caps += 1
                Image.fromarray(fr).save(os.path.join(gdir, f"m{caps:02d}.png"))
    return {"status": "ok", "listed": True, "captures": caps, "frames": 900}


def chest_functions(d):
    """씬 파일 안의 **보물상자 시스템 문안 함수**들 → [RAM 주소].

    이 함수들은 `ED2.BIN 0x0602F350`(리더 이름 읽기)을 불러 `sprintf(0x0607B180)` 로 문안을 만든다 — 그 호출 리터럴을 찾아
    거슬러 올라가 함수 머리(`mov.l rN,@-r15` 줄 + `sts.l pr,@-r15`)를 잡는다. (제품 이미지는 한글이라 일본어 문안 검색은 못 쓴다.)
    🔴 씬의 「번호→스크립트」 본 함수가 아니라 **그 안에서 불리는 번호 101~ 처리 함수**라서 `ss_scene_sweep.text_fn` 이 못 찾는다
       (ED2SCN24 는 번호 1 하나만 보인다). `PTR_TEXT` 를 이 함수로 바꿔 부르면 `EVENT_RUN` 이 그 문안을 대화창으로 띄운다.
    """
    out = []
    lit, i = struct.pack(">I", 0x0602F350), 0
    while (k := d.find(lit, i)) >= 0:
        i = k + 1
        o = (k & ~1) - 2
        while o > 0x100 and d[o : o + 2] != b"\x4f\x22":
            o -= 2
        while o >= 2 and d[o - 2] == 0x2F and (d[o - 1] & 0x0F) == 6:
            o -= 2
        if X.SCN_BASE + o not in out:
            out.append(X.SCN_BASE + o)
    return out


def chest_mode(a, h, nav, outdir):
    import common

    mm, fl = X.scene_files(common, a.cue)
    X.configure("ed2")
    h.load(nav)
    h.run(5)
    code, body = X.build_stub()
    X.verify_stub(code, body)
    h.poke(X.HOOK, code)
    for k in range(0, 0x20, 4):
        X.p32(h, X.MB + k, 0)
    h.poke(X.TICK, X.hook_patch())
    h.run(30)
    base = X.snapshot(h)
    os.makedirs(outdir, exist_ok=True)
    done, index = {}, []
    for sc in range(1, 48):
        name = f"/BIN/ED2SCN{sc:02d}.BIN"
        if name not in fl:
            continue
        d = common.read_extent(mm, *fl[name])
        for fn in chest_functions(d):
            X.restore(h, base)
            h.run(1)
            h.poke(X.SCN_BASE, d)
            X.p32(h, X.PTR_TEXT, fn)
            h.run(2)
            bs = X.snapshot(h)
            ids = []
            for i in range(90, 140):
                ok, script = X.read_script(h, bs, fn, i)
                if ok and script and (hashlib.md5(script).hexdigest(), 0) not in done:
                    done[(hashlib.md5(script).hexdigest(), 0)] = (sc, i)
                    ids.append(i)
            print(f"ED2SCN{sc:02d} fn {fn:08x} 새 번호 {ids}", flush=True)
            if not ids:
                continue
            sdir = os.path.join(outdir, f"ED2SCN{sc:02d}")
            os.makedirs(sdir, exist_ok=True)
            for var in ("a", "b"):
                X.restore(h, bs)
                X.inject_args(h, var)
                h.run(1)
                snap = X.snapshot(h)
                for i in ids:
                    shots, why = X.play_id(h, snap, i, sdir, f"id{i:03d}_{var}")
                    index.append(dict(scene=sc, id=i, args=var, shots=[f"ED2SCN{sc:02d}/{x}" for x in shots], status=why))
                    print(json.dumps(index[-1], ensure_ascii=False), flush=True)
    json.dump(index, open(os.path.join(outdir, "index.json"), "w"), ensure_ascii=False, indent=1)


# ── ED1 (2026-10-19) — 전투가 완전 자동이라 **필드 시스템 메뉴**(start → 주문/사용)로만 쓴다. 주소는 정적+peek 실측.
ED1_INV = (0x060BC490, 0x060AFA3D, 0x060B0849)  # 소지품 바이트 배열(ED2 와 같은 꼴 — 아이템 번호 = 이름표 칸 번호) · 라이브 + 파티 사본 둘
ED1_ITEM_TAB = 0x060BE470  # 32B 칸 · 이름 16B · 번호 1~116 (나이프=1). +20 바이트 = 쓸 수 있는 도구(1)
ED1_SPELL_TAB = 0x060B8E50  # 32B 칸 · 이름 16B · 번호 n 의 칸 = n-1. +18 바이트 = 필드에서 쓸 수 있음(1, 아니면 목록에 빨갛게)
ED1_REC = (0x060AF5F0, 0x060B03FC, 0x060B8820, 0x060B8CA0)  # 파티 레코드 사본 넷(세리오스) · 칸 108 · 다음 칸 = 류난
ED1_NAV = "ed1_field"


def ed1_field_cast(h, nav, kind, ident, gdir):
    """ED1 필드 메뉴로 도구/주문 하나를 쓴다. 주문은 세리오스 칸 `+0x31` 쌍 (번호, 1), MP `+0xC`·`+0x10` 를 채운다."""
    os.makedirs(gdir, exist_ok=True)
    h.load(nav)
    h.run(5)
    for base in ED1_REC:
        for m in range(2):
            r = base + 108 * m
            h.poke(r + 0xC, struct.pack(">I", 99))
            h.poke(r + 0x10, struct.pack(">I", 99))
            h.poke(r + 4, struct.pack(">I", S.be32(h.peek(r + 8, 4)) // 2))
            if kind == "spell":
                h.poke(r + 0x31, bytes([ident, 1]) + b"\xff\x00" * 6)
    for a in ED1_INV:
        h.poke(a, bytes([ident if kind == "item" else 0]) + bytes(23))
    h.press("start", 3, 40)
    h.press("b", 3, 30)
    for _ in range(8):
        h.press("up", 2, 25)
    if kind == "item":
        h.press("down", 2, 25)
    h.press("c", 3, 40)
    h.run(30)
    Image.fromarray(h.frame).save(os.path.join(gdir, "list.png"))
    seen, caps = set(), 0
    for t in range(0, 900, 3):
        h.run(3)
        if t % 60 == 30:
            h.press("c", 2, 0)
        if t % 18 == 0:
            fr = h.frame
            key = hashlib.md5(fr[100:236, 10:206].tobytes()).hexdigest()
            if key not in seen:
                seen.add(key)
                caps += 1
                Image.fromarray(fr).save(os.path.join(gdir, f"m{caps:02d}.png"))
    return {"status": "ok", "listed": True, "captures": caps, "frames": 900}


def ed1_main(a):
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, a.cue, a.out, bkr=a.bkr)
    nav = os.path.join(H.CACHE, "beetle-saturn", f"{ED1_NAV}_{S.image_key(a.cue)}.state")
    if not os.path.exists(nav):
        S.GAME = S.GAMES["ed1"]
        S.ed1_boot_to_field(h)
        h.save(nav)
    inv = S.inverse_map()
    h.load(nav)
    h.run(5)
    item_names = {i: decode(h.peek(ED1_ITEM_TAB + 32 * i, 16), inv) for i in range(1, 117)}
    item_use = {i: h.peek(ED1_ITEM_TAB + 32 * i + 20, 1)[0] == 1 for i in range(1, 117)}
    spell_names = {i: decode(h.peek(ED1_SPELL_TAB + 32 * (i - 1), 16), inv) for i in range(1, 31)}
    spell_field = {i: h.peek(ED1_SPELL_TAB + 32 * (i - 1) + 18, 1)[0] == 1 for i in range(1, 31)}
    idx_path = os.path.join(a.out, "index.json")
    index = json.load(open(idx_path)) if os.path.exists(idx_path) else {}
    jobs = [("item", i) for i in parse(a.items) if item_use.get(i)] + [("spell", i) for i in parse(a.spells)]
    for kind, ident in jobs:
        key = f"{kind}{ident:03d}"
        if index.get(key, {}).get("status") == "ok":
            continue
        name = item_names[ident] if kind == "item" else spell_names[ident]
        gdir = os.path.join(a.out, f"{key}_{name.replace(' ', '_')}")
        r = ed1_field_cast(h, nav, kind, ident, gdir)
        r.update(kind=kind, id=ident, name=name, dir=os.path.basename(gdir))
        if kind == "spell":
            r["field_usable"] = spell_field[ident]
        index[key] = r
        json.dump(index, open(idx_path, "w"), ensure_ascii=False, indent=1)
        print(json.dumps(r, ensure_ascii=False), flush=True)


def parse(s):
    out = []
    for part in s.split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out += range(int(a), int(b) + 1)
        else:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cue", default="/tmp/claude-0/s/img2/The_Legend_of_Heroes_I&II.cue")
    ap.add_argument("--items", default="")
    ap.add_argument("--spells", default="")
    ap.add_argument("--game", choices=("ed2", "ed1"), default="ed2")
    ap.add_argument("--field", action="store_true", help="필드 시스템 메뉴로 쓴다(전투 대신)")
    ap.add_argument("--chest", action="store_true", help="보물상자 시스템 문안(대사 보기 번호 호출 — 받침 있는/없는 이름 변형 a·b)")
    ap.add_argument("--chest-ids", type=int, default=4, help="문안 함수 하나당 찍을 번호 수")
    ap.add_argument("--group", type=int, default=1)
    ap.add_argument("--per-battle", type=int, default=6, help="전투 하나당 항목 수(새로 띄운다)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bkr", default=S.DEFAULT_BKR)
    a = ap.parse_args()
    if a.game == "ed1":
        return ed1_main(a)
    S.GAME = S.GAMES["ed2"]
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, a.cue, a.out, bkr=a.bkr)
    nav = os.path.join(H.CACHE, "beetle-saturn", f"ed2_field_{S.image_key(a.cue)}.state")
    if not os.path.exists(nav):
        S.boot_to_field(h)
        h.save(nav)
    if a.chest:
        chest_mode(a, h, nav, os.path.join(a.out, "chest"))
        return
    inv = S.inverse_map()
    idx_path = os.path.join(a.out, "index.json")
    index = json.load(open(idx_path)) if os.path.exists(idx_path) else {}
    jobs = [("item", i) for i in parse(a.items)] + [("spell", i) for i in parse(a.spells)]
    n_in_battle = a.per_battle
    names = {}
    if a.field:  # 이름표는 전투 RAM 에서만 읽힌다 — 한 번 띄워 다 읽고 필드 작업을 한다
        assert S.start_battle(h, nav, a.group)
        for i in range(1, 120):
            names[("item", i)] = decode(h.peek(ITEM_TAB + ITEM_STRIDE * i, 16), inv)
        for i in range(1, 34):
            names[("spell", i)] = decode(h.peek(SPELL_TAB + SPELL_STRIDE * (i - 1) + 8, 16), inv)
    for kind, ident in jobs:
        key = f"{kind}{ident:03d}" + ("f" if a.field else "")
        if index.get(key, {}).get("status") == "ok":
            continue
        if not a.field and n_in_battle >= a.per_battle:
            if not S.start_battle(h, nav, a.group):
                print("조우 안 걸림", flush=True)
                break
            n_in_battle = 0
        if a.field:
            name = names[(kind, ident)]
        elif kind == "item":
            name = decode(h.peek(ITEM_TAB + ITEM_STRIDE * ident, 16), inv)
        else:
            name = decode(h.peek(SPELL_TAB + SPELL_STRIDE * (ident - 1) + 8, 16), inv)
        gdir = os.path.join(a.out, f"{key}_{name.replace(' ', '_')}")
        if a.field:
            gdir += "_field"
            r = field_cast(h, nav, kind, ident, gdir)
        else:
            r = cast(h, kind, ident, gdir)
        n_in_battle += 1
        if r.get("status") != "ok":  # 전투가 꼬였다 — 새로 띄운다
            n_in_battle = a.per_battle
        r.update(kind=kind, id=ident, name=name, dir=os.path.basename(gdir))
        index[key] = r
        json.dump(index, open(idx_path, "w"), ensure_ascii=False, indent=1)
        print(json.dumps(r, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
