"""읽을거리(`BOOK*.BIN`) 중 **아직 안 옮긴 문단**을 검토표로 뽑는다.

키는 `book.paragraphs()` 의 문단 색인이고, 되끼울 때 지켜야 하는 것 둘을 같이 적는다 —
**줄 수**(넘으면 못 넣는다)와 **줄마다의 칸(B)**. 재삽입기가 다시 나눠 주므로 번역은
문단 통째로 하면 된다.

⚠ **원문이 실린다 — `work/review/` 밖으로 내보내지 않는다**(루트 「저작권」).

    python3 games/ss-ed3/tools/book_todo.py            # 전부 → work/review/book_todo.md
    python3 games/ss-ed3/tools/book_todo.py BOOK27     # 한 파일만 (화면)
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import book as B
import common as C
import reinsert_book as RB
import strtab as S

OUT = os.path.join(C.REVIEW_DIR, "book_todo.md")


def walk(disc=1, only=None):
    with C.open_disc(disc) as d:
        for n, lba, size in d.files():
            if not (n.startswith("/SYSTEM/BOOK") and n.endswith(".BIN")):
                continue
            stem = os.path.basename(n)[:-4]
            if only and stem != only:
                continue
            data = d.read_extent(lba, size)
            lines = [dict(x, text=S.text_of(x["raw"])) for x in S.strings(data)]
            pars = B.paragraphs(lines)
            if not pars:
                continue
            tbl = RB.table(stem)
            yield stem, lines, pars, tbl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stem", nargs="?")
    a = ap.parse_args()

    out = ["# 읽을거리 — 아직 안 옮긴 문단", "", "⚠ 원문이 실린다 — **커밋 금지**.", ""]
    npar = nch = 0
    for stem, lines, pars, tbl in walk(only=a.stem):
        todo = [(i, at, rows) for i, (at, rows) in enumerate(pars) if str(i) not in tbl]
        if not todo:
            continue
        out.append(f"## {stem}  ({len(todo)}/{len(pars)} 문단)")
        out.append("")
        for i, at, rows in todo:
            w = [len(lines[at + k]["raw"]) for k in range(len(rows))]
            body = B.join_text(rows)
            npar += 1
            nch += len(body.strip())
            out.append(f"- `{i}` · 줄 {len(rows)} · 칸 {w}")
            out.append(f"  - {body}")
        out.append("")
    head = f"- 남은 문단 **{npar}** · 글자 **{nch:,}**\n"
    out.insert(3, head)
    if a.stem:
        print("\n".join(out))
        return
    os.makedirs(C.REVIEW_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(f"남은 문단 {npar} · 글자 {nch:,} → {os.path.relpath(OUT, C.WORK_DIR)}")


if __name__ == "__main__":
    main()
