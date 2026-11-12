#!/usr/bin/env python3
"""줄·쪽 나눔 지표(번역 규칙 2-16, 마스터 10-26) — 대사 전량의 **조판 결과**로 센다. 사람·에이전트 눈이 아니라 기계 지표로 잡는다.

    python3 tools/wrap_metrics.py            지금 값을 센다(목록은 --show)
    python3 tools/wrap_metrics.py --check    기준선(wrap_metrics_baseline.json)보다 늘면 실패 — 래칫
    python3 tools/wrap_metrics.py --freeze   줄었을 때 기준선을 내린다

쪽 = 대사 창 하나(`0F 90 V (01 90 W)* 00` 시퀀스), 줄 = 그 창의 조각 하나. 창 안에서 새로 나눌 수 있는 건 조각 사이 글뿐이고
창 수·조각 수는 그대로다(구조 계약). 지표 넷(창 단위로 센다 — 한 창이 둘에 걸리면 각각 센다):

  a  쪽 끝 한 어절 고아   — 창이 둘 이상의 줄이고, 끝 줄이 한 어절인데 앞 줄이 문장 끝이 아니다(앞 줄에서 이어진 문장의 꼬리 한 낱말)
  b  문장 중간에서 한 낱말로 끝나는 쪽 — 끝 줄이 한 어절이고 문장이 안 끝났는데 다음 창이 이어진다 / 쪽 사이에서 붙여 쓸 말(본용언+보조용언 …)이 갈린다
  c  문장 중간 손 개행   — 한 창 안에서 문장이 안 끝났는데 줄이 바뀌었고, 다음 줄 첫 어절이 앞 줄 남은 칸에 들어간다(폭이 아니라 손이 끊었다)
  e  굳은 [명사+명사] 구가 줄 끝·첫머리로 갈림 — 앞 어절이 조사·어미·관형형·부사로 안 끝나고 같은 이음이 대사 전량에 2회 이상(「노예⏎상인」)
  f  퇴행 — 규칙 적용 뒤 새로 생긴 끊김(`split_reason`)·한 줄이던 문장이 갈림·절 경계 줄 끝이 줄어듦(래칫 0, 걸리면 조판기가 그 창의 변형을 거부한다)
  h  이어지는 창의 마지막 창에 한 어절만 남음 · h2 창 수를 안 늘리고 고르게 나눌 수 있는데 창 줄 수 차가 2 이상(분배)
  d  절째 내리면 들어가는데 쪼갠 줄 — 줄이 넘칠 때 이 줄에서 시작한 절(쉼표·연결어미 뒤부터)이 다음 줄에 통째로 들어가는데 절을 쪼갰다

판정은 `shared/text/krwrap.split_reason`(붙여 쓸 덩어리 정본)을 쓴다 — 조판기와 검출기가 같은 자여야 한다.
"""

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import common
import josa_rt
import script as script_canon
import scriptmap
import typeset

from shared.text import krwrap

BASELINE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wrap_metrics_baseline.json"
)
FREG = {}  # 창마다 퇴행 개수(윈도 순서)
KEYS = ("a", "b", "c", "d", "e", "f", "h", "h2")


def _w(text):
    return typeset.width_cells(text)


def window_stats(rows, nxt, reflowed=True):
    """한 창(비어 있지 않은 줄들)의 지표 → {키: 개수}, nxt = 다음 창의 줄들(없으면 None)."""
    st = dict.fromkeys(KEYS, 0)
    rows = [r for r in rows if r.strip()]
    if not rows:
        return st
    last = rows[-1].split()
    ends = krwrap.is_sentence_end(rows[-1])
    if typeset.orphan_tail(rows):
        st["a"] = 1
    nrows = [r for r in (nxt or []) if r.strip()]
    if (
        nrows
        and not ends
        and not last[-1].endswith(("〜", "～", "ー"))
        and (len(last) == 1 or typeset.bonded(last[-1], nrows[0].split()[0]))
    ):
        st["b"] = 1
    st["e"] = typeset.phrase_violations(rows)
    cols = typeset.COLS["ed3"]
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        if krwrap.is_sentence_end(a):
            continue
        aw, bw = a.split(), b.split()
        if not bw:
            continue
        # c — 손 개행: 재조판을 못 타서 원고의 줄 구조가 그대로 남은 창에서, 다음 줄 첫 어절이 이 줄에 들어가는데도 끊었다
        #     (재조판한 창의 균형 줄바꿈은 손 개행이 아니다. 붙여 쓸 덩어리가 갈리는 자리는 뺀다)
        if (
            not reflowed
            and _w(a) + 0.5 + _w(bw[0]) <= cols
            and len(a) + 1 + len(bw[0]) <= cols
            and not typeset.bonded(aw[-1], bw[0])
        ):
            st["c"] += 1
        # d — 이 줄에서 시작한 마지막 절이 다음 줄에 통째로 들어가는데 절째 내리지 않았다(조판기와 같은 판정)
        if typeset.clause_split(a, b, "ed3", cols):
            st["d"] += 1
    return st


