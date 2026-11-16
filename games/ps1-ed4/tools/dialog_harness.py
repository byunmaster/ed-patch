"""ED4 대사 주입 하네스 — 맵으로 워프하고 **굽은 이미지의 대사 멤버**를 RAM 에 올려 엔진의 대사 루틴으로 그리게 해 게임이 그린 화면을 찍는다.

원리(10-26 중단점 실측, `docs/debug.md` 「대사 주입」):
  · 워프 — 타이틀에서 「처음부터」 전에 새 게임 맵 이름 리터럴(`OP00000`, RAM `0x80088890`)을 다른 맵 이름 7자로 덮는다. 롬을 안 굽는다.
  · 이벤트 VM 의 PC 는 전역 `0x800C65E8` — `0F`(대사) 연산을 읽고 `0x8003C98C(ctx, 스트림 포인터)` 를 부른다. 문자열 표 주소는 전역 `0x800B3014`(표 시작).
  · 그래서 멤버 바이트를 빈 RAM(`BUF`)에 올리고 `0x800B3014 = BUF + 머리 u16`, `0x800C65E8 = BUF + 스트림 시작` 으로 꽂고 2프레임 뒤 PC 만 복구한다(대사 함수는 제 포인터로 계속 돈다).
🔴 이름창 개체(`12 NN`)·변수 삽입 값은 현재 맵 상태를 따라가므로 이름은 그 맵 것이 나올 수 있다 — 줄·쪽 조판 확인용이다.
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(HERE, "..", "..", "ps1-ed3", "tools"))
import common
import headless_ps1 as H
import typeset

from shared.ps1 import gmf_arc

import ctypes as _C

_orig_env = H.Emu._env


def _env_drc_off(self, cmd, data):
    """🔴 동적 재컴파일러(JIT)는 RAM 에 꽂은 바이트·불러온 상태와 어긋나 죽는다 — 코어 옵션 `pcsx_rearmed_drc=disabled`(인터프리터)로 돌린다."""
    if (cmd & 0xFFFF) == 15:
        v = _C.cast(data, _C.POINTER(H.Var))[0]
        if v.key == b"pcsx_rearmed_drc":
            p = _C.c_char_p(b"disabled")
            self._keep.append(p)
            _C.cast(data, _C.POINTER(H.Var))[0].value = p
            return True
    return _orig_env(self, cmd, data)


H.Emu._env = _env_drc_off

LITERAL = 0x80088890
PC = 0x800C65E8
TABLE = 0x800B3014
BUF = 0x801B0000


def read_member(bin_path, archive, member):
    """굽은 이미지에서 멤버 바이트. `archive` = `A_SC000.DAT`, `member` = `..\\BIN\\AT02000.BIN`."""
    with common.open_disc(bin_path) as d:
        for path, lba, size in d.files():
            if path == archive or path.strip("/").replace("/", "_") == archive:
                data = d.read_extent(lba, size)
                _, ents = gmf_arc.arc_parse(data)
                for nm, off, sz in ents:
                    if nm == member:
                        return data[off : off + sz]
    raise KeyError((archive, member))


def boot_map(cue, card, name, settle=600):
    """새 게임을 `name` 맵으로 시작한다(리터럴 덮어쓰기)."""
    tmp = "/tmp/claude-0/card_dh.mcr"
    shutil.copy(card, tmp)
    e = H.Emu(cue, card=tmp)
    for _ in range(14):
        e.press("circle", 8, 82)
    e.run(300)
    e.press("cross", 8, 40)
    e.press("up", 8, 30)
    e.poke(LITERAL, name.encode("ascii") + b"\x00")
    e.press("circle", 8, 60)
    e.run(settle)
    return e


def inject(e, member, p0):
    """멤버를 `BUF` 에 올리고 스트림(`p0` 오프셋)을 한 번 돌린다. 반환 = 옛 (PC, 표)."""
    import struct

    base = struct.unpack_from("<H", member, 0)[0]
    e.poke(BUF, member + b"\x00\x00")
    old_pc, old_tbl = e.u32(PC), e.u32(TABLE)
    e.poke(TABLE, (BUF + base).to_bytes(4, "little"))
    e.poke(PC, (BUF + p0).to_bytes(4, "little"))
    e.run(2)
    e.poke(PC, old_pc.to_bytes(4, "little"))
    return old_pc, old_tbl


def streams(member):
    return typeset.message_streams(member)


# ── 대사 스트림 주입(전수 촬영) ───────────────────────────────────────────────────────────────────────────────────────
# 🔴 위 `inject`(PC 전역을 꽂는 방식)는 필드에서 안 먹는다 — VM 이 이벤트 중에만 돈다. 그래서 **새 게임 첫 대사(오레시아 「자, 어빈, 아이멜.」)가 입력을 기다리는 순간**의
# 상태를 한 번 만들어 두고, 그 대사 함수(`0x8003C98C`)의 **지역 변수(스트림 포인터, 스택 `0x801FFF44`)** 와 표 전역을 우리 멤버로 바꾼 뒤 ○ 를 누른다 — 함수가 제 포인터로 계속 읽는다(실측: 레뮤라스 대사가 떴다).
STACK_PTR = 0x801FFF44
WIN_TOP = (100, 160, (238, 170, 98))
WIN_IN = (100, 162, (16, 56, 32))


def make_state(cue, card, path):
    tmp = "/tmp/claude-0/card_dh_state.mcr"
    shutil.copy(card, tmp)
    e = H.Emu(cue, card=tmp)
    for _ in range(14):
        e.press("circle", 8, 82)
    e.run(300)
    e.press("cross", 8, 40)
    e.press("up", 8, 30)
    e.press("circle", 8, 600)
    e.save(path)
    return e


def window_open(e):
    f = e.frame
    return tuple(f[WIN_TOP[1], WIN_TOP[0]]) == WIN_TOP[2] and tuple(f[WIN_IN[1], WIN_IN[0]]) == WIN_IN[2]


def stream_start(member, st):
    """주입 시작 자리 — **첫 출력 연산 바이트**(`0F`). 🔴 `p0`(스트림 머리)에서 시작하면 앞의 연산·직전 출력이 먼저 돌아 엉뚱한 쪽(직전 대사·열린 대사의 같은 번호 조각)이 먼저 뜬다(10-30 실측 — `12 03` 뒤 스트림이 첫 쪽에 남의 글을 그렸다)."""
    q = st["prints"][0][0]
    return q - 1 if member[q - 1] == 0x0F else q - 2


def play_stream(e, state_path, member, st, max_pages, out_prefix, wait=220):
    """상태를 불러 멤버·포인터를 꽂고 ○ 로 쪽을 넘기며 찍는다. 반환 = 찍은 파일 목록."""
    import struct

    e.load(state_path)
    e.run(1)
    base = struct.unpack_from("<H", member, 0)[0]
    e.poke(BUF, member + b"\x00\x00")
    e.poke(TABLE, (BUF + base).to_bytes(4, "little"))
    e.poke(STACK_PTR, (BUF + stream_start(member, st)).to_bytes(4, "little"))
    shots = []
    e.press("circle", 6, 6)  # 첫 대사(오레시아)를 닫는다 → 우리 스트림의 첫 쪽
    for k in range(max_pages):
        e.run(wait)
        if not window_open(e):
            break
        p = f"{out_prefix}_{k:02d}.png"
        e.shot(p)
        if shots and open(shots[-1], "rb").read() == open(p, "rb").read():
            os.remove(p)  # 같은 화면 — 스트림이 끝났다(○ 가 더는 쪽을 안 넘긴다)
            break
        shots.append(p)
        e.press("circle", 6, 6)
    return shots
