#!/usr/bin/env python3
"""시나리오 DLL 세그먼트를 엔진 import 이름까지 주석 달아 디스어셈블한다.

lcall/ljmp 0:0xffff (그리고 off16/ptr32 fixup) 자리를 relocation + ED2MAIN
export ordinal→name 으로 해석해 `-> ED2MAIN.YES_NO` 처럼 표기.

usage: annotate.py <dll> <seg> --from HEX [--count N] [--ed2main PATH]
"""

import sys

from capstone import CS_ARCH_X86, CS_MODE_16, Cs
from ne_info import find_ne, parse_ne
from ne_relocs import seg_relocs


def load_ed2main_ordmap(path):
    b = open(path, "rb").read()
    h = parse_ne(b, find_ne(b))
    m = {}
    for name, o in h["resident_names"] + h["nonresident_names"]:
        if o:
            m[o] = name
    return m


def main():
    path = sys.argv[1]
    seg_idx = int(sys.argv[2])
    start = int(sys.argv[sys.argv.index("--from") + 1], 16) if "--from" in sys.argv else 0
    count = int(sys.argv[sys.argv.index("--count") + 1]) if "--count" in sys.argv else 0
    ed2 = (
        sys.argv[sys.argv.index("--ed2main") + 1]
        if "--ed2main" in sys.argv
        else path.rsplit("/", 2)[0] + "/ED2MAIN.EXE"
    )

    b = open(path, "rb").read()
    h = parse_ne(b, find_ne(b))
    seg = h["segments"][seg_idx - 1]
    data = b[seg["file_off"] : seg["file_off"] + seg["length"]]
    relocs = seg_relocs(b, h, seg)  # {off: (label, atname)}
    ordmap = load_ed2main_ordmap(ed2)

    def resolve(label):
        # ED2MAIN.#NNN -> ED2MAIN.NAME
        if label.startswith("ED2MAIN.#"):
            o = int(label.split("#")[1])
            return f"ED2MAIN.{ordmap.get(o, '#' + str(o))}"
        return label

    md = Cs(CS_ARCH_X86, CS_MODE_16)
    n = 0
    for ins in md.disasm(data[start:], start):
        note = ""
        # fixup가 이 명령 바이트 범위 안에 있으면 주석
        for off in range(ins.address, ins.address + ins.size):
            if off in relocs:
                label, atname, additive = relocs[off]
                sym = resolve(label)
                # additive off16이면 placeholder가 addend다 → PL_TOP+2 처럼 표기.
                # (chained ptr32/seg16의 0xffff는 체인 종료 표시일 뿐이라 무시)
                if additive and atname == "off16" and off + 1 < len(data):
                    addend = data[off] | (data[off + 1] << 8)
                    if addend:
                        sym = f"{sym}+{addend:#x}"
                note = f"   ; -> {sym}"
                break
        print(f"{ins.address:04x}: {ins.bytes.hex():<14} {ins.mnemonic:<7} {ins.op_str}{note}")
        n += 1
        if count and n >= count:
            break


if __name__ == "__main__":
    main()