def windows(disc="ed3"):
    """[(자리, [줄…], 다음 창 줄, 재조판 여부)] — 구울 꼴(재조판 또는 원래 구조) 그대로, 멤버마다 창 순서대로."""
    canon, _ = script_canon.load_effective(disc)
    isos = common.iso_files(disc)
    out = []
    for (path, nm), lines in sorted(canon.items()):
        lba, size = isos[path]
        data = common.read_lba(disc, lba, size)
        _, ents = common.arc_parse(data)
        off, sz = next((o, s) for n, o, s in ents if n == nm)
        mem = data[off : off + sz]
        info = scriptmap.parse(mem)
        chains = scriptmap.window_chains(mem, info)
        use = collections.Counter(i for c in chains for i in c)
        texts = [
            None
            if any(i not in lines or use[i] != 1 or lines[i].get("_auto") for i in c)
            else [josa_rt.convert(lines[i]["kr"]) for i in c]
            for c in chains
        ]
        fin = typeset.reflow_member(texts, disc)
        seq = []
        for t, rows in zip(texts, fin, strict=True):
            if t is None:
                seq.append(None)  # 번역 없음·공유 조각 — 순서만 지킨다(이웃 판정을 끊는다)
                continue
            if (
                rows is not None
            ):  # f — 규칙 전 조판(없으면 원고 구조)보다 나빠졌나(조판기가 거부하므로 0 이어야 한다)
                base = typeset.reflow(t, disc, rule216=False)
                FREG[len(FREG)] = len(typeset.regressions(base or t, rows))
            seq.append((rows, True, len(t)) if rows is not None else (t, False, len(t)))
        for n, cur in enumerate(seq):
            if cur is not None:
                nx = seq[n + 1] if n + 1 < len(seq) else None
                out.append(
                    (
                        f"{path}!{nm} #{chains[n][0]}",
                        cur[0],
                        nx[0] if nx else None,
                        cur[1],
                        cur[2],
                        nx,
                    )
                )
    return out


def measure(disc="ed3", show=False):
    typeset.REJECTED.clear()
    tot = collections.Counter()
    shown = collections.defaultdict(list)
    FREG.clear()
    wins = windows(disc)
    tot["f"] = sum(FREG.values())
    for where, rows, nxt, rf, _cap, nx in wins:
        st = window_stats(rows, nxt, rf)
        # h·h2 — 이어지는 창(앞 창이 문장 중간에서 끝남)의 분배: h 마지막 창에 한 어절만 / h2 창 수를 안 늘리고 고르게 나눌 수 있는데 줄 수 차가 2 이상
        a = [r for r in rows if r.strip()]
        if nx and nx[1] and rf and len(a) >= 2 and not typeset._page_end(a[-1]):
            b = [r for r in nx[0] if r.strip()]
            if b:
                st["h2"] = int(len(a) - len(b) >= 2 and len(b) < nx[2])
                st["h"] = int(len(b) == 1 and len(b[0].split()) == 1)
        for k, v in st.items():
            tot[k] += v
            if v and show:
                shown[k].append(where)
    return dict(tot), len(wins), shown


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument(
        "--show", action="store_true", help="자리를 지표별로 최대 20개 찍는다(원문 없음)"
    )
    a = ap.parse_args()
    tot, n, shown = measure("ed3", a.show)
    line = " · ".join(f"{k} {tot.get(k, 0)}" for k in KEYS)
    print(f"   줄·쪽 나눔 지표 — 창 {n:,} · {line} (퇴행이라 거부한 창 {len(typeset.REJECTED)})")
    for k, v in shown.items():
        for w in v[:20]:
            print(f"     {k}: {w}")
    base = None
    if os.path.exists(BASELINE):
        with open(BASELINE, encoding="utf-8") as f:
            base = json.load(f)
    if a.freeze:
        if base and any(tot.get(k, 0) > base.get(k, 0) for k in KEYS):
            print("   🔴 기준선보다 늘었다 — 얼리지 않는다")
            return 1
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump({k: tot.get(k, 0) for k in KEYS}, f)
        print("   기준선을 썼다")
        return 0
    if a.check:
        if base is None:
            print("   🔴 기준선이 없다(--freeze)")
            return 1
        worse = [k for k in KEYS if tot.get(k, 0) > base.get(k, 0)]
        better = [k for k in KEYS if tot.get(k, 0) < base.get(k, 0)]
        for k in worse:
            print(f"   🔴 {k}: 기준선 {base[k]} → {tot.get(k, 0)} (늘었다)")
        if better and not worse:
            print(f"   ⚠ {','.join(better)} 가 기준선보다 줄었다 — `--freeze` 로 내린다")
        return 1 if worse else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
