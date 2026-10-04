#!/usr/bin/env python3
"""006/012 — HUD 지명이 **고정 길이 인라인 복사**로 실려서 깨지던 것을 고친다.

🔴 **이 게임의 HUD 지명은 널종단으로 읽히지 않는다.** 씬 오버레이(ED?SCN*.BIN)의 맵
진입 코드가 지명을 HUD 버퍼(`0x8013DB18`)로 옮길 때, 컴파일러가 `strcpy` 를 **원문
리터럴 길이에 맞춰 인라인**해 놨다 — `lwl/lwr` + `swl/swr` + `lb/sb` 몇 개로 **JP 원문
길이+1 바이트를 무조건** 옮기고, 그 버퍼를 `0x8007A754` 가 통째로 그린다. JP 는 그
자리가 **반각 가타카나**(`ｲｼｭﾀ～ｱﾌﾙ` = 9B)라 널까지 딱 맞지만 우리 전각 한글은 더 길다:

  - 복사 길이보다 **한 바이트라도 길면 널이 안 실린다** → HUD 가 버퍼에 남아 있던 앞
    지명의 꼬리까지 이어 그린다.
  - 복사가 **글자 중간에서 끊기면** 2바이트 문자의 선행바이트만 남는다 → 미정의 글리프
    (012 "이슈타-아훌" 뒤 십자 — `…8fc4 94` 로 잘린다).

`patch_scn_route_labels` 독스트링의 「널종단 읽기라 우리 널 뒤는 안 읽힌다」가 바로 이
때문에 틀렸다(2026-09-20 RE 확정, 마스터 QA 006·012). **슬롯이 넉넉한지와 복사 길이가
넉넉한지는 다른 물음이다** — 슬롯은 데이터, 복사 길이는 **코드에 박혀 있다.**

고치는 방식이 둘이다(실측으로 갈린다):

**ⓐ 복사 길이 부족** — 원본이 가리키는 문자열은 맞는데 길이만 모자란다. 데이터로는 못
푼다(9바이트 = 한글 4.5자). 인라인 복사 블록을 **BIOS A(19h) strcpy** 호출로 갈아 끼워
길이 의존을 없앤다. 블록이 12~16명령이라 `jal`+`nop` 두 개로 바꾸고 나머지는 `nop` —
자리가 남으니 재배치가 없다.

**ⓑ 참조가 엉뚱한 곳을 가리킨다**(006, ED2SCN8 한 곳) — JP 는 이 HUD 참조가 **대사 블록
0 의 이름칸**(오프셋 0, `イシュタ`+널4B)을 그대로 재활용했다. 우리 재삽입이 그 블록을
확장 영역으로 옮기면서 이 참조도 같이 옮겼는데, 옮겨간 쪽은 이름칸과 본문이 한 줄로
합쳐진 번역문("이슈타 야아, 안녕하세요.")이라 9바이트 복사가 **"이슈타 야"** 를 만든다.
⇒ 원본과 같이 **오프셋 0 의 이름칸**을 가리키게 되돌린다. 그 자리는
`reinsert_kr_pilot` 의 jp0 전용 패치가 `"이슈타"`+널패딩 12B 로 유지하고 있다.

⚠ **깨진 자리만 고친다.** 347곳 중 331곳은 원본 바이트 그대로 둔다 — 무변경 구간 검사와
원본 대조를 좁게 유지한다.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import BUILD_DIR, extract, write_user_data
from patch_sys_ui import _scn_layout

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"

SCN_BASE = 0x80165000  # 씬 오버레이 적재 주소 (파일 오프셋 0 = 이 주소)
HUD_BUF = 0x8013DB18  # HUD 지명 라벨 버퍼
HUD_DRAW = 0x8007A754  # HUD 지명 그리기 — 인라인 복사 블록의 끝 표시
BIOS_STRCPY = 0x800A80A4  # A(19h) strcpy(a0, a1) 썽크 (ED2.EXE, 상주)

# HUD 칸에 들어갈 수 있는 최대 길이. 그리기 루틴이 `(0x33 − len*3) >> 1` 로 가운데를
# 잡으므로 17바이트를 넘으면 왼쪽으로 삐져나간다(원본 최장은 12B `큐베라-프로스`).
# 🔑 **이 상한이 ⓐ/ⓑ 를 가르는 장치다** — 지명이 아닌 것(합쳐진 대사문 등)을 strcpy 로
# 옮기면 HUD 에 문장이 통째로 그려지므로, 그런 자리는 여기서 걸려 ⓑ 로 넘어간다.
MAX_HUD_BYTES = 16

# ⓑ 되돌릴 참조 — {씬: 가리켜야 할 주소}. 근거는 모듈 독스트링.
REPOINT = {"ED2SCN8": SCN_BASE}
REPOINT_EXPECT = {"ED2SCN8": bytes.fromhex("90ca8f539357") + b"\x00"}  # "이슈타"+널

NOP = 0x00000000


def _jal(target):
    assert target & 3 == 0 and (target >> 28) == 0x8, f"jal 대상이 이상하다: {target:08X}"
    return 0x0C000000 | ((target >> 2) & 0x03FFFFFF)


def _lui_addiu(reg, target):
    """`lui reg,hi` + `addiu reg,reg,lo` 두 워드 — addiu 의 부호확장을 보정한다."""
    lo = target & 0xFFFF
    hi = ((target >> 16) + (1 if lo >= 0x8000 else 0)) & 0xFFFF
    return (0x3C000000 | (reg << 16) | hi, 0x24000000 | (reg << 21) | (reg << 16) | lo)


# 스토어 명령 → 그 명령이 목적지에서 "몇 바이트째까지" 건드리는가.
# `swl v0,3(a0)` + `swr v0,0(a0)` 한 쌍이 0~3 을 덮으므로 swr 만 폭 4 로 센다.
_STORE_REACH = {0x28: 1, 0x29: 2, 0x2B: 4, 0x2A: 1, 0x2E: 4}  # sb sh sw swl swr


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def _sites(buf):
    """HUD 버퍼로 복사하는 자리를 전부 찾는다."""
    lo = HUD_BUF & 0xFFFF
    out = []
    for off in range(4, len(buf) - 4, 4):
        w = _u32(buf, off)
        # addiu aX, aX, <lo(HUD_BUF)>  — 앞선 lui 로 상위까지 맞는지 확인한다
        if w >> 26 != 0x09 or (w & 0xFFFF) != lo:
            continue
        rs, rt = (w >> 21) & 31, (w >> 16) & 31
        if rs != rt:
            continue
        p = _u32(buf, off - 4)
        if p >> 26 != 0x0F or ((p >> 16) & 31) != rt:
            continue
        if ((p & 0xFFFF) << 16) + (lo - 0x10000) != HUD_BUF:
            continue
        dst = rt

        # 되짚어 src — 사이트 직전 16명령 안의 lui+addiu 쌍(목적지 레지스터 제외)
        src = src_reg = src_lui = src_addiu = None
        pend = {}
        for o2 in range(max(0, off - 0x40), off, 4):
            v = _u32(buf, o2)
            op, r_s, r_t = v >> 26, (v >> 21) & 31, (v >> 16) & 31
            if op == 0x0F:
                pend[r_t] = (v & 0xFFFF, o2)
            elif op == 0x09 and r_s == r_t and r_t in pend and r_t != dst:
                imm = v & 0xFFFF
                a = (pend[r_t][0] << 16) + (imm - 0x10000 if imm > 0x7FFF else imm)
                if SCN_BASE <= a < SCN_BASE + len(buf):
                    src, src_reg, src_lui = a, r_t, pend[r_t][1]
                    src_addiu = o2

        # 앞으로 — 첫 jal 까지가 복사 블록
        reach = 0
        end = tgt = None
        for o2 in range(off + 4, min(len(buf) - 4, off + 0x100), 4):
            v = _u32(buf, o2)
            op = v >> 26
            if op == 0x03:  # jal
                end, tgt = o2, ((v & 0x03FFFFFF) << 2) | 0x80000000
                break
            if op in _STORE_REACH and ((v >> 21) & 31) == dst:
                imm = v & 0xFFFF
                imm -= 0x10000 if imm > 0x7FFF else 0
                reach = max(reach, imm + _STORE_REACH[op])
        if end is None or src is None:
            continue
        out.append(
            {
                "off": off,
                "src": src,
                "src_reg": src_reg,
                "src_lui": src_lui,
                "src_addiu": src_addiu,
                "len": reach,
                "end": end,
                "jal": tgt,
            }
        )
    return out


def _strlen(buf, o, cap=64):
    e = buf.find(b"\x00", o, o + cap)
    return (e - o) if e >= 0 else cap


def _scan(buf):
    """(고쳐야 할 자리, 이미 strcpy 로 바뀐 자리 수, 멀쩡한 자리 수)."""
    broken, converted, ok = [], 0, 0
    for s in _sites(buf):
        if s["jal"] == BIOS_STRCPY:
            converted += 1
            continue
        if s["jal"] != HUD_DRAW:
            continue
        s["need"] = _strlen(buf, s["src"] - SCN_BASE) + 1
        if s["need"] > s["len"]:
            broken.append(s)
        else:
            ok += 1
    return broken, converted, ok


def apply():
    jal_strcpy = _jal(BIOS_STRCPY)
    total_a = total_b = 0
    for name, lba, size in _scn_layout():
        buf = bytearray(extract(lba, size, path=IMG))
        broken, _, _ = _scan(bytes(buf))
        if not broken:
            continue
        for s in broken:
            if s["need"] > MAX_HUD_BYTES:
                # ⓑ — 지명이 아닌 것을 가리키고 있다. 되돌릴 자리를 알아야만 고친다.
                tgt = REPOINT.get(name)
                assert tgt is not None, (
                    f"{name}@0x{s['off']:X} src=0x{s['src']:08X} 가 {s['need']}B 짜리를 가리킨다"
                    f" — HUD 지명이 아니다. 되돌릴 주소를 REPOINT 에 적기 전엔 못 고친다"
                )
                exp = REPOINT_EXPECT[name]
                got = bytes(buf[tgt - SCN_BASE : tgt - SCN_BASE + len(exp)])
                assert got == exp, f"{name} 되돌릴 자리 0x{tgt:08X} 내용 불일치: {got.hex()}"
                w0, w1 = _lui_addiu(s["src_reg"], tgt)
                struct.pack_into("<I", buf, s["src_lui"], w0)
                struct.pack_into("<I", buf, s["src_addiu"], w1)
                print(
                    f"    ⓑ {name} 0x{s['off']:06X}  참조 0x{s['src']:08X}({s['need']}B)"
                    f" → 0x{tgt:08X}(이름칸)"
                )
                total_b += 1
                continue
            # ⓐ — 인라인 복사 블록을 strcpy 호출로
            a, b = s["off"] + 4, s["end"]
            assert b - a >= 8, f"{name}@0x{a:X} 복사 블록이 {b - a}B 뿐 — jal+nop 자리가 없다"
            struct.pack_into("<I", buf, a, jal_strcpy)
            for o in range(a + 4, b, 4):
                struct.pack_into("<I", buf, o, NOP)
            print(
                f"    ⓐ {name} 0x{s['off']:06X}  src=0x{s['src']:08X}"
                f"  복사 {s['len']}B < 필요 {s['need']}B → strcpy ({b - a}B 블록)"
            )
            total_a += 1
        with open(IMG, "r+b") as f:
            write_user_data(f, lba, bytes(buf), label=f"{name} 006/012 HUD 지명 복사")

        # 되읽기 검산 — 손인코딩 규율(낱말 단위로 되짚는다)
        buf2 = extract(lba, size, path=IMG)
        again, _, _ = _scan(buf2)
        assert not again, f"{name} 되읽기 — 아직 {len(again)}곳이 위험: " + ", ".join(
            f"0x{x['off']:X}({x['len']}<{x['need']})" for x in again
        )
        for s in broken:
            if s["need"] > MAX_HUD_BYTES:
                assert _u32(buf2, s["src_lui"]) >> 26 == 0x0F, f"{name} lui 검산 실패"
                assert _u32(buf2, s["src_addiu"]) >> 26 == 0x09, f"{name} addiu 검산 실패"
                continue
            a, b = s["off"] + 4, s["end"]
            w = _u32(buf2, a)
            assert w >> 26 == 0x03 and ((w & 0x03FFFFFF) << 2) | 0x80000000 == BIOS_STRCPY, (
                f"{name}@0x{a:X} jal 인코딩 검산 실패: {w:08X}"
            )
            assert all(_u32(buf2, o) == NOP for o in range(a + 4, b, 4)), (
                f"{name}@0x{a:X} 잔여 명령이 nop 이 아니다"
            )
    print(f"  006/012 HUD 지명 — 고정길이 복사 → strcpy {total_a}곳, 참조 되돌림 {total_b}곳")
    return total_a + total_b


def report():
    """게이트용 — 남은 위험 자리를 센다(고치지 않는다)."""
    bad = []
    for name, lba, size in _scn_layout():
        buf = extract(lba, size, path=IMG)
        broken, conv, ok = _scan(buf)
        if broken or conv:
            print(f"  {name}: 정상 {ok} · strcpy {conv} · 위험 {len(broken)}")
        bad += [(name, s) for s in broken]
    return bad


if __name__ == "__main__":
    sys.exit(0 if apply() is not None else 1)  # 고칠 게 0곳인 것도 정상이다(멱등)
