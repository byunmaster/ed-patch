#!/usr/bin/env python3
"""패치 스펙(JSON)을 게임 디렉터리에 적용/복원한다.

스펙의 각 항목은 `from`(원본 바이트)을 반드시 확인한 뒤에만 쓴다. 이미 적용된
파일에 다시 적용하거나, 판본이 다른 원본에 적용하는 사고를 막기 위해서다.

usage:
  apply_patch.py <spec.json> <game_dir>            적용
  apply_patch.py <spec.json> <game_dir> --revert   복원
  apply_patch.py <spec.json> <game_dir> --check    상태만 확인
"""

import json
import os
import sys


def hexbytes(s):
    return bytes.fromhex(s.replace(" ", ""))


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    root = sys.argv[2]
    revert = "--revert" in sys.argv
    check = "--check" in sys.argv

    print(f"# {spec['name']}")
    if spec.get("description"):
        print(f"# {spec['description']}")
    print(f"# 대상: {root}  ({'복원' if revert else '확인' if check else '적용'})")

    # 파일별로 모아서 한 번만 읽고 쓴다
    by_file = {}
    for p in spec["patches"]:
        by_file.setdefault(p["file"], []).append(p)

    changed = 0
    for rel, items in sorted(by_file.items()):
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            print(f"  !! 없음: {path}")
            continue
        data = bytearray(open(path, "rb").read())
        dirty = False
        for p in items:
            off = int(p["offset"], 16) if isinstance(p["offset"], str) else p["offset"]
            src, dst = hexbytes(p["from"]), hexbytes(p["to"])
            if revert:
                src, dst = dst, src
            cur = bytes(data[off : off + len(src)])
            note = p.get("note", "")
            if cur == dst:
                print(f"  = {rel} @{off:#08x} 이미 {dst.hex()} — 건너뜀  {note}")
                continue
            if cur != src:
                print(
                    f"  !! {rel} @{off:#08x} 기대 {src.hex()} 인데 실제 {cur.hex()} — 중단  {note}"
                )
                sys.exit(1)
            if check:
                print(f"  · {rel} @{off:#08x} {src.hex()} -> {dst.hex()} (미적용)  {note}")
                continue
            data[off : off + len(dst)] = dst
            dirty = True
            changed += 1
            print(f"  + {rel} @{off:#08x} {src.hex()} -> {dst.hex()}  {note}")
        if dirty:
            open(path, "wb").write(bytes(data))

    if not check:
        print(f"# {changed}곳 변경")


if __name__ == "__main__":
    main()
