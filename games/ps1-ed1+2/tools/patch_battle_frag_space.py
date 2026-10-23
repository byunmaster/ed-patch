#!/usr/bin/env python3
"""수치 뒤에 붙는 전투 문장 조각의 앞 공백 — **수치 자리에서만** 띄우고 수치 없는 자리는 공백 없이 가리킨다(10-20, qa e109_21).

**증상.** ED1 「소니아의 ＭＰ가 50회복되었다.」 — 수치 뒤 공백 누락(같은 시트 「ＨＰ가 1000 회복되었다」는 한 문자열이라 공백이 든다).
**원인.** 문구가 `sprintf("%c%d%c")`(수치) → `strcat(조각)` 으로 **조각 문자열을 따로 붙인다**. 조각 「회복되었다.\\n」·
「내려가고 말았다!!\\n」은 원문이 수치 바로 뒤에 붙는 말이라 공백이 없다(정본도 조각은 공백 없음 — 공백은 합친 꼴 `{n} 회복되었다.` 에만 있다).
**고침.** 조각 문자열을 `textmap/battle.json` 에서 **앞 공백이 든 꼴**(` 회복되었다.\\n`)로 두면 수치 자리가 띄워진다. 그런데 그 조각을
**수치 없이** 붙이는 자리(ED2.EXE 「의 ＭＰ가 」 뒤 — 「의 ＭＰ가 회복되었다.」)가 있어 거기선 공백이 겹친다. 그래서 이 패치가
**수치 없는 참조만 `addiu` 의 하위 16비트 +1 로 공백 뒤를 가리키게** 한다(문자열 복제·이동 없이 명령 한 개).

⚠ 수치 판정 = 참조 앞 0x200B 안에 `%d`·`%c%d%c` 서식 참조가 있는가. 개수가 기대와 다르면(코드·문안이 바뀜) 실패한다(`EXPECT`).
  이 패치는 patch_items·patch_ed2_battle(문자열 재배치) **뒤**에 돈다 — 조각의 최종 주소를 읽는다.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map as H
from common import MIPS_ADDIU, MIPS_ORI, extract, iter_lui_pairs, write_user_data
from patch_ed2_monster_lines import IMG

EXES = {"ED.EXE": (257, 1021952), "ED2.EXE": (756, 872448)}  # (LBA, 크기)
EXE_RAM_BASE, EXE_HDR = 0x80010000, 0x800
FRAGS = (" 회복되었다.\n", " 내려가고 말았다!!\n")
NUMFMT = (b"%d", b"%c%d%c")
WINDOW = 0x200
# 수치 없이 조각만 붙이는 참조 수(코드 자리). ED1 은 모든 참조가 수치 뒤라 0.
EXPECT = {"ED.EXE": 0, "ED2.EXE": 1}


def enc(s):
    out = b""
    for c in s:
        out += H.syllable_sjis(c).to_bytes(2, "big") if "가" <= c <= "힣" else c.encode("ascii")
    return out


def fo_of(addr):
    return addr - EXE_RAM_BASE + EXE_HDR


def cstr(buf, fo):
    if not 0 <= fo < len(buf):
        return None
    j = buf.find(b"\x00", fo)
    return bytes(buf[fo:j]) if j >= 0 else None


def sites(buf):
    """[(addiu 오프셋, lui 오프셋, 목표 RAM 주소, 문자열)] — 조각을 가리키는 참조 중 **수치 없는** 것만."""
    refs = {}
    for imm, lui, op, addr in iter_lui_pairs(bytes(buf), {MIPS_ADDIU, MIPS_ORI}):
        s = cstr(buf, fo_of(addr))
        if s is not None:
            refs[imm] = (lui, addr, s)
    pos = sorted(refs)
    targets = {enc(f) for f in FRAGS}
    out = []
    for i, p in enumerate(pos):
        lui, addr, s = refs[p]
        if s not in targets or addr == 0:
            continue
        before = [refs[q][2] for q in pos[:i] if p - WINDOW <= q < p]
        if not any(b in NUMFMT for b in before):
            out.append((p, lui, addr, s))
    return out


def main():
    plan = {}
    for exe, (lba, size) in EXES.items():
        buf = bytearray(extract(lba, size, path=IMG))
        ss = sites(buf)
        if len(ss) != EXPECT[exe]:
            raise SystemExit(f"{exe}: 수치 없는 조각 참조 {len(ss)}곳 — 기대 {EXPECT[exe]}곳(코드·문안이 바뀌었다, 다시 본다)")
        for p, lui, addr, _s in ss:
            hi = struct.unpack_from("<I", buf, lui)[0] & 0xFFFF
            lo = (addr + 1) - (hi << 16)
            assert -0x8000 <= lo <= 0x7FFF, f"{exe} {p:#x}: 하위 16비트 범위 밖"
            w = struct.unpack_from("<I", buf, p)[0]
            struct.pack_into("<I", buf, p, (w & 0xFFFF0000) | (lo & 0xFFFF))
        if ss:
            plan[exe] = (lba, size, buf, len(ss))
    with open(IMG, "r+b") as f:
        for exe, (lba, size, buf, n) in plan.items():
            write_user_data(f, lba, bytes(buf), label=f"{exe} 수치 없는 조각 참조 공백 뒤로 ({n}곳)")
    print(f"전투 문장 조각 앞 공백: 수치 없는 참조 {sum(v[3] for v in plan.values())}곳을 공백 뒤로")
    return 0


if __name__ == "__main__":
    sys.exit(main())
