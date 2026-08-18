#!/usr/bin/env python3
"""**블록마다 정발 판정을 적어 두는 장부** — 같은 자리를 다시 파지 않기 위한 것.

## 왜 필요한가

방침은 처음부터 「정발 퍼스트」였는데(`docs/policy.md`), 배정에서 평탄한 문안 테이블로
옮기며 **기본값이 조용히 뒤집혔다**. 그 결과 「밀었다고 생각했는데 아니었다」가 되고,
한 자리가 어긋나자 **작업 전체를 못 믿게 됐다**(유저 2026-08-17). 다시 미는 것만으로는
같은 일이 반복된다 — 다음에 또 한 자리가 나오면 또 전체를 의심하게 된다.

장부가 있으면 셋이 생긴다:

1. **진행률이 수치로** 나온다 — 미판정이 몇 건인지 보인다.
2. 어긋난 자리가 나와도 **그 블록의 판정 근거를 즉시** 확인할 수 있다.
3. **기계가 채운 것과 사람이 본 것이 구분**된다 — 신뢰의 단위가 「전체」에서 「블록」으로 내려온다.

`locked_lines.json` 이 인게임 확인분에 대해 하는 일을, 이 장부가 정발 판정에 대해 한다.

## 판정 값

| 값     | 뜻                                                       |
| ------ | -------------------------------------------------------- |
| `정발` | 포인터로 둔다(= `script/` 에 `t` 가 없다). 방침의 기본값 |
| `자체` | 자체번역을 쓴다 — **반드시 사유가 있어야 한다**          |
| `없음` | 정발에 대응이 없다(배정을 못 찾았거나 정발이 안 다룬다)  |

⚠ **`자체` 는 사유 없이 못 쓴다.** 사유가 없으면 그게 바로 방침이 샌 자리다 —
`오역`·`게이트:<사유>`·`개성` 중 하나여야 한다.

⚠ 장부는 **상태를 기록**할 뿐 강제하지 않는다. 강제는 게이트(`check_forbidden`·
`check_terms` …)가 한다 — 장부까지 게이트로 세우면 「고치기 전에 장부부터」가 되어
작업이 막힌다.

  python3 tools/jeongbal_ledger.py --sync    # 현재 상태를 장부에 반영
  python3 tools/jeongbal_ledger.py           # 현황(미판정·사유 없는 자체)
"""

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from adopt_jeongbal import clean, dos_text, stem_sim
from align_map import scene_map
from common import OUT_DIR, ROOT

PROP_OK = 0.35  # 이 아래면 제안이 우리 문안과 아무 관계가 없다


def _proposals(scn):
    """파생 정렬이 이 씬에 대해 낸 제안 — {eid: (표, 엔트리)}.

    ⚠ 「자체번역인데 왜?」를 가르는 열쇠다. 제안조차 없으면 **정발에 대응이 없을 가능성**이
    크고(그래서 우리가 썼다), 제안이 있는데 자체면 **안 본 자리**다. 남은 일의 정의가
    이 둘로 갈린다 — 숫자 하나로 뭉뚱그리면 어디부터 손댈지 못 정한다.
    """
    g, _, n = scn.partition("SCN")
    p = os.path.join(OUT_DIR, "align", f"{g}_SCN{n}.json")
    if not os.path.exists(p):
        return {}
    out = {}
    for pr in json.load(open(p, encoding="utf-8")).get("pairs", []):
        jp, kr = pr.get("jp"), pr.get("kr")
        if jp and jp.get("entry_id") is not None and kr and kr.get("table") is not None:
            out[str(jp["entry_id"])] = (kr["table"], kr["entry_id"])
    return out


LEDGER = os.path.join(ROOT, "jeongbal_audit.json")
DOC = [
    "정발 전수 대조의 **블록별 판정 장부**. 판정 규칙은 docs/policy.md 「정발 전수 대조」.",
    "값: 정발(포인터) · 자체(사유 필수) · 없음(정발에 대응 없음).",
    "`by` 는 근거다 — `기계:기본값`(배정이 있어 포인터로 둠) · `게이트:<사유>`(넣었더니 탈락)",
    "· `오역`·`개성`(사람이 읽고 판정) · `미탐색`(정발 대응을 아직 안 찾음).",
    "⚠ `자체` 인데 `by` 가 `미탐색` 이면 **아직 안 본 자리**다 — 그게 남은 일의 정의다.",
]


