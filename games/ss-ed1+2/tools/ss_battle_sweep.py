#!/usr/bin/env python3
"""ED2 **전 몬스터 전투 일괄** — 조우 그룹 번호를 지정해 전투를 띄우고, 파티를 방어로 묶어 둔 채 몬스터가 쓰는
메시지를 새 것만 캡처한다(헤드리스 새턴 하네스 `ss_headless.py`).

    python3 tools/ss_battle_sweep.py --groups 62,93,99 --turns 20 --out <폴더>
    python3 tools/ss_battle_sweep.py --groups 1-99 --out <폴더>   # 전수

## 왜 이렇게 하나 (2026-10-18 실측)
- 조우 진입 함수(`ED2.BIN 0x06037F44`)만 바꾸면 **같은 조우의 몬스터 그림 로더(`0x06060A4C`)가 원래 그룹을 다시 읽어**
  슬롯 2 그림 번호가 255 로 남고(`M255.PAL` 파일 없음 → 널 호출) 검은 화면에서 선다. 원본 JP 도 같다(우리 패치 탓 아님).
  ⇒ 조우 함수(`0x0602F118`) 안의 **그룹을 읽는 두 자리**(`mov.b @r9,r4` = `6490`, 0x0602F14E · 0x0602F17C)를
  `mov #NN,r4`(`E4NN`) 로 RAM 에 쓰면 다음 조우가 그룹 NN 이다. 오버레이(ED2MON01~10)는 자연 경로가 올린다.
- 파티는 **방어만 고르고**(몬스터를 안 죽인다) HP 를 매 프레임 채운다(`0x0609E690` 파티 표, 108B 칸, +4 HP ← +8 최대).
- 몬스터 행동 난수는 매 턴 시드를 바꿔 다양하게 뽑는다(`[0x06094FC4]+48` 의 LCG 상태).
🔴 스테이트·RAM 쓰기는 **내비게이션·조작용**이다 — 문안은 이 캡처의 **화면**으로만 판정한다(CLAUDE.md).
⚠ 필드 탐색 상태(`ed2_field.state`)는 이미지마다 다르다 — 빌드를 갈면 다시 만든다(이름에 이미지 지문이 든다).
"""

import argparse
import hashlib
import json
import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ss_headless as H

DEFAULT_BKR = "/root/.local/share/emucap/mednafen/47802/sav/The_Legend_of_Heroes_I&II.bkr"
# 아트라스 레코드(Lv<<8 · HP · HPmax)가 **넷 복사**로 산다 — 전투는 0x0609E690 이 라이브지만 넷 다 쓴다(실측 10-18)
PARTY_COPIES = (0x06094FD0, 0x06095E74, 0x0609E210, 0x0609E690)
PARTY = 0x0609E690
MON, STRIDE_MON = 0x0609F560, 104
RNG_PTR = 0x06094FC4
MSG_BOX = (148, 230, 15, 205)  # y0 y1 x0 x1 — 아래 메시지 창
MENU_ROWS = ((168, 182), (186, 200), (204, 218))  # 명령 3줄


def be32(b):
    return struct.unpack(">I", b)[0]


def image_key(cue):
    st = os.stat(cue.replace(".cue", ".bin"))
    return hashlib.sha1(f"{st.st_size}:{int(st.st_mtime)}".encode()).hexdigest()[:10]


def boot_to_field(h):
    """타이틀 → 둘째 게임 → 이어하기 → 2번(Lv90 서장 평원). 입력 열은 emucap 으로 실측한 것."""
    h.run(2500)
    for names, hold, after in (
        ("start", 6, 120), ("right", 5, 20), ("c", 5, 300),
    ):  # fmt: skip
        h.press(names, hold, after)
    h.run(1500)
    h.press("start", 6, 200)
    h.run(1600)
    for names, hold, after in (
        ("right", 5, 20), ("c", 5, 120), ("c", 5, 90), ("down", 5, 15), ("c", 5, 60), ("c", 5, 200),
    ):  # fmt: skip
        h.press(names, hold, after)


def is_menu(frame):
    """명령 창(공격/주문/방어 …) 인가 — 세 줄 모두에 흰 글자가 있다."""
    sub = frame[:, 15:200].astype(int)
    white = (sub[:, :, 0] > 200) & (sub[:, :, 1] > 200) & (sub[:, :, 2] > 200)
    return all(white[a:b].sum() > 25 for a, b in MENU_ROWS)


def msg_crop(frame):
    y0, y1, x0, x1 = MSG_BOX
    return frame[y0:y1, x0:x1]


def has_text(crop):
    w = (crop[:, :, 0] > 200) & (crop[:, :, 1] > 200) & (crop[:, :, 2] > 200)
    return w.sum() > 15


def names_in_battle(h, inv):
    out = []
    for k in range(4):
        raw = h.peek(MON + STRIDE_MON * k + 1, 24)
        raw = raw.split(b"\x00")[0]
        if not raw:
            continue
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
                txt += raw[i : i + 1].decode("cp932", "replace")
                i += 1
        out.append(txt)
    return out


def inverse_map():
    import check_name_tables as C

    return C._inv_map()


def start_battle(h, nav_state, g):
    h.load(nav_state)
    h.run(5)
    for a in (0x0602F14E, 0x0602F17C):
        h.poke(a, bytes([0xE4, g]))
    n = 0
    while be32(h.peek(MON + 0x1C, 4)) == 0 and n < 80:
        h.held = {H.BTN["right" if n % 2 == 0 else "left"]}
        h.run(40)
        h.held = set()
        h.run(5)
        n += 1
    return be32(h.peek(MON + 0x1C, 4)) != 0


