#!/usr/bin/env python3
"""ENTER_PROG/ENTER_PROG2가 가리키는 씬 레코드를 훑어 참조 대상 파일이 실재하는지 검사한다.

씬 ID 규칙(T_246 / C_605 에서 역산·검증):
    scene_id = (prefix_index << 12) | number,  prefix_index -> "CDEFGHMTV"
    파일명은 SCENA\\<P>_<NNN>.DLL   (예: 0x3501 -> F_501.DLL, 0x7246 -> T_246.DLL)

레코드는 0x22바이트이고 **오프셋 12의 워드가 씬 ID**다.
호출 관용구는 `mov bx, imm16` 뒤에 ENTER_PROG(#350)/ENTER_PROG2(#352)로의 ljmp/lcall.

usage: scan_scenes.py <scena_dir> [--all]
       기본은 "참조하는데 파일이 없는" 것만 출력. --all이면 전부 출력.
"""

import glob
import os
import struct
import sys

from ne_info import find_ne, parse_ne
from ne_relocs import seg_relocs

PREFIX = "CDEFGHMTV"
ENTER_PROG = {350, 352}
REC_SIZE = 0x22
SCENE_ID_OFF = 12


def scene_name(sid):
    pi, num = sid >> 12, sid & 0xFFF
    if pi >= len(PREFIX):
        return None
    return f"{PREFIX[pi]}_{num:03X}.DLL"


def main():
    scena = sys.argv[1].rstrip("/")
    show_all = "--all" in sys.argv
    have = {n.upper() for n in os.listdir(scena)}

    missing, total = [], 0
    for path in sorted(glob.glob(os.path.join(scena, "*.DLL"))):
        b = open(path, "rb").read()
        try:
            h = parse_ne(b, find_ne(b))
        except (ValueError, IndexError, KeyError, struct.error):
            continue
        base = os.path.basename(path)
        for si, seg in enumerate(h["segments"], 1):
            data = b[seg["file_off"] : seg["file_off"] + seg["length"]]
            try:
                relocs = seg_relocs(b, h, seg)
            except (ValueError, IndexError, KeyError, struct.error):
                continue
            sites = [
                o
                for o, (lab, _at, _a) in relocs.items()
                if lab.startswith("ED2MAIN.#") and int(lab.split("#")[1]) in ENTER_PROG
            ]
            for o in sites:
                # ljmp/lcall 앞 8바이트 안에서 `bb imm16` (mov bx, imm16) 찾기
                for back in range(3, 10):
                    a = o - back
                    if a < 1 or data[a - 1] != 0xBB:
                        continue
                    rec = int.from_bytes(data[a : a + 2], "little")
                    if rec + REC_SIZE > len(data):
                        break
                    sid = int.from_bytes(
                        data[rec + SCENE_ID_OFF : rec + SCENE_ID_OFF + 2], "little"
                    )
                    name = scene_name(sid)
                    total += 1
                    ok = name is not None and name.upper() in have
                    if show_all or not ok:
                        tag = "OK " if ok else "!! "
                        print(
                            f"  {tag}{base} seg{si} rec@{rec:#06x} "
                            f"scene={sid:#06x} -> {name or '(잘못된 prefix)'}"
                        )
                    if not ok:
                        missing.append((base, sid, name))
                    break

    print(f"\n참조 {total}건 검사, 대상 없음 {len(missing)}건")
    if missing:
        seen = sorted({(n, s) for _, s, n in missing})
        print("없는 대상:")
        for n, s in seen:
            print(f"  {n or '?'}  (scene={s:#06x})")


if __name__ == "__main__":
    main()
