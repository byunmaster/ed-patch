#!/usr/bin/env python3
"""SCENA/*.DLL 전체의 export 구성을 집계한다.

"이 DLL만 X를 export하지 않는다"는 식의 관찰은 비교 대상을 좁게 잡으면
쉽게 틀린다. 실제로 3차 분석의 `ALGO_00` 부재설은 F 계열끼리만 비교한 탓에
나온 오판이었다 — 전체로 보면 356개 중 176개가 `ALGO_00` 없이 정상 동작한다.
그런 오판을 반복하지 않으려고 전수 집계를 도구로 남긴다.

usage:
  scan_exports.py <scena_dir>              이름별 등장 횟수 + 조합별 분포
  scan_exports.py <scena_dir> --has NAME   해당 export를 가진 DLL 목록
  scan_exports.py <scena_dir> --lacks NAME 해당 export가 없는 DLL 목록
"""

import collections
import glob
import os
import struct
import sys

from ne_info import find_ne, parse_ne


def exports(path):
    """{이름: ordinal}. ordinal 0(모듈명 자체)은 뺀다."""
    b = open(path, "rb").read()
    h = parse_ne(b, find_ne(b))
    return {n: o for n, o in h["resident_names"] + h["nonresident_names"] if o}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    scena = sys.argv[1]
    paths = sorted(glob.glob(os.path.join(scena, "*.DLL")))
    table = {}
    for p in paths:
        try:
            table[os.path.basename(p)[:-4]] = set(exports(p))
        except (ValueError, struct.error) as e:  # NE 아님 / 테이블 잘림
            print(f"!! {os.path.basename(p)}: {e}", file=sys.stderr)

    for flag, keep in (("--has", True), ("--lacks", False)):
        if flag in sys.argv:
            want = sys.argv[sys.argv.index(flag) + 1]
            hit = [n for n, ex in sorted(table.items()) if (want in ex) == keep]
            print(f"# {want} {'있는' if keep else '없는'} DLL: {len(hit)}/{len(table)}")
            for i in range(0, len(hit), 8):
                print("  " + ", ".join(hit[i : i + 8]))
            return

    cnt = collections.Counter()
    for ex in table.values():
        cnt.update(ex)
    print(f"# DLL {len(table)}개")
    print("\n-- export 이름별 등장 횟수 --")
    for n, c in cnt.most_common():
        print(f"  {n:<16} {c:>4}  ({c * 100 // len(table)}%)")

    combos = collections.defaultdict(list)
    for n, ex in sorted(table.items()):
        combos[tuple(sorted(ex))].append(n)
    print("\n-- export 조합별 분포 --")
    for k, v in sorted(combos.items(), key=lambda kv: -len(kv[1])):
        print(f"  [{len(v):>3}] {', '.join(k)}")
        if len(v) <= 12:
            print(f"        {', '.join(v)}")


if __name__ == "__main__":
    main()
