#!/usr/bin/env python3
"""번역 진행률 — **번역 정본으로 얼마나 옮겼는가**.

⚠ **축이 바뀌었다**(2026-08-12). 예전엔 `assign_pages.jp_open()`(미배정 PS1 블록)으로
「정발 배정 회수율」을 셌는데, 방침이 「정발을 살리되 고친다」로 옮겨 가면서 배정 자체를
그만뒀다([policy.md](../docs/policy.md) 번역 방침). 이제 세는 것은 **`script/` 로 올라간
블록**이다 — 그게 우리가 쓴 문안이고 유일한 정본이다.

세 수가 다르다:

- **총 블록** — 그 씬의 대사 블록(원문 바이트가 있는 것)
- **정본** — `script/ED1SCN*.json` 에 올라간 것. 사람이 읽고 통과시켰다는 뜻
- **재삽입** — 지난 빌드가 실제 이미지에 넣은 수. 구조 계약 게이트를 통과한 것만이라
  정본보다 적을 수 있다(차이가 곧 게이트에 막힌 블록)

  python3 tools/status.py             # 씬 요약
  python3 tools/status.py --maps      # 맵(코드 함수)별 — 어디가 남았는지
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import OUT_DIR, ROOT

GAME = "ED1"
SCENES = range(1, 7)
SCRIPT_DIR = os.path.join(ROOT, "script")


def scn_blocks(scn):
    """{entry_id} — 그 씬의 대사 블록(원문 바이트가 있는 것)."""
    p = os.path.join(OUT_DIR, "scn_jp", f"{GAME}SCN{scn}.json")
    with open(p, encoding="utf-8") as f:
        doc = json.load(f)
    return {e["entry_id"] for e in doc["entries"] if e.get("raw_hex")}


def done(scn):
    """{entry_id} — 정본으로 올라간 블록."""
    p = os.path.join(SCRIPT_DIR, f"{GAME}SCN{scn}.json")
    if not os.path.exists(p):
        return set()
    with open(p, encoding="utf-8") as f:
        return {int(k) for k in json.load(f) if k.isdigit()}


def _reinserted():
    """지난 빌드가 남긴 재삽입 수(있으면). 없으면 {}."""
    p = os.path.join(OUT_DIR, "build_stats.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def by_scene():
    stats = _reinserted()
    tot = ok = 0
    print(f"  {'씬':10} {'총':>6} {'정본':>7} {'남음':>7}  진행")
    for scn in SCENES:
        blocks, d = scn_blocks(scn), done(scn)
        n, k = len(blocks), len(blocks & d)
        tot += n
        ok += k
        bar = "█" * int(k / max(n, 1) * 20)
        pct = k / max(n, 1) * 100
        print(f"  {GAME}SCN{scn:<5} {n:>6} {k:>7} {n - k:>7}  {bar:<20} {pct:5.1f}%")
    print(f"  {'계':10} {tot:>6} {ok:>7} {tot - ok:>7}  {ok / max(tot, 1) * 100:5.1f}%")
    if stats:
        print(f"\n  지난 빌드 재삽입 {sum(stats.values())}블록")
    return tot - ok


def by_map():
    """맵(코드 함수)별 남은 블록 — 어디를 다음에 잡을지 고르는 축.

    ⚠ 맵 귀속은 `scn_callgraph`(코드가 실제로 부르는 블록)가 정본이다. 예전엔 `scn_maps`
    (지명 헤더 위치)로 추정했는데 그건 배정 제약용이라 같이 걷어냈다.
    """
    import scn_callgraph as G

    for scn in SCENES:
        name = f"{GAME}SCN{scn}"
        d = done(scn)
        rows = []
        for f, eids in G.functions(name).items():
            left = [e for e in eids if e not in d]
            if left:
                rows.append((len(left), f, left))
        rows.sort(reverse=True)
        print(f"  {name}: 남은 맵 {len(rows)}")
        for n, f, left in rows[:8]:
            print(f"      fn@{f:#x}  {n:>4}블록 남음  jp{left[0]}~jp{left[-1]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", action="store_true")
    a = ap.parse_args()
    if a.maps:
        by_map()
    else:
        by_scene()


if __name__ == "__main__":
    main()
