#!/usr/bin/env python3
"""QA 디버그 빌드(`ED_DEBUG_QA=1`) — 마스터 11-18 「제품판에 넣기보단 내 QA 용으로… 괜찮으면 기능으로 추가」.

🔴 **제품 롬은 바이트 불변이다** — 이 모듈은 `ED_DEBUG_QA=1` 이 아니면 아무것도 안 쓴다(`apply()` 첫 줄).
꼬리표는 `ED_BUILD_TAG=qa-debug`(test- 가 아니다 — 마스터 파일서버 목록에 보여야 한다).

원판엔 디버그 메뉴·진입키가 없다(`ed1-status` 「숨은 기능 조사」, 10-16 전수) — 그래서 **원판이 안 읽는 버튼**
(Select·L1·R1·L2·R2·△·□)을 쓴다. 필드 패드 읽기(ED1 `0x800ABFCC` 가 `PadRead(0x800C1C4C)` 를 부른 직후)에 훅을 걸어,
원시 패드 워드(libpad 비트: Select `0x100` · L1 `0x4` · R1 `0x8` · L2 `0x1` · R2 `0x2` · △ `0x10` · ○ `0x20` · × `0x40` · □ `0x80` ·
Start `0x800`)를 본다. **Select 를 누른 채** 다른 버튼을 새로 누르면 기능이 한 번 돈다(엣지 검출 — 직전 워드를 스텁 옆 4B 에 둔다).

코드 자리: 조사 훅이 쓰는 것과 같은 부류 — **VAB 사운드 뱅크 헤더의 미사용 0 패딩**(`patch_josa_hook` 머리 주석 참조).
조사 훅이 쓴 둘 말고 다른 0 런을 쓴다. 쓰기 전에 ① 자리가 전부 0 ② `vab.safe_len` 한계 안 을 단언한다.

기능(이번 판): Select+□ = 소지품 첫 빈칸에 아이템 번호를 1부터 하나씩 늘려 가며 넣기 · Select+R1 = 돈 +100,000(상한 9,999,999) · Select+○ = 이동 속도 토글(3↔1, 2배) · Select+L1 = 파티 경험치 +100,000(상한 0xFFFFFF, 필드에서만 —
전투 중엔 사본 A 가 따로라 의미 없다. 레벨은 다음 전투 승리 때 원판 보상 루틴이 올린다).
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from patch_josa_hook import REG, Asm, _i, _r  # noqa: E402

# ── ED1(ED.EXE) 좌표 — 전부 에뮬 실측으로 대조(11-18: 골드 5,450,835 화면 = RAM 0x801086B8) ──
ED1 = {
    "lba": 257,
    "size": 1021952,
    "hook": 0x800ABFF0,  # move v1,v0 / andi v0,v1,0x8000 — PadRead(0x800C1C4C) 직후
    "hook_orig": (0x00401821, 0x30628000),
    "resume": 0x800ABFF8,  # beqz v0 … (andi 는 스텁이 대신 실행)
    "gold": 0x801086B8,
    "mode": 0x80108A68,  # 1 = 전투
    "party": 0x80115758,  # 영구 파티 배열 B, 0x6C × 4
    "inv": 0x80112B98,  # 소지품 28칸(바이트, 0=빈칸, 앞으로 당겨 채움 — 삭제 함수 0x80082850 이 `[inv+i]→[inv+i-1]` 28회)
    "item_max": 0x74,  # 세이브에서 관측한 최대 번호(눈 달린 신발) — 그 너머는 미확인이라 안 넘는다
    "cave": 0x800D231C,  # VAB 헤더 0 패딩(조사 훅 자리 아님)
    "speed": 0x80108ADE,  # u16 — 필드 메인루프가 프레임마다 패드 읽기·이동을 되풀이하는 횟수(기본 3). 작을수록 빠르다(1 = 2배, 0 = 4배쯤)
}
# ── ED2(ED2.EXE) — 같은 필드 패드 읽기 함수(PadRead 0x8009D640), 에뮬로 돈·소지품·파티 대조(11-18, 화면 949,018 = RAM 0x800E4134) ──
ED2 = {
    "lba": 756,
    "size": 872448,
    "hook": 0x80082704,  # move v1,v0 / andi v0,v1,0x8000 — PadRead 직후(ED1 과 같은 두 명령)
    "hook_orig": (0x00401821, 0x30628000),
    "resume": 0x8008270C,
    "gold": 0x800E4134,
    "mode": 0x800E43A0,  # 1 = 전투 (이벤트 전투 핸들러 0x80074DCC 가 1 을 쓴다)
    "party": 0x800F0FE8,
    "inv": 0x800EE3D8,  # 소지품 28칸(에뮬: 첫 칸에 1 을 쓰니 목록 맨 위가 나이프로 바뀜)
    "item_max": 0x52,  # 세이브에서 관측한 최대 번호 — 그 너머는 미확인
    "speed": 0x800E440C,  # ED1 과 같은 필드 메인루프(0x8002A770 의 lhu)
    "cave": 0,
}

STRIDE, EXP_OFF = 0x6C, 0x1C
GOLD_CAP, EXP_CAP, STEP = 9999999, 0xFFFFFF, 100000
INV_SLOTS, ITEM_MAX = (
    28,
    0x74,
)  # 0x74 = 세이브에서 관측한 최대 번호(눈 달린 신발) — 그 너머는 미확인이라 안 넘는다


def hi(a):
    return ((a + 0x8000) >> 16) & 0xFFFF


def lo(a):
    v = a & 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def _lw(a, rt, off, base):
    a.emit(_i(0x23, REG[base], REG[rt], off & 0xFFFF))


def _sw(a, rt, off, base):
    a.emit(_i(0x2B, REG[base], REG[rt], off & 0xFFFF))


def _r3(a, fn, rd, rs, rt):
    a.emit(_r(0, REG[rs], REG[rt], REG[rd], 0, fn))


def _li32(a, rt, v):
    a.lui(rt, (v >> 16) & 0xFFFF)
    a.ori(rt, rt, v & 0xFFFF)


def _add_capped(a, tag, addr, step, cap):
    """[addr] += step, cap 초과면 cap — 명령 17개. t6/t7/t8/t9 사용."""
    a.lui("t6", hi(addr))
    _lw(a, "t7", lo(addr), "t6")
    a.emit(0)  # 로드 지연
    _li32(a, "t8", step)
    _r3(a, 0x21, "t7", "t7", "t8")  # addu
    _li32(a, "t9", cap)
    _r3(a, 0x2B, "t8", "t9", "t7")  # sltu t8 = (cap < t7)
    a.branch(0x04, "t8", "zero", tag + "_s")  # beq t8,zero → 넘치지 않음
    a.emit(0)
    a.emit(_r(0, REG["t9"], 0, REG["t7"], 0, 0x21))  # move t7,t9 (addu t7,t9,zero)
    a.label(tag + "_s")
    _sw(a, "t7", lo(addr), "t6")


def _asm(st, base, sa):
    a = Asm(base)
    a.emit(st["hook_orig"][0])  # move v1,v0
    a.lui("t0", hi(sa))
    _lw(a, "t1", lo(sa), "t0")
    a.emit(0)
    _sw(a, "v1", lo(sa), "t0")
    a.emit(_i(0x0C, REG["v1"], REG["t2"], 0x100))  # andi t2,v1,0x100 (Select 눌림)
    a.branch(0x04, "t2", "zero", "exit")
    a.emit(0)
    _r3(a, 0x26, "t3", "t1", "v1")  # xor  t3 = 직전 ^ 지금
    _r3(a, 0x24, "t3", "t3", "v1")  # and  t3 = 새로 눌린 비트
    a.lui("t4", hi(st["mode"]))
    _lw(a, "t4", lo(st["mode"]), "t4")
    a.emit(0)
    a.addiu("t5", "zero", 1)
    a.branch(0x04, "t4", "t5", "exit")  # 전투 중엔 건너뜀
    a.emit(0)
    a.emit(_i(0x0C, REG["t3"], REG["t2"], 0x08))  # Select+R1 → 돈
    a.branch(0x04, "t2", "zero", "l1")
    a.emit(0)
    _add_capped(a, "gold", st["gold"], STEP, GOLD_CAP)
    a.label("l1")
    a.emit(_i(0x0C, REG["t3"], REG["t2"], 0x04))  # Select+L1 → 파티 경험치 4명
    a.branch(0x04, "t2", "zero", "sq")
    a.emit(0)
    # 4명 루프(코드 크기 — 펼치면 VAB 빈 슬롯 한계를 넘는다)
    a.lui("t6", hi(st["party"] + EXP_OFF))
    a.addiu("t6", "t6", lo(st["party"] + EXP_OFF))
    a.addiu("t0", "zero", 4)
    a.label("eloop")
    _lw(a, "t7", 0, "t6")
    a.emit(0)
    _li32(a, "t8", STEP)
    _r3(a, 0x21, "t7", "t7", "t8")
    _li32(a, "t9", EXP_CAP)
    _r3(a, 0x2B, "t8", "t9", "t7")
    a.branch(0x04, "t8", "zero", "es")
    a.emit(0)
    a.emit(_r(0, REG["t9"], 0, REG["t7"], 0, 0x21))
    a.label("es")
    _sw(a, "t7", 0, "t6")
    a.addiu("t6", "t6", STRIDE)
    a.addiu("t0", "t0", -1)
    a.branch(0x05, "t0", "zero", "eloop")
    a.emit(0)
    a.label("sq")
    # Select+□ → 소지품 첫 빈칸에 다음 아이템 번호(1..ITEM_MAX 순환, 카운터 = 상태 워드 +4). 28칸이 차면 번호만 넘어간다.
    a.emit(_i(0x0C, REG["t3"], REG["t2"], 0x80))
    a.branch(0x04, "t2", "zero", "sp")
    a.emit(0)
    a.lui("t6", hi(sa))
    _lw(a, "t7", lo(sa + 4), "t6")
    a.emit(0)
    a.addiu("t7", "t7", 1)
    a.sltiu("t8", "t7", st["item_max"] + 1)
    a.branch(0x05, "t8", "zero", "iok")  # bne
    a.emit(0)
    a.addiu("t7", "zero", 1)
    a.label("iok")
    _sw(a, "t7", lo(sa + 4), "t6")
    a.lui("t6", hi(st["inv"]))
    a.addiu("t6", "t6", lo(st["inv"]))
    a.addiu("t8", "zero", INV_SLOTS)
    a.label("iloop")
    a.lbu("t9", 0, "t6")
    a.emit(0)
    a.branch(0x04, "t9", "zero", "iput")
    a.emit(0)
    a.addiu("t6", "t6", 1)
    a.addiu("t8", "t8", -1)
    a.branch(0x05, "t8", "zero", "iloop")
    a.emit(0)
    a.branch(0x04, "zero", "zero", "exit")
    a.emit(0)
    a.label("iput")
    a.sb("t7", 0, "t6")
    a.branch(0x04, "zero", "zero", "exit")
    a.emit(0)
    a.label("sp")
    # Select+○ → 이동 속도 토글(필드 루프 반복 횟수 u16: 3 ↔ 1). 이미 1 이면 3 으로, 아니면 1 로.
    a.emit(_i(0x0C, REG["t3"], REG["t2"], 0x20))
    a.branch(0x04, "t2", "zero", "exit")
    a.emit(0)
    a.lui("t6", hi(st["speed"]))
    a.emit(_i(0x25, REG["t6"], REG["t7"], lo(st["speed"]) & 0xFFFF))  # lhu t7
    a.emit(0)
    a.addiu("t8", "zero", 1)
    a.branch(0x05, "t7", "t8", "sp1")  # bne t7,1 → 1 로
    a.emit(0)
    a.addiu("t8", "zero", 3)
    a.label("sp1")
    a.emit(_i(0x29, REG["t6"], REG["t8"], lo(st["speed"]) & 0xFFFF))  # sh t8
    a.label("exit")
    a.emit(st["hook_orig"][1])  # andi v0,v1,0x8000
    a.emit(0x08000000 | ((st["resume"] >> 2) & 0x03FFFFFF))  # j resume
    a.emit(0)
    return a.resolve()


def build_stub(st, base):
    """(코드+상태 워드 바이트, 상태 워드 주소). 코드 바로 뒤 8B = 상태(+0 직전 패드, +4 아이템 카운터)."""
    n = len(_asm(st, base, base))
    code = _asm(st, base, base + n)
    assert len(code) == n
    return code + b"\0" * 8, base + n


def _in_unused_vag_slots(ed, co, need, vab):
    """[co, co+need) 가 그 뱅크의 **VAG 오프셋 표 중 안 쓰는 슬롯**(사용 항목 `(vs+1)·2`B 뒤 ~ 파형 시작 앞)에 드는가.

    「0 런 + 파형 직전 한계」만으로는 **쓰는 톤·프로그램 속성의 0 필드**를 덮을 수 있다(관리자 11-18 — free-space-vab-trap).
    VAB 헤더는 프로그램 128×16 · 톤 512×ps · VAG 표 512B 순이고, 표의 쓰는 항목 뒤는 라이브러리가 안 읽는 빈 슬롯이다.
    """
    import struct

    for b_off, fsize, nprog, wav in vab.banks(ed):
        if b_off <= co < b_off + fsize:
            vs = struct.unpack_from("<H", ed, b_off + 22)[0]
            vag_tab = b_off + vab.HDR_FIXED + vab.TONE_ATTR * nprog
            return vag_tab + 2 * (vs + 1) <= co and co + need <= wav
    return False


def pick_cave(ed, need, vab):
    """현재 이미지에서 **아직 전부 0** 이고 VAB 파형 직전 한계 안인 0 런의 시작 주소(첫 번째). 다른 패치가 쓴 자리는 건너뛴다."""
    import re

    body = bytes(ed[0x800:])
    for m in re.finditer(rb"\x00{%d,}" % (need + 16), body):
        co = 0x800 + m.start()
        co += (-co) % 4  # 4B 정렬
        safe = vab.safe_len(ed, co)
        if (
            safe is not None
            and safe >= need
            and not any(ed[co : co + need])
            and _in_unused_vag_slots(ed, co, need, vab)
        ):
            return co - 0x800 + 0x80010000
    raise SystemExit("  ❌ QA 디버그 코드를 둘 0 런이 없다")


def apply():
    """빌드 체인 끝(조사 훅 뒤)에서 부른다. ED_DEBUG_QA=1 이 아니면 아무것도 안 한다."""
    if os.environ.get("ED_DEBUG_QA") != "1":
        return 0
    from common import BUILD_DIR, extract, write_user_data

    import vab

    img = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
    off = lambda addr: addr - 0x80010000 + 0x800  # noqa: E731
    total = 0
    for name, st in (("ED1", ED1), ("ED2", ED2)):
        ed = bytearray(extract(st["lba"], st["size"], path=img))
        need = len(build_stub(st, 0x80100000)[0])
        cave = pick_cave(ed, need, vab)
        code, _state_addr = build_stub(st, cave)
        st = {**st, "cave": cave}
        co = off(cave)
        safe = vab.safe_len(ed, co)
        assert safe is not None and len(code) <= safe, f"QA 디버그 코드 {len(code)}B 가 자리 한계 {safe} 를 넘는다"
        assert not any(ed[co : co + len(code)]), "QA 디버그 자리가 0 이 아니다(다른 패치와 겹침?)"
        ho = off(st["hook"])
        assert struct.unpack_from("<II", ed, ho) == st["hook_orig"], f"QA 디버그 훅 자리 원명령 불일치({name})"
        ed[co : co + len(code)] = code
        ed[ho : ho + 8] = struct.pack("<II", 0x08000000 | ((st["cave"] >> 2) & 0x03FFFFFF), 0)
        with open(img, "r+b") as f:
            n = write_user_data(f, st["lba"], bytes(ed), label=f"QA 디버그 훅({name})")
        print(f"QA 디버그 [{name}]: 코드 {len(code)}B @0x{st['cave']:08X} (한계 {safe}B), 훅 0x{st['hook']:08X}, 섹터 {n}개")
        total += n
    n = total
    return n


if __name__ == "__main__":
    sys.exit(0 if apply() is not None else 1)
