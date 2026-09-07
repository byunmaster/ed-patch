"""읽을거리 문안을 **칸에 맞춰 다듬는 자리** — 후보를 재 보고, 좋아질 때만 넣는다.

🔴 낱말 갈림은 조판이 아니라 **길이** 문제다. 조판이 가져갈 몫은 DP 가 이미 가져갔고
   (`book.split_to`), 남은 갈림은 **문안이 원문 줄 격자보다 길어서** 생긴다. 줄이면 없어진다.
⚠ 그런데 눈으로 줄이면 **엉뚱한 데서 나빠진다** — 한 자를 줄였는데 `fit_spaces` 가 다른 줄의
  띄어쓰기를 되살려 갈림이 늘기도 한다. 그래서 **재 보고 넣는다.**

    python3 games/ss-ed3/tools/book_fit.py --list             # 갈림 있는 문단
    python3 games/ss-ed3/tools/book_fit.py --show BOOK27 24   # 지금 상태 + 줄 나눔
    python3 games/ss-ed3/tools/book_fit.py --try  BOOK27 24 "새 문안"   # 재 보기만
    python3 games/ss-ed3/tools/book_fit.py --apply BOOK27 24 "새 문안"  # 좋아질 때만 넣는다

`--apply` 가 받아들이는 조건(하나라도 어기면 안 넣는다):
  · 원문 줄 수에 들어간다(`ok`)
  · 낱말 갈림이 **줄거나**, 같더라도 **띄어쓰기가 되살아난다**
  · 띄어쓰기를 빼야 들어가는 상태로 **나빠지지 않는다**
⚠ 「갈림이 줄 때만」으로 두면 **공백이 빠지는 문단을 못 고친다** — 갈림 수는 그대로인데
  화면에서는 낱말이 붙어 나오는 자리가 있다(BOOK24[19] 실측 2026-09-03).
"""

import argparse
import collections
import glob
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import book as B
import common as C
import reinsert_book as RB
import strtab as S

SCRIPT = os.path.join(C.GAME_DIR, "script", "book")
_grid = {}


def grid(stem):
    """그 책의 **문단별 줄 폭**(바이트) — 원본이 정한 격자다."""
    if stem not in _grid:
        name = f"/SYSTEM/{stem}.BIN"
        with C.open_disc(1) as d:
            data = next(d.read_extent(l, s) for n, l, s in d.files() if n == name)
        lines = [dict(x, text=S.text_of(x["raw"])) for x in S.strings(data, S.load_base(name))]
        _grid[stem] = {
            str(pi): [len(x["raw"]) for x in lines[at : at + len(rows)]]
            for pi, (at, rows) in enumerate(B.paragraphs(lines))
        }
    return _grid[stem]


def rate(stem, pi, text=None):
    """`(칸, 문안 길이, 초과, 공백뺌, 들어가나, 갈림, 줄들)` — 되끼움과 같은 경로로 잰다."""
    widths = grid(stem)[str(pi)]
    kr = RB.table(stem)[str(pi)] if text is None else text
    base = B.tidy_spaces(B.to_fullwidth(kr))
    kr2, dropped = B.fit_spaces(base, widths)
    new, ok = B.split_to(kr2, widths)
    if not ok and "|" in base:
        kr2, dropped = B.fit_spaces(B.tidy_spaces(base.replace("|", "　")), widths)
        new, ok = B.split_to(kr2, widths)
    return {
        "cells": sum(widths) // 2,
        "want": len(base.replace("|", "")),
        "over": len(base.replace("|", "")) - sum(widths) // 2,
        "dropped": bool(dropped),
        "ok": ok,
        "cuts": B.word_cuts(kr2, new) if ok else None,
        "lines": new,
    }


def line(stem, pi, r):
    return (
        f"{stem}[{pi}] 칸 {r['cells']} 문안 {r['want']} 초과 {r['over']:+d} "
        f"· 공백뺌 {r['dropped']} · 갈림 {r['cuts']}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--show", nargs=2, metavar=("BOOK", "번호"))
    ap.add_argument("--try", dest="probe", nargs=3, metavar=("BOOK", "번호", "문안"))
    ap.add_argument("--apply", nargs=3, metavar=("BOOK", "번호", "문안"))
    a = ap.parse_args()

    if a.list:
        tot = nsp = 0
        for f in sorted(glob.glob(os.path.join(SCRIPT, "BOOK*.json"))):
            stem = os.path.basename(f)[:-5]
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            for k in sorted((x for x in d if not x.startswith("_")), key=int):
                r = rate(stem, k)
                #   🔴 **띄어쓰기가 빠지는 문단도 같이 본다** — 갈림은 0 인데 화면에선
                #     낱말이 붙어 나오는 자리가 있다(`fit_spaces` 가 칸을 맞추려고 뺀다).
                #     갈림만 세면 그 자리가 영영 안 보인다(2026-09-03 실측 14 문단).
                if r["cuts"] or r["dropped"]:
                    print("  " + line(stem, k, r))
                    tot += r["cuts"] or 0
                    nsp += bool(r["dropped"])
        print(f"→ 낱말 갈림 {tot} · 띄어쓰기가 빠지는 문단 {nsp}")
        return 0

    if a.show:
        stem, pi = a.show
        r = rate(stem, pi)
        print(line(stem, pi, r))
        for i, x in enumerate(r["lines"]):
            print(f"   {i:2d}: {x}")
        return 0

    if a.probe or a.apply:
        stem, pi, text = a.probe or a.apply
        o, n = rate(stem, pi), rate(stem, pi, text)
        print("전 " + line(stem, pi, o))
        print("후 " + line(stem, pi, n))
        for i, x in enumerate(n["lines"]):
            print(f"   {i:2d}: {x}")
        if a.probe:
            return 0
        better = n["cuts"] < o["cuts"] or (
            n["cuts"] == o["cuts"] and o["dropped"] and not n["dropped"]
        )
        good = n["ok"] and better and (o["dropped"] or not n["dropped"])
        if not good:
            print("✗ 안 넣는다 — 나아지지 않거나 띄어쓰기가 더 빠진다")
            return 1
        p = os.path.join(SCRIPT, f"{stem}.json")
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh, object_pairs_hook=collections.OrderedDict)
        d[str(pi)] = text
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print(f"✅ 넣었다 — 갈림 {o['cuts']} → {n['cuts']}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