def state():
    """블록별 상태 — {씬: {eid: (판정, 근거)}}.

    ⚠ **분모는 「재삽입 대상 전수」다.** `script/` 에서 유도하면 `t` 를 지운 항목이 통째로
    사라져 **채택할수록 총합이 줄어든다**(실측 2026-08-17: ED1 4,467 → 4,462). 정형 빌더가
    만드는 블록도 `script/` 에도 배정에도 없어 장부 밖이었다(ED2SCN11·12·13 에서 6건).
    가변 소스에서 우주를 유도하면 총합이 조용히 어긋난다 — 재삽입이 실제로 무엇을 쓰는지가
    유일하게 안정된 분모다.
    """
    import reinsert_kr_pilot as R

    out = {}
    for scn, _lba, _size in R.SCN_FILES:
        p = os.path.join(ROOT, "script", f"{scn}.json")
        canon = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
        with R.overlay_for(scn):
            tr, _, _ = R.load_translations(scn.replace("SCN", "_SCN"), scn)
        pin = scene_map(scn) or {}
        prop = _proposals(scn)
        rows = {}
        for eid in tr:
            k = str(eid)
            v = canon.get(k, {})
            has_t = bool((v.get("t") or "").strip())
            has_pin = bool(pin.get(str(int(k))) or pin.get(int(k)))
            if not has_t and not has_pin:
                # 정형 블록·상점 프롬프트 등 — 전용 빌더가 **정발 문안에서** 만든다
                rows[k] = ("정발", "기계:정형빌더")
            elif not has_t:
                rows[k] = ("정발", "기계:기본값")
            elif has_t and has_pin:
                rows[k] = ("자체", "미탐색:배정있음")  # 넣었다 물러난 자리 — 사유를 적어야 한다
            elif has_t:
                # ⚠ **「제안이 있다」와 「제안이 맞다」는 다르다.** 정렬기 정확도가 62%라
                # 제안 수를 그대로 「남은 일」로 세면 부풀려진다 — ED1 실측(2026-08-17)에서
                # 1,059건 중 784건이 최고 페이지와 견줘도 어간 유사도 **0.0** 이었다.
                # 그건 볼 자리가 아니라 **제안이 틀린 자리**다.
                m = prop.get(str(int(k)))
                by = "미탐색:대응없음"
                if m:
                    raw = dos_text(*m) or ""
                    t = (v.get("t") or "").strip()
                    best = max(
                        (stem_sim(clean(x), t) for x in str(raw).split("{p}") if clean(x)),
                        default=0,
                    )
                    by = "미탐색:제안있음" if best >= PROP_OK else "미탐색:제안무효"
                rows[k] = ("자체", by)
        if rows:
            out[scn] = rows
    return out


def load():
    if os.path.exists(LEDGER):
        return json.load(open(LEDGER, encoding="utf-8"))
    return {"_doc": DOC}


def sync():
    """현재 상태를 장부에 반영 — ⚠ **사람이 적은 근거는 덮지 않는다.**"""
    led = load()
    led["_doc"] = DOC
    cur = state()
    kept = added = moved = 0
    for scn, rows in cur.items():
        old = led.setdefault(scn, {})
        for k, (v, by) in rows.items():
            prev = old.get(k)
            if prev is None:
                old[k] = {"v": v, "by": by}
                added += 1
                continue
            # ⚠ **사람이 적은 근거만 지킨다.** 기계가 적은 것(`기계:`·`미탐색`)은 매번 현재
            # 상태로 갱신해야 한다 — 안 그러면 분류를 고쳐도 장부가 옛 값을 물고 있어
            # 「남은 일」이 실제와 어긋난다(실측 2026-08-17: 11,514건이 통째로 안 바뀌었다).
            human = not prev["by"].startswith(("기계:", "미탐색"))
            new = {"v": v, "by": prev["by"] if (human and v == "자체") else by}
            if new != prev:
                old[k] = new
                moved += 1
            else:
                kept += 1
        for k in [k for k in old if k not in rows]:
            del old[k]
    json.dump(led, open(LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  장부 갱신 — 신규 {added} · 판정 변경 {moved} · 유지 {kept}")


def report():
    led = load()
    tally = collections.Counter()
    for scn, rows in led.items():
        if scn.startswith("_"):
            continue
        g = scn[:3]
        for e in rows.values():
            tally[(g, e["v"], e["by"])] += 1
    print("  정발 판정 장부")
    for g in ("ED1", "ED2"):
        rows = {(v, by): n for (gg, v, by), n in tally.items() if gg == g}
        if not rows:
            continue
        tot = sum(rows.values())
        print(f"\n  [{g}] 기록된 블록 {tot}")
        for (v, by), n in sorted(rows.items(), key=lambda x: -x[1]):
            mark = "🔴" if (v == "자체" and by.startswith("미탐색")) else "  "
            print(f"    {mark} {v:4s} · {by:14s} {n:5d}")
    n = sum(n for (_g, v, by), n in tally.items() if v == "자체" and by.startswith("미탐색"))
    print(f"\n  🔴 아직 안 본 자리(자체·미탐색) {n}건 — 이게 남은 일이다")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync", action="store_true")
    a = ap.parse_args()
    if a.sync:
        sync()
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
