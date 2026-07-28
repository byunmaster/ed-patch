#!/usr/bin/env python3
"""NE 세그먼트 relocation 테이블을 파싱해 import(lcall/ljmp 0:0xffff) 대상을 해석.

각 세그먼트 데이터 뒤(NSRELOC 플래그 0x0100 세트 시)에 WORD count + 8바이트
레코드가 온다. import(ordinal/name) 대상은 modref→imported-name-table 로
모듈명(ED2MAIN/KERNEL)과 ordinal/이름을 얻는다. additive가 아닌 경우 fixup
위치의 WORD가 다음 fixup offset을 가리키는 체인이다.
"""

import struct
import sys

from ne_info import find_ne, parse_ne


def _read_pstr(b, off):
    n = b[off]
    return b[off + 1 : off + 1 + n].decode("latin1"), off + 1 + n


def module_names(b, ne, h):
    """modref 테이블 → 모듈명 리스트(1-based index로 접근)."""
    cmod = h["cmod"]
    names = []
    for i in range(cmod):
        (nameoff,) = struct.unpack_from("<H", b, h["off_modref"] + i * 2)
        s, _ = _read_pstr(b, h["off_import"] + nameoff)
        names.append(s)
    return names


def imported_name(b, h, name_off):
    s, _ = _read_pstr(b, h["off_import"] + name_off)
    return s


def seg_relocs(b, h, seg):
    """세그먼트의 fixup들을 {seg_offset: (label, atname, additive)} 로 반환.

    additive면 파일에 박힌 placeholder가 **addend**다(로더가 타깃 주소를 더한다).
    이 게임의 엔진 전역 참조(off16)는 전부 additive라서, `mov bx,[2] -> PL_TOP`은
    `PL_TOP + 2` 즉 구조체 필드 오프셋을 뜻한다. 반대로 ptr32/seg16은 chained라
    placeholder(0xffff:0000)는 체인 종료 표시일 뿐 의미가 없다.
    """
    if not (seg["flags"] & 0x0100):
        return {}
    p = seg["file_off"] + seg["length"]
    (count,) = struct.unpack_from("<H", b, p)
    p += 2
    mods = module_names(b, find_ne(b), h)
    out = {}
    for _ in range(count):
        atype, rtype, off, t1, t2 = struct.unpack_from("<BBHHH", b, p)
        p += 8
        additive = bool(rtype & 0x04)
        kind = rtype & 0x03
        if kind == 1:  # imported ordinal
            mod = mods[t1 - 1] if 1 <= t1 <= len(mods) else f"mod{t1}"
            label = f"{mod}.#{t2}"
        elif kind == 2:  # imported name
            mod = mods[t1 - 1] if 1 <= t1 <= len(mods) else f"mod{t1}"
            label = f"{mod}.{imported_name(b, h, t2)}"
        elif kind == 0:  # internal ref
            label = f"seg{t1}:{t2:#06x}" if t1 != 0xFF else f"movable#{t2}"
        else:
            label = f"osfixup({t1},{t2})"
        atname = {0: "lobyte", 2: "seg16", 3: "ptr32", 5: "off16", 11: "off32", 13: "ptr48"}.get(
            atype, f"at{atype}"
        )
        # additive가 아니면 fixup 위치에서 체인을 따라 모든 site를 수집
        seg_data = b[seg["file_off"] : seg["file_off"] + seg["length"]]
        cur = off
        seen = set()
        while cur != 0xFFFF and cur not in seen and cur + 1 < len(seg_data):
            seen.add(cur)
            out[cur] = (label, atname, additive)
            if additive:
                break
            nxt = seg_data[cur] | (seg_data[cur + 1] << 8)
            if nxt == 0xFFFF:
                break
            cur = nxt
    return out


def main():
    b = open(sys.argv[1], "rb").read()
    ne = find_ne(b)
    h = parse_ne(b, ne)
    segidx = int(sys.argv[2]) if len(sys.argv) > 2 else None
    print("modules:", module_names(b, ne, h))
    for seg in h["segments"]:
        if segidx and seg["idx"] != segidx:
            continue
        rl = seg_relocs(b, h, seg)
        print(f"\nseg{seg['idx']} relocs: {len(rl)} sites")
        for off in sorted(rl):
            label, atname, additive = rl[off]
            add = "+add" if additive else ""
            print(f"  {off:#06x} [{atname}{add}] -> {label}")


if __name__ == "__main__":
    main()
