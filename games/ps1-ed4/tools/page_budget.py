"""쪽 예산 — 원본 쪽(3줄 한도)이 얼마나 꽉 찼고, 한글이 일본어보다 길어지면 몇 쪽이 넘치는가(추정).

    python3 tools/page_budget.py [--seed N]

- **쪽 구조**는 원본에서 읽는다(`typeset.windows` — 표 규격 356멤버의 `01`/`02` 흐름 / 풀 규격 125멤버의 `window_chains`).
- **한글/일본어 길이 비**는 ED3 실측값이다(번역 29,414줄 — 한글 칸수(공백 포함, 개행 제외) ÷ 일본어 글자 수, 일본어 6글자 이상인 줄만):
  전각(공백·부호도 1칸) p5 0.625 · p10 0.70 · p25 0.833 · **p50 1.00** · p75 1.083 · p90 1.188 · p95 1.267 · p99 1.455
  반각(공백·`. , ! ?` 0.5칸)  p5 0.556 · p10 0.618 · p25 0.731 · **p50 0.842** · p75 0.944 · p90 1.038 · p95 1.107 · p99 1.267
  (ED3 번역은 ps1-ed3 워크트리의 진행분 — 읽기만 했다. 일본어 줄 길이는 ED3 디스크에서 새로 쟀다.)
- 줄바꿈 효율 `EFF`(어절 단위로 접느라 줄 끝에 남는 칸): 전각 0.92 · 반각 0.95 (가정 — 줄 끝 낭비 평균 ~2칸/24).
- 쪽당 필요 줄 수 = ceil(한글 칸수 ÷ (24 × EFF)), 한글 칸수 = Σ(줄별 일본어 글자 수 × 그 줄에 뽑은 비). 비는 위 분포에서 **줄마다 독립으로** 뽑는다(2000회 시뮬레이션).
🔴 추정이다 — 실제 번역은 쪽 구조에 맞춰 줄이거나 늘릴 수 있다. 「넘칠 확률」로 읽는다.
"""

import argparse
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dump
import typeset

from shared.ps1 import gmf_script as sm

Q = (0.0, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.0)
FULL = (0.40, 0.625, 0.70, 0.833, 1.00, 1.083, 1.188, 1.267, 1.455, 1.9)
HALF = (0.30, 0.556, 0.618, 0.731, 0.842, 0.944, 1.038, 1.107, 1.267, 1.6)
EFF = {"full": 0.92, "half": 0.95}
COLS = typeset.COLS
LIM = typeset.PAGE_LINES


def draw(table, rng):
    """분위수 표에서 선형 보간으로 한 값을 뽑는다."""
    u = rng.random()
    for i in range(len(Q) - 1):
        if u <= Q[i + 1]:
            t = (u - Q[i]) / (Q[i + 1] - Q[i])
            return table[i] + t * (table[i + 1] - table[i])
    return table[-1]


def pages_of(mem):
    """[(kind, [조각 색인…])] — 쪽 단위."""
    out = []
    if sm.layout(mem) == sm.LAYOUT_TABLE:
        for msg in typeset.windows(mem):
            for pg in msg:
                out.append(("table", pg))
    else:
        info = sm.parse(mem)
        for chain in sm.window_chains(mem, info):
            out.append(("pool", chain))
    return out


def collect():
    rows = []
    for _path, _nm, data, off, sz in dump.script_members():
        mem = data[off : off + sz]
        info = sm.parse(mem)
        segs = [len([c for c in codes if c >= 0x10]) for _, codes in info["segments"]]
        for kind, pg in pages_of(mem):
            lens = [segs[i] for i in pg if i < len(segs)]
            if lens and all(n <= COLS + 4 for n in lens):  # 25~28코드는 대사 자리가 아니다(wrap.md)
                rows.append((kind, lens))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rows = collect()
    print(
        f"쪽 {len(rows):,} (표 규격 {sum(1 for k, _ in rows if k == 'table'):,} · 풀 규격 {sum(1 for k, _ in rows if k == 'pool'):,})"
    )
    by = {}
    for _, lens in rows:
        by[len(lens)] = by.get(len(lens), 0) + 1
    print("쪽당 줄 수 분포:", dict(sorted(by.items())))
    full3 = [lens for _, lens in rows if len(lens) == LIM]
    dense = [lens for lens in full3 if min(lens) >= 20]
    print(
        f"꽉 찬 쪽 — 3줄 {len(full3):,} · 그중 줄마다 20칸 이상 {len(dense):,} · 쪽 평균 일본어 글자 {sum(sum(l) for _, l in rows) / len(rows):.1f}"
    )
    fill = [sum(lens) / (COLS * LIM) for _, lens in rows]
    print(
        f"쪽 채움(일본어 글자 ÷ 72칸): 평균 {sum(fill) / len(fill):.2f} · 90% {sorted(fill)[int(len(fill) * 0.9)]:.2f} · 최대 {max(fill):.2f}"
    )
    rng = random.Random(a.seed)
    print("\n한글 길이가 ED3 실측 분포로 나올 때 **3줄을 넘길 확률** (추정):")
    for name, table in (("전각(반각 없음)", FULL), ("반각(공백·부호 0.5)", HALF)):
        key = "full" if table is FULL else "half"
        exp = 0.0
        over_med = 0
        over_p90 = 0
        N = 400
        for _, lens in rows:
            tot = sum(lens)
            # 중앙값·p90 비를 쪽 전체에 균일 적용(결정적 참고치)
            r50 = table[4]
            r90 = table[6]
            if math.ceil(tot * r50 / (COLS * EFF[key])) > LIM:
                over_med += 1
            if math.ceil(tot * r90 / (COLS * EFF[key])) > LIM:
                over_p90 += 1
            hit = 0
            for _ in range(N):
                need = sum(n * draw(table, rng) for n in lens)
                if math.ceil(need / (COLS * EFF[key])) > LIM:
                    hit += 1
            exp += hit / N
        print(
            f"  {name}: 기대 넘침 쪽 {exp:,.0f} / {len(rows):,} ({exp / len(rows):.1%}) · 중앙 비({table[4]:.2f})만 쓰면 {over_med:,} · p90 비({table[6]:.2f}) 전부면 {over_p90:,}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
