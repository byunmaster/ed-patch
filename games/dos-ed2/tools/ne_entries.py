#!/usr/bin/env python3
"""NE entry table을 파싱해 ordinal → seg:offset 을 얻고, 주소를 export 이름으로 되짚는다.

크래시 화면의 `CS:IP = segment #N of ED2MAIN.EXE` 를 "어느 엔진 함수인가"로
바꾸는 데 쓴다.

entry table 구조: 번들(bundle)의 연속.
  [count][seg_indicator]
    seg_indicator == 0x00 : null 번들 — ordinal을 count만큼 건너뛴다
    seg_indicator == 0xFF : movable — 엔트리 6바이트 {flags, INT3Fh(2), seg, offset(2)}
    그 외                 : fixed    — 엔트리 3바이트 {flags, offset(2)}, seg = indicator
count == 0 이면 테이블 끝.

usage:
  ne_entries.py <exe> [--seg N] [--near SEG:HEXOFF]
"""

import sys

from ne_info import find_ne, parse_ne


def entries(b, h):
    """{ordinal: (seg, offset)}"""
    out = {}
    p = h["off_entry"]
    end = p + h["cbenttab"]
    ordinal = 1
    while p < end:
        count = b[p]
        if count == 0:
            break
        ind = b[p + 1]
        p += 2
        if ind == 0x00:
            ordinal += count
            continue
        for _ in range(count):
            if ind == 0xFF:
                seg = b[p + 3]
                off = int.from_bytes(b[p + 4 : p + 6], "little")
                p += 6
            else:
                seg = ind
                off = int.from_bytes(b[p + 1 : p + 3], "little")
                p += 3
            out[ordinal] = (seg, off)
            ordinal += 1
    return out


def names_by_ordinal(h):
    return {o: n for n, o in h["resident_names"] + h["nonresident_names"] if o}


def main():
    path = sys.argv[1]
    b = open(path, "rb").read()
    h = parse_ne(b, find_ne(b))
    ents = entries(b, h)
    nm = names_by_ordinal(h)

    if "--near" in sys.argv:
        seg_s, off_s = sys.argv[sys.argv.index("--near") + 1].split(":")
        seg, off = int(seg_s), int(off_s, 16)
        cands = [(o, s, f) for o, (s, f) in ents.items() if s == seg and f <= off]
        if not cands:
            print(f"seg{seg}:{off:#06x} 앞쪽에 export 없음")
            return
        cands.sort(key=lambda t: t[2])
        o, s, f = cands[-1]
        print(f"seg{seg}:{off:#06x} 를 포함하는(직전) export:")
        print(f"  #{o} {nm.get(o, '?')}  @ seg{s}:{f:#06x}   (+{off - f:#x})")
        print("직전 5개:")
        for o, s, f in cands[-5:]:
            print(f"  #{o:<4} {nm.get(o, '?'):<24} seg{s}:{f:#06x}  (+{off - f:#x})")
        return

    want = int(sys.argv[sys.argv.index("--seg") + 1]) if "--seg" in sys.argv else None
    rows = sorted(((s, f, o) for o, (s, f) in ents.items()), key=lambda t: (t[0], t[1]))
    for s, f, o in rows:
        if want and s != want:
            continue
        print(f"  seg{s}:{f:#06x}  #{o:<4} {nm.get(o, '')}")


if __name__ == "__main__":
    main()