def run_group(h, nav_state, g, turns, outdir, inv, attempts=6):
    """한 그룹 — 파티가 쓰러지면(독 등) 같은 그룹을 **다른 시드로 다시** 띄워 턴을 채운다(캡처는 이어 쌓는다)."""
    gdir = os.path.join(outdir, f"g{g:02d}")
    seen, caps, t, names, tries, frames = set(), 0, 0, None, 0, 0
    while t < turns and tries < attempts:
        if not start_battle(h, nav_state, g):
            return {"group": g, "status": "조우 안 걸림"}
        os.makedirs(gdir, exist_ok=True)
        tries += 1
        nav_turn_done = False
        obj = be32(h.peek(RNG_PTR, 4))
        local = 0
        while t < turns and local < 6000:
            for pc_ in PARTY_COPIES:
                h.poke(pc_ + 4, h.peek(pc_ + 8, 4))
            h.run(3)
            local += 3
            frames += 3
            fr = h.frame
            if h.peek(PARTY + 0x46, 1) == b"\x01":  # 기절 — 이 시도는 여기까지
                break
            if is_menu(fr):
                if names is None:
                    names = names_in_battle(h, inv)
                    Image.fromarray(fr).save(os.path.join(gdir, "menu.png"))
                if not nav_turn_done:
                    h.poke(obj + 48, struct.pack(">I", 0x1234 + t * 7919 + g * 104729 + tries * 31337))
                    for b in ("up", "up", "left", "left", "right", "right", "c"):
                        h.press(b, 4, 8)
                    t += 1
                    nav_turn_done = True
                    h.run(20)
            else:
                nav_turn_done = False
                if local % 9 == 0:
                    crop = msg_crop(fr)
                    if has_text(crop):
                        key = hashlib.md5(crop.tobytes()).hexdigest()
                        if key not in seen:
                            seen.add(key)
                            caps += 1
                            Image.fromarray(fr).save(os.path.join(gdir, f"m{caps:02d}.png"))
    return {"group": g, "status": "ok", "monsters": names or [], "turns": t, "tries": tries, "captures": caps}


def fast_win(h, frames=3600):
    """**전투 스킵** — 몬스터 HP 를 1 로 묶고 공격만 눌러 곧장 이기게 한다(보상·드롭 문구까지 정상으로 나온다).

    🔴 함수째 건너뛰면 안 된다 — 조우 함수(`0x0602F118`)를 `rts` 로 막거나 호출(`jsr`)을 `nop` 로 바꾸면 전투 뒤 처리가
       빈 레코드로 돌아 **파티가 Lv0/HP0 으로 깨진다**(실측 10-18). 전투는 하되 한 턴에 끝내는 쪽이 안전하다.
    반환: 전투가 끝났나(몬스터 HP 전부 0).
    """
    for _ in range(frames // 3):
        alive = False
        for i in range(4):
            a = MON + STRIDE_MON * i + 0x1C
            if be32(h.peek(a, 4)):
                alive = True
                h.poke(a, struct.pack(">I", 1))
        if not alive:
            return True
        h.run(3)
        if is_menu(h.frame):
            for b in ("up", "up", "left", "left", "c", "c", "c"):
                h.press(b, 4, 8)
    return False


def contact_sheet(gdir, cols=3):
    """캡처를 한 장으로 — 메시지 창만 잘라 3열로 깐다(검수는 이 한 장을 본다)."""
    fs = sorted(f for f in os.listdir(gdir) if f.startswith("m") and f.endswith(".png"))
    if not fs:
        return None
    y0, y1, x0, x1 = MSG_BOX
    w, hh = x1 - x0, y1 - y0
    sheet = Image.new("RGB", (cols * (w + 4), ((len(fs) + cols - 1) // cols) * (hh + 4)))
    for i, f in enumerate(fs):
        im = Image.open(os.path.join(gdir, f)).crop((x0, y0, x1, y1))
        sheet.paste(im, ((i % cols) * (w + 4), (i // cols) * (hh + 4)))
    path = os.path.join(gdir, "sheet.png")
    sheet.save(path)
    return path


def parse_groups(s):
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += range(int(a), int(b) + 1)
        else:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", default="62")
    ap.add_argument("--turns", type=int, default=20)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=None)
    ap.add_argument("--bkr", default=DEFAULT_BKR)
    ap.add_argument("--nav-only", action="store_true", help="필드 상태만 만들고 끝낸다(병렬 실행 전)")
    a = ap.parse_args()
    import common

    cue = a.cue or os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue")
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, cue, a.out, bkr=a.bkr)
    nav = os.path.join(H.CACHE, "beetle-saturn", f"ed2_field_{image_key(cue)}.state")
    if not os.path.exists(nav):
        boot_to_field(h)
        h.save(nav)
    if a.nav_only:
        return
    inv = inverse_map()
    rows = []
    for g in parse_groups(a.groups):
        r = run_group(h, nav, g, a.turns, a.out, inv)
        rows.append(r)
        if r.get("status") == "ok":
            contact_sheet(os.path.join(a.out, f"g{g:02d}"))
        print(json.dumps(r, ensure_ascii=False), flush=True)
    tag = a.groups.replace(",", "_")
    with open(os.path.join(a.out, f"table_{tag}.json"), "w") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
