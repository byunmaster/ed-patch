"""대사 번역 진척 — 「어디까지 됐나 · 다음에 뭘 하나」를 한 화면에.

    python3 games/ss-ed3/tools/progress.py            # 전체 집계
    python3 games/ss-ed3/tools/progress.py --files    # 파일별
    python3 games/ss-ed3/tools/progress.py --todo MAP001   # 그 파일의 남은 블록을 검토표로

⚠ **검토표는 원문을 담는다** — `work/review/` 로 나가고 커밋하지 않는다(CLAUDE.md).
   커밋되는 것은 우리 번역만 담은 `script/MAP*.json` 뿐이다.

세는 단위는 **블록**이 아니라 **글자**다. 블록은 「네」 한 마디부터 3 페이지짜리까지
편차가 30 배라 블록 수로 세면 진척이 거짓말을 한다.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import mapfile as M
import typeset as T

SCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "script")


def script_of(stem):
    """`script/<stem>.json` 의 번역 — 없으면 빈 dict."""
    p = os.path.join(SCRIPT_DIR, f"{stem}.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def walk(disc=1):
    """`[(stem, [블록…], 번역 dict)]` — 맵 파일을 번호순으로."""
    out = []
    with C.open_disc(disc) as d:
        for n, lba, size in sorted(d.files()):
            if not n.startswith("/MAP/") or not n.endswith(".BIN"):
                continue
            stem = os.path.basename(n)[:-4]
            out.append((stem, M.blocks(d.read_extent(lba, size)), script_of(stem)))
    return out


def tally(disc=1):
    """파일별 `(stem, 블록수, 번역블록수, 글자수, 번역글자수)`."""
    rows = []
    for stem, bl, kr in walk(disc):
        n = c = dn = dc = 0
        for i, x in enumerate(bl):
            t = M.text_of(x["body"])
            # ⚠ 시작이 밀린 블록은 애초에 번역 대상이 아니다(`mapfile.suspect_head`) —
            #   분모에 넣으면 다 옮긴 파일이 영영 100% 가 안 된다.
            if not t.strip() or M.suspect_head(x):
                continue
            n += 1
            c += len(t)
            if str(i) in kr:
                dn += 1
                dc += len(t)
        rows.append((stem, n, dn, c, dc))
    return rows


def todo(stem, disc=1):
    """그 파일의 **남은** 블록을 검토표로 — `work/review/todo_<stem>.json`."""
    for s, bl, kr in walk(disc):
        if s != stem:
            continue
        items = {}
        for i, x in enumerate(bl):
            t = M.text_of(x["body"])
            if not t.strip() or str(i) in kr:
                continue
            if M.suspect_head(x):
                continue  # 시작이 밀린 블록 — 번역하면 먹힌 글자가 앞에 남는다
            items[str(i)] = {
                "jp": t,
                "budget": len(x["body"]),  # 우리 문안이 들어갈 바이트 예산
                "rows": [len(l) for l in t.replace("\f", "\n").split("\n")],
                "narration": T.is_narration(t),
            }
        os.makedirs(C.REVIEW_DIR, exist_ok=True)
        p = os.path.join(C.REVIEW_DIR, f"todo_{stem}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
        return p, len(items)
    raise SystemExit(f"그런 맵이 없다: {stem}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", type=int, default=1)
    ap.add_argument("--files", action="store_true")
    ap.add_argument("--todo")
    a = ap.parse_args()

    if a.todo:
        p, n = todo(a.todo, a.disc)
        print(f"남은 블록 {n} → {p}")
        return

    rows = tally(a.disc)
    if a.files:
        for stem, n, dn, c, dc in rows:
            bar = "█" * int(dc / c * 20) if c else ""
            print(f"  {stem}  {dc:>6,}/{c:>6,}자 {dc / c * 100 if c else 0:5.1f}%  {bar}")
    N = sum(r[1] for r in rows)
    DN = sum(r[2] for r in rows)
    Cc = sum(r[3] for r in rows)
    DC = sum(r[4] for r in rows)
    done = sum(1 for r in rows if r[3] and r[3] == r[4])
    print(f"\n대사 {DC:,}/{Cc:,}자 ({DC / Cc * 100:.2f}%) · 블록 {DN:,}/{N:,} · 파일 {done}/{len(rows)}")


if __name__ == "__main__":
    main()
