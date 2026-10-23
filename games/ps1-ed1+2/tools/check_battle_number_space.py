#!/usr/bin/env python3
"""전투 문구 조립의 공백 — 최종 이미지 방출 바이트에서 **수치 뒤 한글 낱말 붙음**과 **공백 이중**을 센다(10-20, qa e109_21·e106_09).

문구는 `sprintf`(서식) → `strcat`(조각) 으로 이어 붙는다. 조립은 참조(`lui`+`addiu`) 순서로 읽는다.
  ① 수치 서식(`%d`·`%c%d%c`) 바로 다음 조각이 **한글로 시작**하면 붙음 — 조사(`의 피해`·`이나`)·단위(`포인트`·`Gold`)가 아닌 낱말이면
     「ＭＰ가 50회복되었다」 꼴이다. 조각이 공백으로 시작해야 한다.
  ② 앞 조각이 공백으로 끝나는데 다음 조각도 공백으로 시작하면 「는  어둠 속에」 꼴 이중 공백이다(공백뿐인 칸은 제외).
허용 시작(`ALLOWED_START`)은 조사·단위뿐이다 — 새 낱말이 오면 실패하고 사람이 본다.

  python3 tools/check_battle_number_space.py [--allow-stale]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map as H
import patch_battle_frag_space as F
from common import MIPS_ADDIU, MIPS_ORI, extract, iter_lui_pairs

NUMFMT = (b"%d", b"%c%d%c")
WINDOW = 0x100
REV = {H.syllable_sjis(c).to_bytes(2, "big"): c for c in H.SYL_INDEX}
# 수치 바로 뒤에 붙어도 되는 시작 — 조사·단위(정본 규칙 1-5: 숫자+단위 붙임). 새 낱말은 사람이 본다.
ALLOWED_START = ("의 ", "이나", "포인트", "Gold")


def first_text(s):
    """조각의 앞부분을 한글 평문으로."""
    out, i = [], 0
    while i < len(s) and len(out) < 8:
        x = s[i : i + 2]
        if x in REV:
            out.append(REV[x])
            i += 2
        elif s[i] < 0x80:
            out.append(chr(s[i]))
            i += 1
        else:
            out.append("?")
            i += 2
    return "".join(out)


def audit(buf, fo_of=F.fo_of):
    """[(종류, 위치(imm), 앞 조각, 뒤 조각)] — 비어 있어야 통과."""
    refs = {}
    for imm, _lui, _op, addr in iter_lui_pairs(bytes(buf), {MIPS_ADDIU, MIPS_ORI}):
        s = F.cstr(buf, fo_of(addr))
        if s is not None:
            refs[imm] = s
    pos = sorted(refs)
    bad = []
    for i, p in enumerate(pos):
        s1 = refs[p]
        nxt = next((q for q in pos[i + 1 :] if q - p <= WINDOW), None)
        if nxt is None:
            continue
        s2 = refs[nxt]
        if s1 in NUMFMT and s2 and 0x81 <= s2[0] <= 0xFC:
            t = first_text(s2)
            if not t.startswith(ALLOWED_START):
                bad.append(("수치 뒤 붙음", nxt, first_text(s1), t))
        if s1.endswith(b" ") and s2.startswith(b" ") and s1.strip() and s2.strip():
            bad.append(("공백 이중", nxt, first_text(s1[-4:]), first_text(s2)))
    return bad


def main(argv):
    import check_pointer_audit as PA

    img = PA.image_path()
    why = PA.stale_reason(img, "--allow-stale" in argv)
    if why:
        print(f"  ❌ 안 쟀다 — {why}")
        return 1
    n = 0
    for exe, (lba, size) in F.EXES.items():
        buf = bytes(extract(lba, size, path=img))
        for kind, p, a, b in audit(buf):
            n += 1
            print(f"  ❌ {exe} {p - F.EXE_HDR + F.EXE_RAM_BASE:#x} {kind}: 「{a}」→「{b}」")
    if n:
        print(f"  ❌ 전투 문구 조립 공백 {n}곳")
        return 1
    print("  ✅ 전투 문구 조립 공백: 수치 뒤 붙음 0 · 공백 이중 0")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
