"""맵 점프(`status.md` 「디버그 빌드」 (나)) 용 표 — 맵 표 443항목 × 그 맵이 든 챕터 폴더. 에이전트가 emucap 으로 맵을 옮길 때 본다.

  python3 warp_table.py [--out 파일.tsv]

열: 이름 · 챕터 폴더(여럿이면 `,`) · 팩 번호(맵 표 +6) · 영역(+7). 챕터가 다른 곳으로 가려면 먼저 `14 02 FF <챕터>` 로 그 챕터 시작 맵에 간 뒤
같은 챕터 안 `14 <방향> 06 <이름>` 로 이동한다(실측 10-18). 원본을 읽기만 한다.
"""

import argparse
import re
import sys

import common
import engine_patch as E
from debugpatch import MAP_TABLE


def table(disc="ed3"):
    lba, size = common.iso_files(disc)["/ED3.EXE"]
    exe = bytearray(common.read_lba(disc, lba, size))
    rows, o = [], E._off(MAP_TABLE)
    while exe[o] != 0x5A:
        rows.append((bytes(exe[o : o + 6]).decode("ascii"), exe[o + 6], exe[o + 7]))
        o += 10
    where = {}
    for path, (plba, psize) in common.iso_files(disc).items():
        m = re.fullmatch(r"/SCE(\d)/SC\d\d\d\.DAT", path)
        if not m:
            continue
        for n in common.arc_members(common.read_lba(disc, plba, psize)):
            mm = re.fullmatch(r"\.\.\\DATA\\(\w{6})\.BIN", n)
            if mm:
                where.setdefault(mm.group(1), set()).add(int(m.group(1)))
    return [(n, sorted(where.get(n, ())), p, a) for n, p, a in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()
    lines = ["\t".join((n, ",".join(map(str, ch)) or "-", str(p), str(a))) for n, ch, p, a in table()]
    text = "이름\t챕터\t팩\t영역\n" + "\n".join(lines) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
