#!/usr/bin/env python3
"""SCENA/*.DLL 전체를 훑어 특정 ED2MAIN 심볼(ordinal)을 참조하는 자리를 찾는다.

relocation으로 심볼 참조 위치를 특정한 뒤, 그 자리를 포함하는 명령을 디스어셈블해
`mov byte ptr [ROUTE_NO], 8` 같은 대입 값을 뽑아낸다.

usage: scan_sym.py <scena_dir> <ORDINAL|NAME> [--ed2main PATH]
"""

import glob
import os
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_16, Cs
from ne_info import find_ne, parse_ne
from ne_relocs import seg_relocs


def ordmap(path):
    b = open(path, "rb").read()
    h = parse_ne(b, find_ne(b))
    return {o: n for n, o in h["resident_names"] + h["nonresident_names"] if o}


def main():
    scena = sys.argv[1]
    want = sys.argv[2]
    ed2 = (
        sys.argv[sys.argv.index("--ed2main") + 1]
        if "--ed2main" in sys.argv
        else os.path.join(os.path.dirname(scena.rstrip("/")), "ED2MAIN.EXE")
    )
    om = ordmap(ed2)
    if want.isdigit():
        ordinal = int(want)
    else:
        ordinal = next(o for o, n in om.items() if n == want)
    target = f"ED2MAIN.#{ordinal}"
    print(f"# {om.get(ordinal, '?')} = ED2MAIN ordinal #{ordinal}")

    md = Cs(CS_ARCH_X86, CS_MODE_16)
    for path in sorted(glob.glob(os.path.join(scena, "*.DLL"))):
        b = open(path, "rb").read()
        try:
            h = parse_ne(b, find_ne(b))
        except (ValueError, IndexError, KeyError, struct.error):
            continue  # NE가 아니거나 잘린 파일 — 조용히 건너뛴다
        for si, seg in enumerate(h["segments"], 1):
            data = b[seg["file_off"] : seg["file_off"] + seg["length"]]
            try:
                relocs = seg_relocs(b, h, seg)
            except (ValueError, IndexError, KeyError, struct.error):
                continue  # reloc 테이블이 없거나 깨진 세그먼트
            hits = {o for o, (lab, *_) in relocs.items() if lab == target}
            if not hits:
                continue
            # 참조 자리 앞쪽부터 훑어 그 자리를 덮는 명령을 찾는다
            for hit in sorted(hits):
                found = None
                for back in range(1, 12):
                    a = hit - back
                    if a < 0:
                        break
                    for ins in md.disasm(data[a : hit + 8], a):
                        if ins.address <= hit < ins.address + ins.size:
                            found = ins
                        break
                    if found and found.address + found.size > hit:
                        break
                txt = f"{found.mnemonic} {found.op_str}" if found else "?"
                print(f"{os.path.basename(path)} seg{si}:0x{hit:04x}  {txt}")


if __name__ == "__main__":
    main()
