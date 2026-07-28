#!/usr/bin/env python3
"""NE 시나리오 DLL의 세그먼트를 추출/디스어셈블한다 (16비트 x86, capstone).

usage:
    ne_disasm.py <dll> [seg_index] [--from HEX] [--count N]

seg_index 미지정 시 세그먼트 목록만 출력. 코드 세그먼트(flags bit0=0)를
16비트로 디스어셈블한다. 오프셋은 세그먼트 로컬(0 기준).
"""

import sys

from capstone import CS_ARCH_X86, CS_MODE_16, Cs

from ne_info import find_ne, parse_ne


def main():
    path = sys.argv[1]
    b = open(path, "rb").read()
    h = parse_ne(b, find_ne(b))
    segs = h["segments"]
    if len(sys.argv) < 3:
        for s in segs:
            kind = "DATA" if (s["flags"] & 1) else "CODE"
            print(f"seg{s['idx']}: {kind} file_off={s['file_off']:#08x} len={s['length']:#06x}")
        return
    idx = int(sys.argv[2])
    seg = segs[idx - 1]
    data = b[seg["file_off"] : seg["file_off"] + seg["length"]]

    start = 0
    count = 0
    if "--from" in sys.argv:
        start = int(sys.argv[sys.argv.index("--from") + 1], 16)
    if "--count" in sys.argv:
        count = int(sys.argv[sys.argv.index("--count") + 1])

    md = Cs(CS_ARCH_X86, CS_MODE_16)
    md.detail = False
    n = 0
    for ins in md.disasm(data[start:], start):
        b_hex = ins.bytes.hex()
        print(f"{ins.address:04x}: {b_hex:<14} {ins.mnemonic:<7} {ins.op_str}")
        n += 1
        if count and n >= count:
            break


if __name__ == "__main__":
    main()
