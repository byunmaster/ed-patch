#!/usr/bin/env python3
"""번역 진행률 — 씬·맵별 회수율을 한 번에 본다.

"1장은 거진 다 된거야?" 같은 질문에 그때그때 계산하지 않으려고 만들었다. 축은
`assign_pages.jp_open()`(미배정 PS1 블록)이라 판정 기준이 배정 파이프라인과 어긋나지 않는다.

⚠ 여기 "회수"는 **배정된 블록 수**다. 그중 구조 계약 게이트(`window_deficit`·`fmt_excess`·
`ctrl_seq` 등)를 통과해 실제로 이미지에 들어간 수는 `build.py` 의 "총 재삽입"이고 더 적다.
차이가 곧 **게이트에 막힌 블록**이라 그것도 같이 찍는다.

  python3 tools/status.py              # 씬 요약
  python3 tools/status.py --maps       # 맵(인스턴스)별 — 어디가 비었는지
  python3 tools/status.py --maps -n 20 # 미회수 많은 순 상위 20
"""

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from assign_pages import jp_open  # noqa: E402
from common import OUT_DIR  # noqa: E402
from scn_maps import block_instances  # noqa: E402

GAME = "ED1"
SCENES = range(1, 7)


def scn_blocks(scn):
    """{entry_id} — 그 씬의 대사 블록(원문 바이트가 있는 것)."""
    p = os.path.join(OUT_DIR, "scn_jp", f"{GAME}SCN{scn}.json")
    doc = json.load(open(p, encoding="utf-8"))
    return {e["entry_id"] for e in doc["entries"] if e.get("raw_hex")}


def _reinserted():
    """지난 빌드가 남긴 재삽입 수(있으면). 없으면 None."""
    p = os.path.join(OUT_DIR, "reinsert_stats.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8")).get("total")
    return None


def bar(done, total, w=24):
    if not total:
        return " " * w
    n = round(w * done / total)
    return "█" * n + "·" * (w - n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", action="store_true", help="맵(인스턴스)별 상세")
    ap.add_argument("-n", type=int, default=0, help="상세에서 상위 N개만")
    a = ap.parse_args()

    # 미회수 블록 — 재삽입기와 같은 판정을 쓴다
    open_by_scn = collections.defaultdict(set)
    for b in jp_open(GAME):
        open_by_scn[b["scn"]].add(b["id"])

    print(f"{'씬':>4} {'회수':>6} {'전체':>6}  {'':24}  비율")
    t_done = t_all = 0
    per_map = collections.defaultdict(lambda: [0, 0])  # 인스턴스 → [회수, 전체]
    for scn in SCENES:
        try:
            blocks = scn_blocks(scn)
        except FileNotFoundError:
            continue
        opened = open_by_scn[scn] & blocks
        done, tot = len(blocks) - len(opened), len(blocks)
        t_done += done
        t_all += tot
        print(f"SCN{scn} {done:6} {tot:6}  {bar(done, tot)}  {done / tot:5.1%}" if tot else "")
        if a.maps:
            inst = block_instances(GAME, scn)
            for bid in blocks:
                k = f"SCN{scn} {inst.get(bid, '(미상)')}"
                per_map[k][1] += 1
                if bid not in opened:
                    per_map[k][0] += 1
    print(f"{'계':>4} {t_done:6} {t_all:6}  {bar(t_done, t_all)}  {t_done / t_all:5.1%}")
    ins = _reinserted()
    if ins:
        print(f"\n배정 {t_done} · 실제 재삽입 {ins} → 게이트에 막힌 블록 {t_done - ins}")
    else:
        print("\n(실제 재삽입 수는 build.py 출력의 '총 재삽입' — 게이트 통과분)")

    if a.maps:
        rows = sorted(per_map.items(), key=lambda kv: (kv[1][0] - kv[1][1], kv[0]))
        if a.n:
            rows = rows[: a.n]
        print(f"\n{'맵(인스턴스)':<34} {'회수':>5} {'전체':>5}  비율   미회수")
        for k, (d, t) in rows:
            print(f"{k:<34} {d:5} {t:5}  {d / t:5.1%}  {t - d:5}")


if __name__ == "__main__":
    main()
