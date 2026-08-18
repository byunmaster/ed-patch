#!/usr/bin/env python3
"""동영상 EXE 넷의 패치 앵커를 **도출**하고 OPEN1 의 알려진 값과 대조한다.

`patch_opening_font.py` 는 OPEN1 오프셋을 하드코딩한다. ED2 오프닝(OPEN2)·엔딩(END1·END2)
을 같은 방식으로 한글화하려면 그 앵커들을 **파일마다 다시 찾아야** 한다 — 넷은 같은
프로그램의 다른 빌드라 주소가 밀려 있다(69~78% 바이트가 다르다).

**검증 논법**: 도출기가 OPEN1 에서 하드코딩 값을 **그대로 재현하면** 나머지 셋의 도출값도
믿을 수 있다. 오버레이 base(`check_overlay_base.py`)·폰트베이스 때 쓴 것과 같은 방법이다.
지금 여섯 앵커 전부 재현한다.

⚠ **찾은 값을 쓰기 전에 이 검사를 돌린다.** 앵커 하나만 틀려도 증상은 오타가 아니라
검은 화면이거나 소프트락이다(`patch_opening_font` 의 RELOCATE_OVERFLOW 실패 이력 참조).

  python3 tools/check_movie_anchors.py
"""

import struct
import sys

from common import extract

TADDR = 0x80010000
FILES = (("OPEN1", 69), ("OPEN2", 116), ("END1", 163), ("END2", 210))
# OPEN1 실측 정답 (patch_opening_font.py 하드코딩)
KNOWN = {
    "pc0": 0x80021D50,
    "fontbase": 0x8001BE84,
    "narrow_w": 0x800132E0,
    "narrow_d": 0x80013704,
    "adv_w": 0x80013370,
    "adv_d": 0x80013750,
    "stub": 0x15C14,
    "font": 0x15CE0,
}
NARROW_IMM = (0x8140, 0x8289, 0x8286, 0x828A, 0x828C)  # 실측 순서(원본 비교 체인)


def ram(off):
    return TADDR + off - 0x800


def derive(d):
    a = {}
    a["pc0"] = struct.unpack_from("<I", d, 0x10)[0]

    # 폰트베이스 획득부: ori a0,zero,0x889F + jal + nop + move s0,v0
    for i in range(0, len(d) - 16, 4):
        if d[i : i + 4] == bytes.fromhex("9F880434"):
            w = int.from_bytes(d[i + 4 : i + 8], "little")
            if (w >> 26) == 3 and d[i + 12 : i + 16] == bytes.fromhex("21804000"):
                a["fontbase"] = ram(i + 4)
                break

    # 반각 비교 체인 — ori 다섯 개가 정해진 즉시값을 순서대로 쓴다. stride 는 두 곳이 다르다
    # (표시 쪽은 ori 사이에 beq 가 낀다) → 4·8 둘 다 시도한다.
    chains = []
    for i in range(0, len(d) - 40, 4):
        for step in (4, 8):
            ok = True
            for k, imm in enumerate(NARROW_IMM):
                w = int.from_bytes(d[i + k * step : i + k * step + 4], "little")
                if (w >> 26) != 0x0D or (w & 0xFFFF) != imm:
                    ok = False
                    break
            if ok:
                chains.append((ram(i), step))
    for r, step in chains:
        a["narrow_w" if step == 4 else "narrow_d"] = r

    # advance 상수: 폭측정 `addiu a0,a0,4`(24840004) · 표시 `addiu s3,s3,4`(26730004).
    # 반각 체인 뒤 가까운 곳에 있다 — 체인 시작에서 앞뒤 0x200 안에서 찾는다.
    for key, chain_key, word in (
        ("adv_w", "narrow_w", 0x24840004),
        ("adv_d", "narrow_d", 0x26730004),
    ):
        if chain_key not in a:
            continue
        base = a[chain_key] - TADDR + 0x800
        # ⚠ 체인 **뒤** 첫 것을 고른다 — 앞에도 같은 워드가 있어서(0x80013680) 범위만으로는
        # 갈리지 않는다. advance 상수는 비교 체인을 통과한 뒤(=전각 확정) 진행하는 자리다.
        hits = [
            ram(i)
            for i in range(base, min(len(d) - 4, base + 0x200), 4)
            if int.from_bytes(d[i : i + 4], "little") == word
        ]
        if hits:
            a[key] = hits[0]

    # 안전 0영역: 0x15000~0x17000 최장 0런
    z = best = 0
    start = 0
    for i in range(0x15000, 0x17000):
        if d[i] == 0:
            z += 1
            if z > best:
                best, start = z, i - z + 1
        else:
            z = 0
    a["zero_run"] = (start, best)
    return a


def main():
    rows = {n: derive(extract(l, 96256)) for n, l in FILES}
    keys = ("pc0", "fontbase", "narrow_w", "narrow_d", "adv_w", "adv_d")
    print(f"{'앵커':10} " + "".join(f"{n:>12}" for n, _ in FILES) + "   OPEN1 정답 대조")
    for k in keys:
        cells = ""
        for n, _ in FILES:
            v = rows[n].get(k)
            cells += f"{v:>12X}" if isinstance(v, int) else f"{v!s:>12}"
        ok = rows["OPEN1"].get(k) == KNOWN[k]
        mark = "✅ 재현" if ok else f"❌ 불일치 (정답 {KNOWN[k]:X})"
        print(f"{k:10} {cells}   {mark}")
    print()
    for n, _ in FILES:
        s, ln = rows[n]["zero_run"]
        print(f"{n}: 안전 0영역 file 0x{s:05X} {ln}B (RAM 0x{ram(s):08X})")
    print(f"  OPEN1 하드코딩: 스텁 0x{KNOWN['stub']:05X} · 폰트 0x{KNOWN['font']:05X}")
    bad = [k for k in keys if rows["OPEN1"].get(k) != KNOWN[k]]
    if bad:
        print(f"\n❌ OPEN1 재현 실패: {bad} — 도출기를 믿을 수 없다")
        return 1
    print("\n✅ 여섯 앵커 전부 OPEN1 하드코딩 값 재현 — 나머지 셋의 도출값도 쓸 수 있다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
