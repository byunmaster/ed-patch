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

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ss_headless as H

DEFAULT_BKR = "/root/.local/share/emucap/mednafen/47802/sav/The_Legend_of_Heroes_I&II.bkr"
# 아트라스 레코드(Lv<<8 · HP · HPmax)가 **넷 복사**로 산다 — 전투는 0x0609E690 이 라이브지만 넷 다 쓴다(실측 10-18)
PARTY_COPIES = (0x06094FD0, 0x06095E74, 0x0609E210, 0x0609E690)
PARTY = 0x0609E690
MON, STRIDE_MON = 0x0609F560, 104
RNG_PTR = 0x06094FC4

# 게임별 상수 — ED2 는 위 값, ED1 은 `ED.BIN` 조우 함수 `0x0603E45C` (객체 표 0x060B8A20 +15 가 그룹).
# 그룹을 읽는 두 자리는 `6320`(mov.b @r2,r3) → `E3NN`(mov #NN,r3). 값은 정적 분석, 실측은 게임별 주석 참고.
GAMES = {
    "ed2": dict(
        sites=(0x0602F14E, 0x0602F17C),
        orig=b"\x64\x90",
        op=0xE4,  # 6490 → E4NN
        groups="1-99",
        state="ed2_field",
    ),
    "ed1": dict(
        sites=(0x0603E4A8, 0x0603E4FC),
        orig=b"\x63\x20",
        op=0xE3,  # 6320 → E3NN
        groups="1-110",
        state="ed1_battle_field"  # 🔴 씬 하네스(`ss_scene_sweep`)의 `ed1_field_*` 와 **다른 칸** — 같은 이름이면 서로의 상태(슬롯 1 성 vs 슬롯 3 해안)를 읽어 「조우 안 걸림」이 된다(2026-10-19),
    ),
}
GAME = GAMES["ed2"]
MSG_BOX = (148, 230, 15, 205)  # y0 y1 x0 x1 — 아래 메시지 창
MENU_ROWS = ((168, 182), (186, 200), (204, 218))  # 명령 3줄


def be32(b):
    return struct.unpack(">I", b)[0]


def image_key(cue):
    """필드 상태 파일 이름표 — **이미지 내용 해시**다. 세이브스테이트는 옛 롬의 RAM(글리프 표·글·코드)을 되살리므로 롬이 다르면 상태도 달라야 한다.
    (옛 열쇠는 크기:mtime 이라 mtime 을 보존해 복사한 같은 크기의 다른 롬이 옛 상태를 물려받을 수 있었다 — 2026-10-20 ps1-ed3 「줄→앗」 사고 점검.)"""
    h = hashlib.sha1()
    with open(cue.replace(".cue", ".bin"), "rb") as f:
        while b := f.read(1 << 24):
            h.update(b)
    return h.hexdigest()[:10]


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


# 🔴 파티 이름 버퍼 채우기(2026-10-19) — 강제 조우로 띄운 전투에서 전투 문구의 `%s`(대상·행위자가 파티원) 이름이 **빈칸**으로 찍힌다
#    (「…에게 41의 피해」 앞 이름 없음 — 원본 JP 이미지에서도 똑같다 = 하네스 조건). 이름 표 칸 0(ED2 0x0609E1F8 · ED1 0x060B8808)이 비어 있다.
#    그 칸에 대표 이름을 매 틀 써 준다(롬 불변, 화면 판정용). ED1 은 받침 없는/있는 이름을 번갈아 써 두 조사 꼴이 다 나오게 한다.
PARTY_NAME_TAB = {"ed2": (0x0609E1F8, 12, ("아트라스",)), "ed1": (0x060B8808, 12, ("세리오스", "류난"))}
FILL_NAMES = True
# 🔴 표시 이름은 이름 표 칸 0 이 아니라 **파티 슬롯 1**(칸 0 + 0x6C — ED2 0x0609E264 · ED1 0x060B8874 = 세리오스, 슬롯 2 = 류난)에서 읽힌다(2026-10-20 RAM 스캔).
#    칸 0 만 덮으면 `--party-name` 이 안 먹는다(a/b 판이 같은 화면). `--party-name` 이 줄 때만 슬롯 1 도 덮는다.
PARTY_NAME_EXTRA = {}
PARTY_NAME_ADDRS = {"ed2": (0x06095024, 0x06095EC8, 0x0609E264, 0x0609E6E4), "ed1": (0x060B8874, 0x060B8CF4, 0x060B88E0, 0x060B8D60)}  # RAM 스캔(데이터 영역)에서 이름이 있던 자리


