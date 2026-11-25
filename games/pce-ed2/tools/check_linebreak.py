"""줄·쪽 나눔 지표 래칫 (번역 규칙 2-16) — 대사 전량의 **조판 결과**로 센다. 기준선(`linebreak_baseline.json`)보다 늘면 실패, 줄면 `--freeze` 요구.

단위 = 구간(§ 로 가른 한 덩이를 손 쪽 표지 ¶ 로 가른 조각) 하나가 지표에 한 번이라도 걸리면 1.
  a 쪽 끝 한 어절 고아 · b 문장 중간 한 낱말로 끝나는 쪽 · c 문장 중간 손 개행 · f 규칙 후 새로 생긴 퇴행(전 조판과 대조) · d 절째 내리면 들어가는데 쪼갠 줄 · e 굳은 [명사+명사] 구가 줄 끝·첫머리로 갈림 (정의: linemetrics.py)
`--before` 는 규칙을 끄고(ED_LINERULE=0) 센다. `--changes <파일>` 은 규칙 때문에 조판이 달라진 구간을 TSV 로 쓴다.
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_punct
import linemetrics
import typeset

FIT = lambda ln: typeset.px(ln) <= typeset.WIDTH * 12 and not typeset.engine_wraps(ln)  # noqa: E731
BASE = Path(__file__).resolve().parents[1] / "linebreak_baseline.json"


def measure(changes: list | None = None) -> tuple[Counter, int, int]:
    typeset._ensure_phrases()
    cnt: Counter = Counter()
    units = pages = 0
    for where, kind, t, _dots in check_punct.corpus():
        if kind != "dlg":
            continue
        for si, seg in enumerate(t.split("§")):
            for h in linemetrics.hand_newlines(seg):
                cnt["c"] += 1
            for ci, ch in enumerate(seg.split("\f")):
                units += 1
                hd = check_punct.headed(where, si, ci)
                pgs = typeset.pages(ch, headed=hd)
                pages += len(pgs)
                h, spread = linemetrics.window_stats(pgs)
                cnt["h"] += h
                if spread:
                    cnt["h2raw"] += 1
                    words = typeset.spaced(ch.replace("~", "～")).split()
                    if linemetrics.rebalance(words, FIT, pgs):
                        cnt["h2"] += 1  # 창 수를 안 늘리고 고르게 나눌 수 있는데 안 나눈 구간
                for k, v in linemetrics.chunk_metrics(pgs).items():
                    if v:
                        cnt[k] += 1
                if not os.environ.get("ED_LINERULE"):
                    os.environ["ED_LINERULE"] = "0"
                    old = typeset.pages(ch, headed=hd)
                    os.environ.pop("ED_LINERULE")
                    if linemetrics.regress(old, pgs):
                        cnt["f"] += 1
                    if changes is not None and old != pgs:
                        changes.append((where, " / ".join("|".join(p) for p in old), " / ".join("|".join(p) for p in pgs)))
    return cnt, units, pages


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--before", action="store_true")
    ap.add_argument("--changes")
    a = ap.parse_args()
    if a.before:
        os.environ["ED_LINERULE"] = "0"
    ch: list | None = [] if a.changes else None
    cnt, units, pages = measure(ch)
    now = {k: cnt[k] for k in "abcdefh"}
    now["h2"] = cnt["h2"]
    print(f"  줄·쪽 나눔 지표 [pce-ed2] — 구간 {units} · 쪽 {pages} · a {now['a']} · b {now['b']} · c {now['c']} · d {now['d']} · e {now['e']} · f {now['f']} · h {now['h']} · h2 {cnt['h2']} (줄 수 차 2↑ 전체 {cnt['h2raw']})" + (" (규칙 끔)" if a.before else ""))
    if a.changes:
        Path(a.changes).write_text("\n".join("\t".join(r) for r in ch), encoding="utf-8")
        print(f"  바뀐 구간 {len(ch)} → {a.changes}")
    if a.before:
        return 0
    base = json.loads(BASE.read_text()) if BASE.exists() else None
    if a.freeze:
        BASE.write_text(json.dumps(now, indent=1) + "\n")
        return 0
    if base is None:
        print("  ✗ 기준선이 없다 — --freeze")
        return 1
    worse = [k for k in now if now[k] > base.get(k, 10**9)]
    if worse:
        print(f"  ✗ 기준선 {base} 보다 늘었다: {worse}")
        return 1
    if any(now[k] < base.get(k, 0) for k in now):
        print(f"  ✗ 기준선 {base} 보다 줄었다 — --freeze 로 내린다(래칫)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
