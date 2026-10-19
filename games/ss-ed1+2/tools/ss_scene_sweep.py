#!/usr/bin/env python3
"""ED2 **전 씬 대사 일괄** — 씬 파일(`/BIN/ED2SCNnn.BIN`)의 메시지 번호를 하나씩 **실제 대화창으로** 띄워 찍는다
(헤드리스 새턴 하네스 `ss_headless.py`, 롬·이미지는 안 고친다 — RAM 쓰기 + RAM 위 SH-2 스텁뿐).

    python3 tools/ss_scene_sweep.py --scenes 1 --out <폴더>              # 한 씬
    python3 tools/ss_scene_sweep.py --scenes 1-47 --out <폴더>           # 전 씬
    python3 tools/ss_scene_sweep.py --scenes 1 --ids 0,2,12 --out <폴더> # 번호 지정
    python3 tools/ss_scene_sweep.py --scenes 1 --probe-only --out <폴더> # 번호별 스크립트 버퍼만(찍지 않음)
    python3 tools/ss_scene_sweep.py --scenes 8 --ids 214 --args --out <폴더>  # 런타임 인자(%s·%d)에 대표 값을 넣어 변형별로 두 번 찍는다
    python3 tools/ss_scene_sweep.py --game ed1 --scenes 1 --out <폴더>   # ED1 씬(/BIN/ED1SCNnn.BIN) — 아래 「ED1」 절

산출: `<out>/ED2SCN01/id012_p1.png …`(한 번호가 여러 창이면 p1·p2 …) + `<out>/index.json`
(씬 · 번호 · 쪽 · 파일 · 스크립트 바이트). 🔴 문안은 이 캡처의 **화면**으로만 판정한다 — 상태는 번호마다 새로 되돌린다.

## 구조 (2026-10-19 실측)
- **씬 파일은 RAM `0x060B8000` 에 올라오는 네이티브 SH-2 코드**다. 초기화 코드가 함수 포인터를 RAM 에 등록한다 —
  `0x060A0878` ← **번호→스크립트 함수**(`f(r4=번호, r5=출력버퍼)`; 버퍼엔 `02`=창 시작 · `01`=이름 끝 · `0a`=줄 · `08`=창
  끝(뒤에 `02` 가 또 오면 다음 창) · `06`=끝 인 **게임 글자코드 바이트열**이 든다. 번호가 범위 밖이거나 문안이 아니면 빈 버퍼).
- **번호를 대화창으로 띄우는 함수 = `ED2.BIN 0x06054AF8(r4=번호)`** — 번호 → `0x0602CBD0`(= `[0x060A0878]` 호출)로 스크립트를
  받아 글자를 모아 `0x0605AA94`(창 열기)로 띄우고 키를 기다린다. 필드의 NPC·이벤트가 부르는 바로 그 경로다.
- **호출 방법**: 레지스터를 못 쓰므로 `ED2.BIN 0x0605C09C`(필드·대기 루프가 프레임마다 부르는 틱)의 앞 12바이트를 `jmp 스텁`으로
  바꾸고, 스텁이 우편함(`0x060F7000`: +0 함수 주소 · +4 r4 · +12 r5 · +8 끝난 횟수)을 보고 **있으면 그 함수를 `jsr`** 한다.
  함수가 키 대기로 안에서 돌아도 틱이 다시 불려 안전하다(재진입 때 우편함은 이미 비어 있다). 코어의 명령 캐시는 안 켜져 있어(`Data only`)
  RAM 쓰기가 곧바로 먹는다. 우편함·스텁은 호스트가 읽고 쓰는 칸이라 CPU 쪽은 캐시를 우회하는 `0x26……` 미러로 읽는다.
- 🔴 씬 초기화(`0x060B800C`)는 **돌리지 않는다**(맵 로딩·이벤트 시작까지 같이 돈다) — 번호→스크립트 포인터(`0x060A0878`)만 직접
  쓴다. 다른 두 포인터(`0x0609ED10` 이벤트 핸들러 · `0x060A0800`)까지 쓰면 **엔진이 그 씬의 시작 이벤트를 스스로 돌려** 화면이 오염된다(실측).
- 필드 탐색 상태(`ed2_field_<지문>.state`)는 `ss_battle_sweep.py` 와 같은 것을 쓴다(없으면 만든다).
## 런타임 인자 `--args` (2026-10-19 실측)
문안의 `%s`(이름·아이템)·`%d`(수치)는 **씬 코드가 `sprintf(0x0607B180)` 로 채운다**(번호→스크립트 함수 안: `r7 = 0x0609F870 + 32×아이템번호` 처럼
게임 상태에서 퍼 온다). 구동기는 씬 초기화를 안 돌려 그 상태가 0 이라 **빈칸/0** 이 찍힌다(가짜 결함). 그래서 롬 대신 **RAM 표를 채운다**:
- 아이템 이름표 `0x0609F870`(32B 칸 × 120 · 이름은 칸 앞 16B, 게임 글자코드 NUL 끝) — **전 칸의 이름**을 대표 값으로 덮는다
  (어느 번호가 어느 칸을 고르든 같은 이름이 나온다. 상자 번호→아이템 표 `0x0609F4C8` 은 씬 데이터라 0 = 칸 0 이다).
- 파티 이름 `0x0609E1F8 + 108×k`(k=1~4 파티원 · 칸 앞 12B) — 상자 여는 사람 · 화자 이름.
- 수치 `0x060A07C8`(dword · 상점 값 `n Gold`).
변형 `a` = 받침 없는 이름 · 최장 아이템 · 한 자리 / `b` = 받침 있는 이름 · 짧은 아이템 · 다섯 자리. 캡처 이름 `idNNN_a_pK.png`.
⚠ 이 표들이 안 덮는 인자(주문 · 지명 · 다른 수치 칸)는 그대로 빈칸/0 이다.
ED1 은 `ED1_ARGS`(아래 「ED1」 절 끝) — 파티 레코드 0x060B8808+108k(k=0~4) · 아이템 이름표 0x060BE470(32B×117) · 상점 값 0x060BF368.

## ED1 (`--game ed1`, 2026-10-19 실측 — 구조는 ED2 와 같되 주소가 다르고 **씬 파일 하나에 지역 모듈이 여럿**이다)
- 씬 파일은 RAM `0x060D0000` 에 올라온다. 번호→스크립트 함수는 포인터 등록이 아니라 **본체(ED.BIN) 하드코딩**이다 —
  `ED.BIN 0x06038DA0(r4=번호, r5=버퍼)` 가 필드 바이트 `0x060BF39E`(·`0x060BF39F`)로 갈라 `0x060Dxxxx` 함수를 직접 부른다(리터럴).
  그래서 우리는 이 함수의 앞 12바이트를 `jmp 모듈의 번호→스크립트 함수` 로 바꾼다(RAM 쓰기만). 모듈의 함수는 본체 분기
  리터럴 중 씬 파일 안에서 「`cmp/hi r1,r4` + `jmp` 표 + `strcpy(0x06095C28)` 호출」 서명을 가진 것이다(파일당 1~6개 = 지역 모듈).
- 번호 → 대화창 = `ED.BIN 0x06040538(r4=번호)`(ED2 의 0x06054AF8 과 같은 모양: 스크립트 받기 · 준비 0x0604085C · 그리기 0x06040580 · 마무리 0x060408B0).
  프레임 틱 = `ED.BIN 0x0608083C`(모드 바이트 `0x060BF315`, 모드 ≤14, 앞 6명령 `…e10e`).
- 스크립트 버퍼 규약은 ED2 와 같다(`02` 창 시작 · `01` 이름 끝 · `0a` 줄 · `08` 창 끝 · `06` 끝).

- `--args`: sprintf(`0x06095BCC`)의 %s 는 파티 레코드·아이템 이름표(번호는 상점 구조 0x060BF350+7+슬롯 바이트)에서, %d(상점 값)는 0x060BF368 에서 온다. NPC 이름은 씬 안 상수다.

⚠ 번호마다 스테이트를 되돌린다 — 한 번호의 이벤트가 만든 플래그·NPC 이동이 다음 번호에 새지 않게.
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

import ss_battle_sweep as B
import ss_headless as H

HOOK = 0x060F6000  # 스텁 (필드 상태에서 0 으로 비어 있는 칸)
MB = 0x260F7000  # 우편함 — 캐시 우회 미러(호스트 쪽 peek/poke 는 하위 29비트만 본다)
TICK = 0x0605C09C  # 프레임 틱 (앞 12B 를 jmp 스텁으로 바꾼다)
TICK_RET = TICK + 12
EVENT_RUN = 0x06054AF8  # 번호 → 대화창 (r4=번호)
SCN_BASE = 0x060B8000
PTR_TEXT = 0x060A0878  # 번호→스크립트 함수 포인터
BUF = 0x060F8000  # 스크립트 버퍼 (0x400)
MODE_BYTE = 0x060A0773

# ── 게임별 주소 (configure 가 모듈 전역을 덮는다)
GAMES = {
    "ed2": dict(
        tag="ED2", scn_base=0x060B8000, tick=0x0605C09C, mode_byte=0x060A0773, event_run=0x06054AF8,
        imm=0xE10F, orig_first=(0x2FE6, 0x4F22, 0xD141, 0x6110, 0x621C, 0xE10F), dispatch=None,
    ),
    "ed1": dict(
        tag="ED1", scn_base=0x060D0000, tick=0x0608083C, mode_byte=0x060BF315, event_run=0x06040538,
        imm=0xE10E, orig_first=(0x2FE6, 0x4F22, 0xD13E, 0x6110, 0x621C, 0xE10E), dispatch=0x06038DA0,
    ),
}
GAME = "ed2"


def configure(game):
    """주소 모음을 모듈 전역에 올린다 — 아래 함수들은 호출 때 전역을 읽는다."""
    global GAME, TICK, TICK_RET, EVENT_RUN, SCN_BASE, MODE_BYTE, ORIG_FIRST, DISPATCH, TAG
    g = GAMES[game]
    GAME, TAG = game, g["tag"]
    TICK, TICK_RET, EVENT_RUN = g["tick"], g["tick"] + 12, g["event_run"]
    SCN_BASE, MODE_BYTE, ORIG_FIRST, DISPATCH = g["scn_base"], g["mode_byte"], g["orig_first"], g["dispatch"]


NOOP_FN = bytes.fromhex("2fe66ef36ef6000b")  # push r14 · mov r15,r14 · pop r14 · rts — 문안 없는 씬의 빈 함수
configure("ed2")  # 기본 = ED2 (ORIG_FIRST = 덮어쓰는 TICK 앞 6명령 — 스텁이 재현한다)


def build_stub():
    """우편함을 보고 함수를 부르는 스텁 → (바이트, 본문 길이). 손인코딩이라 `verify_stub` 가 읽어 대조한다."""
    code, fix = [], []

    def w(x):
        code.append(x)

    def ldl(name, reg):  # mov.l @(name,pc),reg
        fix.append((len(code), name, "pc"))
        w(0xD000 | (reg << 8))

    for m in range(8):
        w(0x2F06 | (m << 4))  # mov.l rm,@-r15  (r0..r7)
    w(0x4F22)
    w(0x4F12)
    w(0x4F02)  # sts.l pr / macl / mach
    ldl("MB", 1)
    w(0x5315)
    w(0x7301)
    w(0x1135)  # [mb+20]++ (진단: 틱 횟수)
    w(0x6212)  # r2 = [mb] (함수 주소)
    w(0x2228)  # tst r2,r2
    fix.append((len(code), "skip", "bt"))
    w(0x8900)  # bt skip
    w(0xE300)
    w(0x2132)  # [mb] = 0 (먼저 비운다 — 재진입 방지)
    w(0x5411)  # r4 = [mb+4]
    w(0x5513)  # r5 = [mb+12]
    w(0x420B)  # jsr @r2   ⚠ jsr=4m0B, jmp=4m2B — 처음에 jmp 로 써서 돌아오지 않았다
    w(0x0009)
    ldl("MB", 1)
    w(0x5212)
    w(0x7201)
    w(0x1122)  # [mb+8]++ (끝난 횟수)
    skip_at = len(code)
    w(0x4F06)
    w(0x4F16)
    w(0x4F26)  # lds.l mach / macl / pr
    for m in range(7, -1, -1):
        w(0x6006 | (m << 8) | (15 << 4))  # mov.l @r15+,rm
    for x in ORIG_FIRST[:2]:
        w(x)  # 덮어쓴 앞 두 명령 재현 (push r14 · push pr)
    ldl("A", 1)
    w(0x6110)
    w(0x621C)
    w(ORIG_FIRST[5])  # 덮어쓴 d1xx(=mov.l @(A),r1) · 6110 · 621c · e10f(ED1 은 e10e) 재현
    ldl("RET", 0)
    w(0x402B)
    w(0x0009)  # jmp @r0
    while len(code) % 2:  # 리터럴 풀은 4바이트 정렬
        w(0x0009)
    body = len(code) * 2
    pool = [("MB", MB), ("FN", EVENT_RUN), ("A", MODE_BYTE), ("RET", TICK_RET)]
    out = bytearray()
    for x in code:
        out += struct.pack(">H", x)
    pool_at = {}
    for n, v in pool:
        pool_at[n] = len(out)
        out += struct.pack(">I", v)
    for i, n, k in fix:
        if k == "pc":
            pc = i * 2
            d = (pool_at[n] - ((pc + 4) & ~3)) // 4
            assert 0 <= d < 256, n
            out[pc + 1] = d
        else:
            d = (skip_at * 2 - (i * 2 + 4)) // 2
            assert -128 <= d < 128
            out[i * 2 + 1] = d & 0xFF
    return bytes(out), body


def verify_stub(code, body):
    """스텁 본문을 2바이트씩 캡스톤으로 읽어 전부 해독되는지 + 우리가 의도한 호출(jsr)·분기가 있는지 본다."""
    import capstone

    md = capstone.Cs(capstone.CS_ARCH_SH, capstone.CS_MODE_SH2 | capstone.CS_MODE_BIG_ENDIAN)
    text = []
    for o in range(0, body, 2):
        ins = list(md.disasm(code[o : o + 2], HOOK + o))
        assert ins, f"해독 실패 @{o:#x}: {code[o : o + 2].hex()}"
        text.append(f"{ins[0].mnemonic} {ins[0].op_str}")
    assert "jsr @r2" in text and text.count("jmp @r0") == 1, "호출/복귀 명령이 의도와 다르다"
    return text


def hook_patch_to(target):
    """ED1: 분배기 앞 12B → `jmp target`(스텁과 같은 꼴, 리터럴만 다르다)."""
    return struct.pack(">HHHH", 0xD001, 0x402B, 0x0009, 0x0009) + struct.pack(">I", target)


def valid_script(script):
    """스크립트 버퍼 모양 검사 — `02`(창 시작) 또는 글자코드로 시작한다(함수 후보가 엉뚱한 것이면 걸러낸다)."""
    return script[:1] == b"\x02" or script[0] >= 0x80  # 화자 없는 독백·메뉴 문구는 02 없이 글자코드로 시작한다(씬 17·21 실측)


def boot_to_field_ed1(h):
    """타이틀 → 첫째 게임(영웅전설 I) → 이어하기(세이브 슬롯 1) → 필드. 입력 열은 하네스로 실측(2026-10-19)."""
    h.run(2500)
    for names, hold, after in (("start", 6, 120), ("c", 5, 300)):
        h.press(names, hold, after)
    h.run(1500)
    h.press("start", 6, 200)
    h.run(1600)
    for names, hold, after in (("right", 5, 20), ("c", 5, 120), ("c", 5, 90), ("c", 5, 90), ("c", 5, 200), ("c", 5, 200)):
        h.press(names, hold, after)


def hook_patch():
    """TICK 앞 12B → `mov.l @(pc),r0 ; jmp @r0 ; nop ; nop ; .long 스텁`."""
    return struct.pack(">HHHH", 0xD001, 0x402B, 0x0009, 0x0009) + struct.pack(">I", HOOK)


# ── 하네스 보조
def p32(h, a, v):
    h.poke(a, struct.pack(">I", v))


def g32(h, a):
    return struct.unpack(">I", h.peek(a, 4))[0]


def snapshot(h):
    import ctypes as C

    n = h.core.retro_serialize_size()
    b = C.create_string_buffer(n)
    assert h.core.retro_serialize(b, n)
    return b.raw


def restore(h, raw):
    assert h.core.retro_unserialize(raw, len(raw))


def scene_files(common, cue):
    f, mm = common.open_image(cue.replace(".cue", ".bin"))
    fl = {n: (lba, size) for n, lba, size in common.iso_files(mm)}
    return mm, fl


def text_fn(d):
    """씬 초기화 코드 안에서 `[0x060A0878] = 함수` 를 찾는다 — `mov.l @(pc),rN` 리터럴 중 `0x060A0878` 바로 뒤 씬 범위 값."""
    lits = []
    for o in range(0x0C, min(len(d), 0x400), 2):
        w = struct.unpack(">H", d[o : o + 2])[0]
        if (w & 0xF000) == 0xD000:
            t = ((o + 4) & ~3) + (w & 0xFF) * 4
            if t + 4 <= len(d):
                lits.append((o, (w >> 8) & 15, struct.unpack(">I", d[t : t + 4])[0]))
    for i, (_o, r, v) in enumerate(lits):
        if v == PTR_TEXT:
            for j in range(i + 1, min(len(lits), i + 3)):
                _o2, r2, v2 = lits[j]
                if SCN_BASE <= v2 < SCN_BASE + len(d) and r2 != r:
                    return v2
    return None


ED1_MSG_RANGE = (0x06038DA0, 0x0603AA0A)  # ED.BIN 0x06038DA0 번호→스크립트 분배기 본문 (리터럴 함수 주소가 여기 있다)
STRCPY = struct.pack(">I", 0x06095C28)


def ed1_dispatch_targets(ed):
    """ED.BIN 의 분배기 본문에서 씬 영역(0x060D0000~)을 가리키는 4바이트 리터럴 → 후보 함수 주소 집합."""
    base = 0x06028000
    out = set()
    for o in range(ED1_MSG_RANGE[0] - base, ED1_MSG_RANGE[1] - base, 2):
        v = struct.unpack(">I", ed[o : o + 4])[0]
        if 0x060D0000 <= v < 0x060F0000 and not v & 1:
            out.add(v)
    return sorted(out)


def ed1_text_fns(d, targets):
    """씬 파일 `d` 안의 지역 모듈별 번호→스크립트 함수들. 서명 = **함수 머리**(첫 명령이 `mov.l rN,@-r15` 푸시) +
    앞 48워드에 `cmp/hi r1,r4`(3416) · 56워드에 `jmp @r0`(402b) + 뒤 0x700B 안에 `strcpy`(0x06095C28) 호출 리터럴.
    🔴 머리 조건이 없으면 **함수 중간**(다른 씬에서 머리였던 주소)이 통과해 돌아오지 않는다(2026-10-19 씬 16·25 실측 —
    그리고 진짜 머리(prologue 가 길어 cmp 가 24워드 밖)는 걸러졌다). 이 주소 집합은 본체의 모든 씬 합집합이라 씬마다 맞는 것만 남는다."""
    out = []
    for v in targets:
        o = v - SCN_BASE
        if o < 0 or o + 0x80 > len(d):
            continue
        w = struct.unpack(">64H", d[o : o + 128])
        if (w[0] & 0xFF0F) != 0x2F06:
            continue
        if 0x3416 in w[:48] and 0x402B in w[:56] and STRCPY in d[o : o + 0x700]:
            out.append(v)
    if not out:  # 본체 분배기 리터럴에 이 씬의 함수가 없다(씬 24·28 실측) — 씬 파일 안을 직접 훑어 같은 서명의 머리를 찾는다
        prev = -4
        for o in range(0, len(d) - 0x80, 2):
            w = struct.unpack(">64H", d[o : o + 128])
            if (w[0] & 0xFF0F) == 0x2F06 and 0x3416 in w[:48] and 0x402B in w[:56] and STRCPY in d[o : o + 0x1000]:
                if o - prev > 2:  # 연속한 푸시 열은 맨 앞 하나만(그 뒤는 같은 함수의 중간)
                    out.append(SCN_BASE + o)
                prev = o
    return out


# ── 화면 판정 — 대화창은 남색(0,0,128) 바탕이다. 오른쪽 상태 패널(x≥205)도 남색이라 왼쪽만 본다
NAVY = np.array([0, 0, 128], dtype=np.uint8)
WIN_X0, WIN_X1 = 8, 205


def window_sig(frame):
    """대화창이 떠 있나 + 내용 서명(맨 아래 ▽ 깜박임 줄 제외). 없으면 None."""
    m = (frame[:, WIN_X0:WIN_X1] == NAVY).all(axis=2)
    rows = np.where(m.sum(axis=1) > 120)[0]
    if len(rows) < 30:
        return None
    y0, y1 = int(rows.min()), int(rows.max())
    return hashlib.md5(frame[y0 : y1 - 15, WIN_X0:WIN_X1].tobytes()).hexdigest()


def window_blank(frame):
    """대화창은 떠 있는데 안이 비었나(글자 픽셀 15 미만) — `[끝]` 뒤 `0b`(상점·질문 메뉴 코드)가 이어지는 번호에서 메뉴가 안 그려진 빈 창이 남는다.
    🔴 이걸 「쪽」으로 찍지 않는다(2026-10-19 manager — ED1 SCN05 id225·226 의 빈 여분 쪽 6장)."""
    m = (frame[:, WIN_X0:WIN_X1] == NAVY).all(axis=2)
    rows = np.where(m.sum(axis=1) > 120)[0]
    if len(rows) < 30:
        return False
    y0, y1 = int(rows.min()) + 4, int(rows.max()) - 4
    inner = frame[y0:y1, 20:200]
    nonbg = ~(inner == NAVY).all(axis=2) & (inner.max(axis=2) > 120)
    return int(nonbg.sum()) < 15


def trim(buf):
    """스크립트 버퍼의 유효 길이 — 끝 표지(`06`) 까지, 없으면 마지막 0 아닌 바이트까지(실측: 한 번호의 글자코드는 0 이 없다)."""
    i = buf.find(b"\x06")
    n = len(buf.rstrip(b"\x00"))
    return buf[: i + 1] if 0 <= i < n else buf[:n]


def expected_pages(script):
    """스크립트의 쪽 수 — 글자코드(0x80↑ 2바이트)를 건너뛰며 `08`(창 끝, 뒤에 내용이 이어질 때) · `09`(창 안 키 대기)
    마다 +1. 캡처 수 대조용. `0b`(예/아니오 질문)·`0c`(끝)는 쪽을 안 가른다."""
    i, n = 0, 1
    while i < len(script):
        c = script[i]
        if c >= 0x80:
            i += 2
            continue
        if c == 0x08 and i + 1 < len(script) and script[i + 1] not in (0, 6, 0x0B, 0x0C):
            n += 1
        elif c == 0x09:  # 창 안에서 키 대기 후 이어 쓴다 — 화면은 쪽이 바뀐다
            n += 1
        i += 1
    return n


def wait_done(h, n0, maxf=int(os.environ.get("SWEEP_WAITF", "60"))):  # 환경변수로 늘려 느린 함수를 가린다
    f = 0
    while g32(h, MB + 8) == n0 and f < maxf:
        h.run(1)
        f += 1
    return g32(h, MB + 8) != n0


def read_script(h, snap, fn, i):
    restore(h, snap)
    h.run(1)
    h.poke(BUF, bytes(0x400))
    n0 = g32(h, MB + 8)
    p32(h, MB + 4, i)
    p32(h, MB + 12, BUF)
    p32(h, MB, fn)
    ok = wait_done(h, n0)
    return ok, trim(h.peek(BUF, 0x400))


POKES = []  # [(주소, 바이트)] — `--poke 주소:헥스`
RECHECK = False  # `--recheck`: 쪽을 찍은 뒤 60프레임 더 두고 다시 비교한다(도중 프레임이 없는지 — 완성 근거)
RECHECK_LOG = []  # [(태그, 쪽 번호, 다른 글자 픽셀 수)]


def win_text_mask(frame):
    """대화창 안의 글자(흰·노랑) 마스크 — ▽ 깜박임·배경은 뺀다. 창을 못 찾으면 None."""
    blue = (frame[:, :, 0] < 20) & (frame[:, :, 1] < 20) & (frame[:, :, 2] > 100) & (frame[:, :, 2] < 160)
    ys = np.where(blue[:, 20])[0]
    if len(ys) < 20:
        return None
    runs, s, prev = [], ys[0], ys[0]
    for y in ys[1:]:
        if y != prev + 1:
            runs.append((s, prev))
            s = y
        prev = y
    runs.append((s, prev))
    r = max(runs, key=lambda x: x[1] - x[0])
    if r[1] - r[0] < 50:
        return None
    c = frame[r[0] : r[1] + 1, 16:200].astype(int)
    return ((c[:, :, 0] > 200) & (c[:, :, 1] > 200) & (c[:, :, 2] > 200)) | ((c[:, :, 0] > 200) & (c[:, :, 1] > 200) & (c[:, :, 2] < 120))


def play_id(h, snap, i, outdir, tag, maxpolls=900):
    """번호 i 를 대화창으로 띄워 쪽마다 찍는다 → (캡처 파일 목록, 사유).

    ⚠ 호출이 돌아왔다(끝난 횟수 +1)고 끝이 아니다 — **예/아니오 질문(`0b`)은 창을 열고 곧바로 돌아오고** 선택은 게임 루프가
    받는다(실측: 상점 인사말 번호 — 돌아온 뒤에도 창이 남는다). 돌아온 뒤에도 창이 떠 있으면 한 번 더 찍고 멈춘다(키는 안 준다).
    """
    restore(h, snap)
    h.run(1)
    for addr, data in POKES:  # 시험 문자 주입(`--poke`) — 번호를 부르기 직전에 RAM 의 문안을 덮는다
        h.poke(addr, data)
    n0 = g32(h, MB + 8)
    p32(h, MB + 4, i)
    p32(h, MB, EVENT_RUN)
    shots, last, stable, cap_sig, nudges, absent = [], None, 0, None, 0, 0
    returned = 0  # 호출이 돌아온 뒤 센 폴링
    for _ in range(maxpolls):
        h.run(2)
        if g32(h, MB + 8) != n0:
            returned += 1
        sig = window_sig(h.frame)
        if returned and sig is None:
            if returned > 6:
                return shots, "끝"
        if sig is None:
            absent += 1
            last, stable = None, 0
            if absent > 200:  # 창 없이 오래 — 이벤트 대기일 수 있다, 키를 한 번 준다
                h.press("c", 4, 2)
                absent = 100
                nudges += 1
                if nudges > 8:
                    return shots, "창 없이 정지"
            continue
        absent = 0
        stable = stable + 1 if sig == last else 1
        last = sig
        if stable >= 3 and sig != cap_sig and window_blank(h.frame):
            if returned:  # 돌아온 뒤 빈 창 = 메뉴 코드(`0b`) 뒤 — 쪽이 아니다
                return shots, "끝"
            cap_sig = sig
            h.press("c", 4, 2)
            stable = 0
        elif stable >= 3 and sig != cap_sig:
            name = f"{tag}_p{len(shots) + 1}.png"
            Image.fromarray(h.frame).save(os.path.join(outdir, name))
            shots.append(name)
            if RECHECK:  # 60프레임 더 두고 글자가 그대로인지 — 도중 프레임이었다면 더 그려진다
                m1 = win_text_mask(h.frame)
                h.run(60)
                m2 = win_text_mask(h.frame)
                RECHECK_LOG.append((tag, len(shots), -1 if m1 is None or m2 is None or m1.shape != m2.shape else int((m1 != m2).sum())))
            cap_sig, stable, nudges = sig, 0, 0
            if returned:  # 돌아온 뒤의 창 = 질문 — 눌러서 상점·메뉴로 들어가지 않는다
                return shots, "끝"
            h.press("c", 4, 2)
        elif stable >= 20 and sig == cap_sig:  # 눌렀는데 안 넘어갔다
            if returned:
                return shots, "끝"
            nudges += 1
            stable = 0
            if nudges > 4:
                return shots, "쪽 안 넘어감"
            h.press("c", 4, 2)
        elif returned > 40:
            return shots, "끝"
    return shots, "시간 초과"


# ── 런타임 인자 대표 값 (--args)
ITEM_TAB, ITEM_STRIDE, ITEM_N, ITEM_NAME_MAX = 0x0609F870, 32, 120, 16  # 이름표 · 칸 · 칸 수(0~119, 120 부터는 다른 구조 — 덮으면 깨진다) · 이름 필드
PARTY_TAB, PARTY_STRIDE, PARTY_IDX, PARTY_NAME_MAX = 0x0609E1F8, 108, range(1, 5), 12  # 칸 0·5 이상은 이름이 아닌 구조다
NUM_ADDR = 0x060A07C8  # 상점 값(dword) — `%d Gold`
# ED1 (씬 코드의 sprintf 인자 리터럴에서 실측, 2026-10-19): 서식은 `%c%s%c …%d Gold` 처럼 sprintf(0x06095BCC)(r4=버퍼, r5=서식, r6…) 로 채운다.
#  %s(화자 이름) = 파티 레코드 0x060B8874+108k(k=0~3, 이름 앞 12B) — 0x060B8808(k=-1)도 씬 8·9·10·13 이 이름으로 읽는다. NPC 이름은 씬 안 상수라 주입이 필요 없다.
#  %s(아이템) = 이름표 0x060BE470+32×아이템번호(0~116, 이름 앞 16B). 번호는 상점 구조 0x060BF350+7+슬롯 / 소지품 0x060BC490 바이트에서 오고, 기본 0 = 빈 이름이다.
#  %d(상점 값) = 상점 구조 0x060BF350+24 (dword).
ED1_ARGS = dict(
    item_tab=0x060BE470, item_stride=32, item_n=117, item_name_max=16,
    party_tab=0x060B8808, party_stride=108, party_idx=range(0, 5), party_name_max=12, num_addr=0x060BF350 + 24,
)
ARG_VARIANTS = {
    "a": dict(person="아트라스", item="프레이아의 미소", num=5),  # 받침 없음 · 최장(7.5칸) · 한 자리
    "b": dict(person="류난", item="횃불", num=50000),  # 받침 있음 · 짧은 이름 · 다섯 자리
}


def encode_name(kr, limit):
    """한글 문안 → 게임 글자코드(슬롯 SJIS 2B · 공백 1B) + NUL 채움 → `limit` 바이트."""
    import josa

    sc = josa.slot_codes()
    out = b"".join(b" " if c == " " else struct.pack(">H", sc[c]) for c in kr)
    assert len(out) < limit, f"{kr}: {len(out)}B ≥ {limit}"
    return out.ljust(limit, b"\x00")


def inject_args(h, var):
    """RAM 표에 변형 `var` 의 대표 값을 쓴다(롬 불변). 번호마다 스냅샷을 되돌리므로 **스냅샷 찍기 전에** 부른다."""
    v = ARG_VARIANTS[var]
    c = ED1_ARGS if GAME == "ed1" else dict(
        item_tab=ITEM_TAB, item_stride=ITEM_STRIDE, item_n=ITEM_N, item_name_max=ITEM_NAME_MAX,
        party_tab=PARTY_TAB, party_stride=PARTY_STRIDE, party_idx=PARTY_IDX, party_name_max=PARTY_NAME_MAX, num_addr=NUM_ADDR,
    )
    item = encode_name(v["item"], c["item_name_max"])
    for k in range(c["item_n"]):
        h.poke(c["item_tab"] + c["item_stride"] * k, item)
    person = encode_name(v["person"], c["party_name_max"])
    for k in c["party_idx"]:
        h.poke(c["party_tab"] + c["party_stride"] * k, person)
    p32(h, c["num_addr"], v["num"])


def parse_range(s, lo=1):
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += range(int(a), int(b) + 1)
        elif part:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", choices=sorted(GAMES), default="ed2", help="ed2(기본) | ed1")
    ap.add_argument("--scenes", default="1", help="씬 번호(ED2SCNnn · ED1SCNnn) — 1,3,5-9")
    ap.add_argument("--ids", default=None, help="번호 지정(없으면 0~--max-id 중 스크립트가 있는 것 전부)")
    ap.add_argument("--max-id", type=int, default=255)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=None)
    ap.add_argument("--bkr", default=B.DEFAULT_BKR)
    ap.add_argument(
        "--args",
        nargs="?",
        const="a,b",
        default=None,
        help="런타임 인자(%%s·%%d)에 대표 값을 넣어 변형별로 찍는다(a=받침 없음·최장 아이템·한 자리 / b=받침 있음·짧은 아이템·다섯 자리). 기본 a,b",
    )
    ap.add_argument("--state", default=None, help="필드 상태 파일(없으면 이미지 지문으로 찾고, 그것도 없으면 부팅해서 만든다)")
    ap.add_argument("--probe-only", action="store_true", help="번호별 스크립트 버퍼만 읽는다(찍지 않음)")
    ap.add_argument("--recheck", action="store_true", help="쪽마다 60프레임 더 두고 글자 마스크를 다시 비교해 `recheck.json` 에 남긴다(완성 근거 표본 검사)")
    ap.add_argument("--poke", action="append", default=[], help="번호 호출 직전에 RAM 을 덮는다 — 주소:헥스(여러 번 가능). 하네스 대 실게임 창 비교용 시험 문자")
    ap.add_argument("--modules", default=None, help="ED1: 씬 파일 안의 지역 모듈 번호(0부터) 지정, 기본 전부")
    a = ap.parse_args()
    global RECHECK
    RECHECK = a.recheck
    for spec in a.poke:
        ad, hx = spec.split(":")
        POKES.append((int(ad, 16), bytes.fromhex(hx)))
    configure(a.game)
    import common

    cue = a.cue or os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue")
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, cue, a.out, bkr=a.bkr)
    nav = a.state or os.path.join(H.CACHE, "beetle-saturn", f"{a.game}_field_{B.image_key(cue)}.state")
    if not os.path.exists(nav):
        (boot_to_field_ed1 if a.game == "ed1" else B.boot_to_field)(h)
        h.save(nav)
    h.load(nav)
    h.run(5)
    code, body = build_stub()
    verify_stub(code, body)
    h.poke(HOOK, code)
    for k in range(0, 0x20, 4):
        p32(h, MB + k, 0)
    h.poke(TICK, hook_patch())
    h.run(30)  # 틱이 스텁을 한 번 지나가야 한다
    assert g32(h, MB + 20) > 0, "스텁이 안 불렸다 — 틱 훅이 안 먹는다"
    base = snapshot(h)

    mm, fl = scene_files(common, cue)
    ed_targets = ed1_dispatch_targets(common.read_extent(mm, *fl["/ED.BIN"])) if a.game == "ed1" else None
    index_path = os.path.join(a.out, "index.json")
    index = json.load(open(index_path)) if os.path.exists(index_path) else []
    for sc in parse_range(a.scenes):
        name = f"/BIN/{TAG}SCN{sc:02d}.BIN"
        if name not in fl:
            print("없는 씬", name, flush=True)
            continue
        d = common.read_extent(mm, *fl[name])
        # 실험용 — 환경변수 SWEEP_PATCH='{"ED2SCN34": {"0x6ca": "08"}}' 로 씬 파일 바이트를 RAM 적재 전에 바꾼다(롬 불변)
        for off_s, hx in json.loads(os.environ.get("SWEEP_PATCH", "{}")).get(f"{TAG}SCN{sc:02d}", {}).items():
            o, bb = int(off_s, 16), bytes.fromhex(hx)
            d = d[:o] + bb + d[o + len(bb) :]
        if a.game == "ed1":
            fns = ed1_text_fns(d, ed_targets)
        else:
            fn = text_fn(d)
            fns = [fn] if fn else []
        if not fns:
            print(f"{TAG}SCN{sc:02d}: 번호→스크립트 함수를 못 찾았다 — 건너뜀", flush=True)
            continue
        sdir = os.path.join(a.out, f"{TAG}SCN{sc:02d}")
        os.makedirs(sdir, exist_ok=True)
        index = [e for e in index if e["scene"] != sc]
        nshots = nids = 0
        for mi, fn in enumerate(fns):
            if a.modules and mi not in parse_range(a.modules):
                continue
            if a.game == "ed2" and d[fn - SCN_BASE : fn - SCN_BASE + 8] == NOOP_FN:
                print(f"{TAG}SCN{sc:02d}: 번호→스크립트 함수가 빈 함수다(문안 없는 씬) — 건너뜀", flush=True)
                continue
            restore(h, base)
            h.run(1)
            h.poke(SCN_BASE, d)
            if os.environ.get("SWEEP_PATCH"):
                print("  [patch] RAM", h.peek(SCN_BASE + 0x6c0, 16).hex(), flush=True)
            if a.game == "ed1":
                h.poke(DISPATCH, hook_patch_to(fn))  # 분배기 → 이 모듈의 번호→스크립트 함수
            else:
                p32(h, PTR_TEXT, fn)
            h.run(2)
            base_scn = snapshot(h)
            nids_mod = 0
            variants = a.args.split(",") if a.args else [None]
            ids = parse_range(a.ids) if a.ids else range(a.max_id + 1)
            mtag = f"_m{mi}" if mi else ""
            for var in variants:
                if var:
                    restore(h, base_scn)
                    inject_args(h, var)
                    h.run(1)
                snap = snapshot(h)
                nbad = 0
                for i in ids:
                    if nbad >= 6 and nids_mod == 0:  # 앞 번호 여섯이 전부 안 돌아오면 이 후보는 번호→스크립트 함수가 아니다
                        print(f"  (건너뜀) m{mi} {fn:#x} — 번호 6개가 안 돌아온다(함수 후보 아님)", flush=True)
                        break
                    ok, script = read_script(h, snap, fn, i)
                    nbad = 0 if ok else nbad + 1
                    if not ok or not script or (a.game == "ed1" and not valid_script(script)):
                        if os.environ.get("SWEEP_DEBUG") and script:
                            print(f"  (거름) m{mi} id{i:03d} {script[:24].hex()}", flush=True)
                        continue
                    ent = {"scene": sc, "id": i, "script": script.hex(), "shots": [], "status": "스크립트만"}
                    if mi or a.game == "ed1":
                        ent["module"] = mi
                    if var:
                        ent["args"] = var
                    if not a.probe_only:
                        tag = f"id{i:03d}" + mtag + (f"_{var}" if var else "")
                        shots, why = play_id(h, snap, i, sdir, tag)
                        ent["shots"] = [f"{TAG}SCN{sc:02d}/{s}" for s in shots]
                        ent["status"] = why
                        ent["expected"] = expected_pages(script)
                        if why == "끝" and len(shots) != ent["expected"]:
                            ent["status"] = f"쪽 수 불일치(기대 {ent['expected']})"
                        nshots += len(shots)
                    nids += 1
                    nids_mod += 1
                    index.append(ent)
                    lab = f" [{var}]" if var else ""
                    print(
                        f"{TAG}SCN{sc:02d}{mtag} id{i:03d}{lab} 스크립트 {len(script)}B  창 {len(ent['shots'])}  {ent['status']}",
                        flush=True,
                    )
        print(f"{TAG}SCN{sc:02d}: 번호 {nids}개 · 캡처 {nshots}장", flush=True)
        index.sort(key=lambda e: (e["scene"], e.get("module", 0), e["id"], e.get("args", "")))
        json.dump(index, open(index_path, "w"), ensure_ascii=False, indent=1)
        if RECHECK:
            rp = os.path.join(a.out, "recheck.json")
            old = json.load(open(rp)) if os.path.exists(rp) else []
            json.dump(old + [list(x) for x in RECHECK_LOG], open(rp, "w"), ensure_ascii=False)
            RECHECK_LOG.clear()


if __name__ == "__main__":
    main()