def fill_names(h, game, t=0):
    if not FILL_NAMES:
        return
    import josa

    sc = josa.slot_codes()
    addr, lim, names = PARTY_NAME_TAB[game]
    kr = names[(t // 450) % len(names)]
    raw = b"".join(b" " if c == " " else struct.pack(">H", sc[c]) for c in kr)
    assert len(raw) < lim
    h.poke(addr, raw.ljust(lim, b"\x00"))
    for ex in PARTY_NAME_EXTRA.get(game, ()):  # `--party-name` — 실제 표시 이름 칸도 같이 덮는다(이름 + 종단만 — 이웃 필드를 안 건드린다)
        h.poke(ex, raw + b"\x00\x00")


def is_menu(frame):
    """명령 창(공격/주문/방어 …) 인가 — 세 줄 모두에 흰 글자가 있다."""
    sub = frame[:, 15:200].astype(int)
    white = (sub[:, :, 0] > 200) & (sub[:, :, 1] > 200) & (sub[:, :, 2] > 200)
    return all(white[a:b].sum() > 25 for a, b in MENU_ROWS)


def msg_crop(frame):
    y0, y1, x0, x1 = MSG_BOX
    return frame[y0:y1, x0:x1]


def text_mask(crop):
    """글자(흰·노랑)만 남긴 마스크 — ▽ 깜박임·배경 변화에 안 흔들리는 안정 판정용."""
    c = crop.astype(int)
    white = (c[:, :, 0] > 200) & (c[:, :, 1] > 200) & (c[:, :, 2] > 200)
    yel = (c[:, :, 0] > 200) & (c[:, :, 1] > 200) & (c[:, :, 2] < 120)
    return white | yel


def has_text(crop):
    w = (crop[:, :, 0] > 200) & (crop[:, :, 1] > 200) & (crop[:, :, 2] > 200)
    return w.sum() > 15


def names_in_battle(h, inv, skip_empty=False):
    out = []
    mon, stride = GAME.get("mon", (MON, STRIDE_MON))
    for k in range(4):
        if skip_empty and h.peek(mon + stride * k, 1)[0] == 0:
            continue
        raw = h.peek(mon + stride * k + 1, 24)
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


PRE_IDLE = 0  # `--pre-idle N` — 조우를 걸기 전에 N 프레임 더 둔다(게임 난수가 프레임마다 흘러 난수 편성의 다른 변형이 나온다 — ED2 그룹 25 의 빌타라 편성)


def start_battle(h, nav_state, g):
    h.load(nav_state)
    h.run(5 + PRE_IDLE)
    for a in GAME["sites"]:
        assert h.peek(a, 2) in (GAME["orig"], bytes([GAME["op"], h.peek(a + 1, 1)[0]])), hex(a)
        h.poke(a, bytes([GAME["op"], g]))
    n = 0
    while be32(h.peek(MON + 0x1C, 4)) == 0 and n < 80:
        h.held = {H.BTN["right" if n % 2 == 0 else "left"]}
        h.run(40)
        h.held = set()
        h.run(5)
        n += 1
    return be32(h.peek(MON + 0x1C, 4)) != 0


def run_group(h, nav_state, g, turns, outdir, inv, attempts=6, start=None):
    """한 그룹 — 파티가 쓰러지면(독 등) 같은 그룹을 **다른 시드로 다시** 띄워 턴을 채운다(캡처는 이어 쌓는다)."""
    gdir = os.path.join(outdir, f"g{g:02d}")
    seen, caps, t, names, tries, frames = set(), 0, 0, None, 0, 0
    while t < turns and tries < attempts:
        if not (start(h) if start else start_battle(h, nav_state, g)):  # start: 특수 전투(83)는 앞 전투를 이어받아야 돈다 — 진입을 호출자가 정한다
            return {"group": g, "status": "조우 안 걸림"}
        os.makedirs(gdir, exist_ok=True)
        tries += 1
        nav_turn_done = False
        obj = be32(h.peek(RNG_PTR, 4))
        local = 0
        # 🔴 글이 그려지는 도중 프레임을 찍지 않는다(2026-10-19 qa — 「독광석은 ㅇ .」 175곳): 같은 크롭이 3번 연속 폴링(27프레임)
        #    안 바뀌면 다 그려진 것이다. 글이 사라질 때(메뉴·빈 창)는 마지막 프레임을 쓴다.
        pend_key, pend_n, pend_fr = None, 0, None

        def commit(key, fr_):
            nonlocal caps
            if key is not None and key not in seen:
                seen.add(key)
                caps += 1
                Image.fromarray(fr_).save(os.path.join(gdir, f"m{caps:02d}.png"))

        while t < turns and local < 6000:
            for pc_ in PARTY_COPIES:
                h.poke(pc_ + 4, h.peek(pc_ + 8, 4))
            fill_names(h, "ed2")
            h.run(3)
            local += 3
            frames += 3
            fr = h.frame
            if h.peek(PARTY + 0x46, 1) == b"\x01":  # 기절 — 이 시도는 여기까지
                break
            if is_menu(fr):
                commit(pend_key, pend_fr)
                pend_key, pend_n, pend_fr = None, 0, None
                if names is None:
                    names = names_in_battle(h, inv)
                    Image.fromarray(fr).save(os.path.join(gdir, "menu.png"))
                if not nav_turn_done:
                    h.poke(
                        obj + 48, struct.pack(">I", 0x1234 + t * 7919 + g * 104729 + tries * 31337)
                    )
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
                        # 🔴 키는 **글자 마스크**(흰·노랑)로 만든다 — 대기 커서 ▽(하늘색)가 깜박이면 크롭 해시가 계속 바뀌어 안정 판정이 영영 안 선다(보스 대사 그룹 63)
                        key = hashlib.md5(text_mask(crop).tobytes()).hexdigest()
                        if key == pend_key:
                            pend_n += 1
                            if pend_n >= 3:
                                commit(pend_key, pend_fr)
                            # 🔴 **입력을 기다리는 대사는 키를 줘야 넘어간다**(보스 시작 대사 — 그룹 63 카자즘 「크하하하하 너희 따위가…」가 ▽ 에서 영영 멈췄다, 10-20).
                            #    일반 전투 문구는 자동으로 넘어가므로, 같은 화면이 8번(72프레임) 연속 안 바뀔 때만 한 번 누른다.
                            if pend_n >= 8:
                                h.press("c", 3, 20)
                                pend_n = 3
                        else:
                            if pend_n < 3:
                                pass  # 도중 프레임은 버린다 — 다음 글이 이어 그려지는 중
                            pend_key, pend_n, pend_fr = key, 1, fr.copy()
                    else:
                        commit(pend_key, pend_fr)
                        pend_key, pend_n, pend_fr = None, 0, None
    # 🔴 **「ok」는 시도가 안 죽었다는 뜻이 아니다 — 요청한 턴을 다 채웠을 때만 ok**(2026-10-20: 그룹 63 카자즘이 턴 0 인데 ok 였고 manifest 분모에 묻혔다).
    #    턴이 모자라거나 몬스터 이름을 못 읽었으면 `short` — 분모를 채우지 못한 그룹으로 따로 센다.
    short = t < turns or not names
    return {
        "group": g,
        "status": "short" if short else "ok",
        **({"short_why": f"턴 {t}/{turns}" + ("" if names else " · 몬스터 이름 못 읽음")} if short else {}),
        "monsters": names or [],
        "turns": t,
        "tries": tries,
        "captures": caps,
    }


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


# ── ED1 (2026-10-19) — 전투가 **완전 자동**이다(명령 메뉴 없음, 파티가 알아서 공격, `c` 로 메시지를 넘긴다).
# 그래서 ED2 처럼 방어를 고를 필요가 없고, 몬스터 HP 를 높게 묶어 두고 `c` 를 연타하며 메시지를 캡처한다.
ED1_MON = (0x060BCD00, 64)  # 몬스터 슬롯 4칸: +0 번호 · +1 이름(SJIS, NUL) · +0x1C HP(BE32)
GAMES["ed1"]["mon"] = ED1_MON
ED1_PARTY_HP = (
    0x060AF5F4,
    0x060B0400,
    0x060B8824,
    0x060B8CA4,
)  # HP 사본 넷(+4 에 최대), 파티원 간격 108
ED1_GROUP = 0x060BF370  # 현재 조우 그룹 바이트(`0x06050280` 이 쓴다)
ED1_MSG_BOX = (146, 232, 14, 206)  # 아래 메시지 창 y0 y1 x0 x1
ED1_NO_GROUP = (5, 6, 35, 36, 37, 38, 39, 40)  # 점프표(0x060504D0)가 기본값 — 편성 없음


def ed1_boot_to_field(h):
    """타이틀 → 이어하기 → 슬롯 3 → 크루즈마을 부근 해안(바다가 막아 주는 자리, 몬스터 셋이 배회)."""
    h.run(2500)
    h.press("start", 6, 120)
    h.press("c", 5, 300)
    h.run(1500)
    h.press("start", 6, 200)  # 오프닝 건너뛰기 → 「처음부터 / 이어하기」
    h.run(1600)  # 타이틀 메뉴가 입력을 받을 때까지(실측: 곧바로 right 를 누르면 무시된다)
    for names, hold, after in (
        ("right", 5, 20), ("c", 5, 150), ("c", 5, 100), ("down", 5, 10), ("down", 5, 10),
        ("c", 5, 60), ("c", 5, 250),
    ):  # fmt: skip
        h.press(names, hold, after)
    h.run(300)
    h.held = {H.BTN["down"]}
    h.run(300)  # 마을 출구 → 해안 필드
    h.held = set()
    h.run(20)


def ed1_fill_party(h):
    for base in ED1_PARTY_HP:
        for m in range(4):
            a = base + 108 * m
            h.poke(a, h.peek(a + 4, 4))


def ed1_start_battle(h, nav_state, g):
    h.load(nav_state)
    h.run(5)
    for a in GAME["sites"]:
        assert h.peek(a, 2) in (GAME["orig"], bytes([GAME["op"], h.peek(a + 1, 1)[0]])), hex(a)
        h.poke(a, bytes([GAME["op"], g]))
    for n in range(40):  # 오른쪽 셋 → 위 → … (실측: 오른쪽 셋째 걸음에서 해안 몬스터와 닿는다)
        d = ("right", "right", "right", "up", "left", "up", "left", "down")[n % 8]
        h.held = {H.BTN[d]}
        h.run(40)
        h.held = set()
        h.run(10)
        if h.peek(ED1_GROUP, 1)[0] == g:
            return True
    return False


def ed1_run_group(h, nav_state, g, frames, outdir, inv):
    gdir = os.path.join(outdir, f"g{g:03d}")
    if not ed1_start_battle(h, nav_state, g):
        return {"group": g, "status": "조우 안 걸림"}
    os.makedirs(gdir, exist_ok=True)
    mon, stride = ED1_MON
    h.run(120)
    names = None
    seen, caps, y0, y1, x0, x1 = set(), 0, *ED1_MSG_BOX
    Image.fromarray(h.frame).save(os.path.join(gdir, "menu.png"))

    def pin(hp):
        for k in range(4):
            a = mon + stride * k + 0x1C
            if be32(h.peek(a, 4)):
                h.poke(a, struct.pack(">I", hp))

    pend = [None, 0, None]  # [크롭 해시, 연속 폴링 수, 프레임]

    def commit(key, fr_):
        nonlocal caps
        if key is not None and key not in seen:
            seen.add(key)
            caps += 1
            Image.fromarray(fr_).save(os.path.join(gdir, f"m{caps:02d}.png"))

    t = 0
    total = frames + 1500
    while t < total:
        ed1_fill_party(h)
        fill_names(h, "ed1", t)
        pin(0x7FFF if t < frames else 1)  # 앞 구간은 안 죽이고 · 뒤 구간은 죽여서 승리 문구까지
        h.run(3)
        t += 3
        if names is None and t >= 450:  # 슬롯 이름은 전투 그림이 올라온 뒤에야 찬다
            names = [n for k, n in enumerate(names_in_battle(h, inv, skip_empty=True)) if n]
        if t % 45 == 0:  # 키 간격이 짧으면 글이 안정 구간 없이 계속 바뀐다(옛 21프레임 → 덜 그려진 장 205, 10-19)
            h.press("c", 3, 0)
        if t % 9 == 0:
            crop = h.frame[y0:y1, x0:x1]
            if has_text(crop):
                key = hashlib.md5(crop.tobytes()).hexdigest()
                if key == pend[0]:
                    pend[1] += 1
                    if pend[1] >= 2:  # 같은 크롭이 두 번 연속 폴링(18프레임) 안 바뀌면 다 그려진 것
                        commit(key, pend[2])
                else:
                    pend[:] = [key, 1, h.frame.copy()]
            else:
                commit(*([pend[0], pend[2]] if pend[0] else [None, None]))  # 글이 사라질 때는 마지막 프레임을 쓴다
                pend[:] = [None, 0, None]
        if (
            t > frames
            and all(be32(h.peek(mon + stride * k + 0x1C, 4)) == 0 for k in range(4))
            and t > frames + 900
        ):
            break
    short = caps == 0 or not names  # ED1 은 프레임 수로 돈다 — 캡처가 하나도 없거나 이름을 못 읽으면 short
    return {
        "group": g,
        "status": "short" if short else "ok",
        **({"short_why": ("캡처 0" if caps == 0 else "") + ("" if names else " 몬스터 이름 못 읽음")} if short else {}),
        "monsters": names or [],
        "frames": t,
        "captures": caps,
    }


def ed1_contact_sheet(gdir, cols=3):
    fs = sorted(f for f in os.listdir(gdir) if f.startswith("m") and f.endswith(".png"))
    if not fs:
        return None
    y0, y1, x0, x1 = ED1_MSG_BOX
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
    ap.add_argument("--game", choices=sorted(GAMES), default="ed2")
    ap.add_argument(
        "--frames", type=int, default=1800, help="[ed1] 몬스터를 안 죽이고 버티는 프레임"
    )
    ap.add_argument("--no-fill-names", action="store_true", help="파티 이름 버퍼를 채우지 않는다(원 하네스 조건)")
    ap.add_argument(
        "--party-name",
        default=None,
        help="파티 이름을 한 가지로 고정한다(받침 있음/없음 두 판 비교 — 기본은 ED1 두 이름을 번갈아)",
    )
    ap.add_argument("--pre-idle", type=int, default=0, help="조우를 걸기 전에 더 두는 프레임 수(난수 편성의 다른 변형)")
    ap.add_argument("--groups", default="62")
    ap.add_argument("--turns", type=int, default=20)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=None)
    ap.add_argument("--bkr", default=DEFAULT_BKR)
    ap.add_argument(
        "--nav-only", action="store_true", help="필드 상태만 만들고 끝낸다(병렬 실행 전)"
    )
    a = ap.parse_args()
    import common

    global GAME, FILL_NAMES
    GAME = GAMES[a.game]
    global PRE_IDLE
    PRE_IDLE = a.pre_idle
    FILL_NAMES = not a.no_fill_names
    if a.party_name:
        addr, lim, _ = PARTY_NAME_TAB[a.game]
        PARTY_NAME_TAB[a.game] = (addr, lim, (a.party_name,))
        PARTY_NAME_EXTRA[a.game] = PARTY_NAME_ADDRS[a.game]
    if a.game == "ed1" and a.groups == "62":
        a.groups = GAME["groups"]

    cue = a.cue or os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue")
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, cue, a.out, bkr=a.bkr)
    nav = os.path.join(H.CACHE, "beetle-saturn", f"{GAME['state']}_{image_key(cue)}.state")
    if not os.path.exists(nav):
        (ed1_boot_to_field if a.game == "ed1" else boot_to_field)(h)
        h.save(nav)
    if a.nav_only:
        return
    inv = inverse_map()
    rows = []
    for g in parse_groups(a.groups):
        if a.game == "ed1":
            if g in ED1_NO_GROUP:
                continue
            r = ed1_run_group(h, nav, g, a.frames, a.out, inv)
            if r.get("status") == "ok":
                ed1_contact_sheet(os.path.join(a.out, f"g{g:03d}"))
            rows.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
            continue
        r = run_group(h, nav, g, a.turns, a.out, inv)
        rows.append(r)
        if r.get("status") == "ok":
            contact_sheet(os.path.join(a.out, f"g{g:02d}"))
        print(json.dumps(r, ensure_ascii=False), flush=True)
    tag = a.groups.replace(",", "_")
    with open(os.path.join(a.out, f"table_{tag}.json"), "w") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    cnt = {}
    for r in rows:
        cnt[r["status"]] = cnt.get(r["status"], 0) + 1
    print(f"요약 {cnt} — short(분모를 못 채움) {[r['group'] for r in rows if r['status'] == 'short']} · 안 걸림 {[r['group'] for r in rows if r['status'] == '조우 안 걸림']}", flush=True)


if __name__ == "__main__":
    main()
