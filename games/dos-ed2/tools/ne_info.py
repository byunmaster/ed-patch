#!/usr/bin/env python3
"""만트라 DOS판 SCENA/*.DLL 의 내부 NE(New Executable) 헤더를 파싱한다.

구조: outer MZ + DPMI 16비트 스텁(rtm/dpmi16bi) 뒤에, 실제 시나리오 코드가
NE 포맷으로 들어있다. NE는 세그먼트 테이블 + 이름 기반 export(resident/
non-resident name table) + entry table 을 가진 16비트 세그먼트 실행 형식.
"""

import struct
import sys


def find_ne(b: bytes) -> int:
    """내부 MZ의 e_lfanew를 따라 NE 헤더 오프셋을 찾는다.

    outer MZ(offset 0) 다음에 두 번째 MZ가 있고, 그 e_lfanew가 NE를 가리킨다.
    """
    # 두 번째 MZ 탐색 (0 이외)
    off = b.find(b"MZ", 2)
    while off != -1:
        if off + 0x40 <= len(b):
            (lfanew,) = struct.unpack_from("<I", b, off + 0x3C)
            ne = off + lfanew
            if 0 <= ne < len(b) - 2 and b[ne : ne + 2] == b"NE":
                return ne
        off = b.find(b"MZ", off + 2)
    # 폴백: NE 시그니처 직접 탐색
    off = b.find(b"NE")
    while off != -1:
        # NE 헤더 최소 유효성: usage count 위치 등 대충 확인
        if off + 64 <= len(b):
            return off
        off = b.find(b"NE", off + 2)
    raise ValueError("NE header not found")


def parse_ne(b: bytes, ne: int) -> dict:
    """NE 헤더 주요 필드 + 세그먼트/이름 테이블을 파싱."""
    h = {}
    (
        sig,
        ver,
        rev,
        enttab,
        cbenttab,
        crc,  # DWORD
        flags,
        autodata,
        heap,
        stack,
        csip,
        sssp,
        cseg,
        cmod,
        cbnonres,
        segtab,
        rsrctab,
        restab,
        modtab,
        imptab,
        nonres,
        cmovent,
        align,
        cres,
        exetyp,
    ) = struct.unpack_from("<2sBBHHIHHHHIIHHHHHHHHIHHHB", b, ne)
    h.update(
        sig=sig,
        flags=flags,
        cseg=cseg,
        cmod=cmod,
        align=align or 9,
        csip=csip,
        sssp=sssp,
        autodata=autodata,
        off_seg=ne + segtab,
        off_rsrc=ne + rsrctab,
        off_resname=ne + restab,
        off_modref=ne + modtab,
        off_import=ne + imptab,
        off_nonres=nonres,  # 파일 절대 오프셋
        off_entry=ne + enttab,
        cbenttab=cbenttab,
        cbnonres=cbnonres,
    )
    shift = h["align"]
    # 세그먼트 테이블: 엔트리 8바이트 {offset(sector), length, flags, minalloc}
    segs = []
    for i in range(cseg):
        so, sl, sf, sa = struct.unpack_from("<HHHH", b, h["off_seg"] + i * 8)
        segs.append(
            dict(idx=i + 1, file_off=so << shift, length=sl or 0x10000 if so else sl, flags=sf)
        )
    h["segments"] = segs

    # resident-name table (exports 이름): [len][name][ordinal(2)] ... len==0 종료
    def read_names(off):
        names = []
        p = off
        while p < len(b):
            n = b[p]
            if n == 0:
                break
            name = b[p + 1 : p + 1 + n].decode("latin1")
            (ordv,) = struct.unpack_from("<H", b, p + 1 + n)
            names.append((name, ordv))
            p += 1 + n + 2
        return names

    h["resident_names"] = read_names(h["off_resname"])
    h["nonresident_names"] = read_names(h["off_nonres"]) if nonres else []
    return h


def main():
    b = open(sys.argv[1], "rb").read()
    ne = find_ne(b)
    print(f"file={sys.argv[1]} size={len(b)}  NE@ {ne:#x}")
    h = parse_ne(b, ne)
    print(
        f"flags={h['flags']:#06x} segs={h['cseg']} modrefs={h['cmod']} "
        f"align=2^{h['align']} autodata_seg={h['autodata']} csip={h['csip']:#x} sssp={h['sssp']:#x}"
    )
    print("-- segments --")
    for s in h["segments"]:
        print(
            f"  seg{s['idx']}: file_off={s['file_off']:#08x} len={s['length']:#06x} flags={s['flags']:#06x}"
        )
    print("-- resident names (exports, ordinal→entry) --")
    for name, ordv in h["resident_names"]:
        print(f"  #{ordv:<3} {name}")
    if h["nonresident_names"]:
        print("-- non-resident names --")
        for name, ordv in h["nonresident_names"]:
            print(f"  #{ordv:<3} {name}")


if __name__ == "__main__":
    main()
