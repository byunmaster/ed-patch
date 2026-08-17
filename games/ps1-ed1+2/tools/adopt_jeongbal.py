#!/usr/bin/env python3
"""**정발이 이기는 자리를 기계로 골라 포인터로 되돌린다** — 전수 대조의 기계 몫.

판정 규칙은 `docs/policy.md` 「정발 전수 대조」다. 그중 **읽지 않아도 규칙이 자동으로
적용되는 구간**만 여기서 처리한다 — 뜻이 같고(어간이 겹치고) 길이가 1:1 이면 규칙 ①이
그대로 성립한다. 나머지(뜻이 갈리는 구간·정발 한 엔트리가 여러 블록에 걸치는 구간)는
사람이 읽어야 한다.

**정발 채택 = `script/` 의 `t` 삭제**다. 그러면 배정(정발 포인터)이 살아나고, 문안은
리포에 안 남는다 — 저작권 체계와 같은 방향이다(`t` 에 베껴 적으면 정반대가 된다).

## 왜 문자열 유사도가 아니라 어간인가

`외출하십니까` vs `외출하시나요` 는 뜻이 같은데 문자열로 재면 어미 때문에 점수가 깎인다.
어절 앞 2음절만 보면(조사·어미를 버리면) 이런 짝이 제대로 붙는다 — 사전 없이 쓰는 근사지만
「내용어가 같은가」라는 물음에는 충분하다. ⚠ 반대로 **어간이 갈리면 뜻이 갈린 것**이므로
자동 채택에서 뺀다.

## 자동으로 빼는 것

- **용어 정본의 금지어가 정발에 있는 자리**(`용자`·`마법`·`체력` …) — 규칙 ④(일관성)와
  부딪힌다. 정발을 받아들이면 `check_terms` 가 실패한다.
- **락이 걸린 블록** — 인게임 확인분이라 사람이 판단한다.
- **길이가 1:1 이 아닌 자리** — 정발 한 엔트리가 PS1 여러 블록에 걸치는 꼴이라
  `t` 삭제만으로는 안 되고 조각내기(`chain`/`subs`)가 필요하다.

## 넣어 보고 깨지면 되돌린다

정발 문안이 우리 것보다 길면 **슬롯을 넘거나 씬이 부풀어 다른 블록이 앵커를 침범**한다
(실측: ED2SCN1 은 총 +26자만으로 4블록이 밀렸다). 그래서 적용 → 빌드 → **이번에 넣은 것
중 탈락한 자리만 되돌림** → 재빌드까지가 한 벌이다. 사람이 하면 매번 샌다.

  python3 tools/adopt_jeongbal.py --dry            # 후보만 센다
  python3 tools/adopt_jeongbal.py                  # 적용 + 되돌림까지
  python3 tools/adopt_jeongbal.py --sim 0.6        # 문턱을 낮춘다(⚠ 확인 필요해진다)
"""

import argparse
import collections
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from align_map import scene_map
from check_terms import TERMS
from common import OUT_DIR, ROOT

BAD_TERMS = [b for _c, bad, _w in TERMS.values() for b in bad]
LEN_LO, LEN_HI = 0.7, 1.4  # 1:1 로 볼 길이비
_CACHE = {}


def dos_text(table, eid):
    """정발 엔트리 문안 — `work/derived/dos_kr/<표>.json` 에서."""
    if table not in _CACHE:
        p = os.path.join(OUT_DIR, "dos_kr", *table.split("/")) + ".json"
        _CACHE[table] = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
    d = _CACHE[table]
    if d is None:
        return None
    for e in d if isinstance(d, list) else d.get("entries", []):
        if e.get("entry_id") == eid or e.get("id") == eid:
            return e.get("text")
    return None


def clean(t):
    """비교용 정규화 — 제어·마크업을 걷어낸다.

    ⚠ **화자 마크업을 반드시 먼저 뗀다.** 정발은 `신부{/spk}곤란한 일이…` 처럼 이름을
    본문 앞에 얹어 두는데, 안 떼면 그 이름이 길이와 어간에 섞여 멀쩡한 짝이 문턱 아래로
    떨어진다 — 실측(2026-08-17): 신부 대사 27블록이 이것 때문에 자동 채택에서 빠졌다.
    """
    t = str(t)
    t = re.sub(r"\{spk\}.*?\{/spk\}", "", t)   # {spk}이름{/spk}
    t = re.sub(r"^[^{]*\{/spk\}", "", t)        # 이름{/spk} (여는 태그가 없는 꼴)
    t = re.sub(r"\\x[0-9a-fA-F]{2}|\{/?[a-z]+\}", "", t)
    return re.sub(r"\s+", " ", t).strip()


def stems(t):
    """어절 앞 2음절 — 조사·어미 차이를 지운다(사전 없이 쓰는 근사)."""
    out = []
    for w in re.sub(r"[^\w가-힣%\s]", " ", t).split():
        w = re.sub(r"[^가-힣A-Za-z0-9%]", "", w)
        if w:
            out.append(w[:2])
    return out


def stem_sim(a, b):
    A, B = collections.Counter(stems(a)), collections.Counter(stems(b))
    if not A or not B:
        return 0.0
    return 2 * sum((A & B).values()) / (sum(A.values()) + sum(B.values()))


def candidates(threshold, games=("ED1",)):
    """[(씬, eid, 정발, 우리)] — 자동 채택해도 되는 자리."""
    locks = json.load(open(os.path.join(ROOT, "locked_lines.json"), encoding="utf-8"))["_settled"]
    out, skipped = [], collections.Counter()
    for p in sorted(glob.glob(os.path.join(ROOT, "script", "*SCN*.json"))):
        scn = os.path.basename(p)[:-5]
        if not any(scn.startswith(g) for g in games):
            continue
        canon = json.load(open(p, encoding="utf-8"))
        pin = scene_map(scn) or {}
        lk = locks.get(scn, {})
        for k, v in canon.items():
            t = (v.get("t") or "").strip()
            m = pin.get(str(int(k))) or pin.get(int(k))
            if not t or not m:
                continue
            d = clean(dos_text(m["table"], m["entry_id"]))
            if not d:
                continue
            if not (LEN_LO <= len(d) / max(len(t), 1) <= LEN_HI):
                skipped["길이 다름(조각내기 필요)"] += 1
                continue
            if stem_sim(d, t) < threshold:
                skipped["어간이 갈린다(사람이 읽는다)"] += 1
                continue
            if any(b in d for b in BAD_TERMS):
                skipped["용어 정본과 충돌"] += 1
                continue
            if k in lk:
                skipped["락(인게임 확인분)"] += 1
                continue
            out.append((scn, k, d, t))
    return out, skipped


def _write(scn, mutate):
    p = os.path.join(ROOT, "script", f"{scn}.json")
    d = json.load(open(p, encoding="utf-8"))
    mutate(d)
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def build_drops():
    """빌드하고 **화면에 일본어가 남는** 탈락 자리를 돌려준다 — {(씬, eid): 사유}."""
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "build.py")],
        capture_output=True,
        text=True,
        cwd=os.path.join(ROOT, "tools"),
    )
    drops = {}
    # ⚠ 빌드는 탈락 목록을 **stderr 로도** 낸다 — stdout 만 보면 되돌림이 조용히 안 걸린다
    # (실측 2026-08-17: 「최종 채택 91건」이라 해 놓고 두 블록이 일본어로 남아 있었다).
    for m in re.finditer(r"^\s+(ED[12]SCN\d+) jp(\d+): (\w+)$", r.stdout + r.stderr, re.M):
        if m.group(3) in ("anchor_overlap", "mid_block_ref", "anchor_tail_size"):
            continue  # 배치 사유라 문안과 무관하다
        drops[(m.group(1), m.group(2))] = m.group(3)
    return r.returncode, drops


def flip_all(games, scenes=None):
    """**배정이 있는 블록은 전부 정발로 둔다** — 08-12 방침의 기본값 복원.

    ⚠ 방침은 처음부터 「정발 퍼스트」였는데(policy.md), 배정에서 평탄한 문안 테이블로 옮기며
    **기본값이 조용히 뒤집혔다** — `script/` 에 `t` 를 적어야 문안이 나가고, 적는 순간 정발보다
    우선한다. 규칙이 바뀐 게 아니라 구조가 바꿔 놓은 것이다(2026-08-17 규명).

    기본값이 정발이면 **미판정 = 방침 준수**가 된다. 안 본 자리가 있어도 규칙이 안 깨지므로,
    「전수를 다 봤는가」가 신뢰의 조건에서 빠진다 — 이게 전수조사보다 근본적인 교정이다.
    """
    locks = json.load(open(os.path.join(ROOT, "locked_lines.json"), encoding="utf-8"))["_settled"]
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "script", "*SCN*.json"))):
        scn = os.path.basename(p)[:-5]
        if not any(scn.startswith(g) for g in games):
            continue
        if scenes and scn not in scenes:
            continue
        canon = json.load(open(p, encoding="utf-8"))
        pin = scene_map(scn) or {}
        lk = locks.get(scn, {})
        for k, v in canon.items():
            t = (v.get("t") or "").strip()
            m = pin.get(str(int(k))) or pin.get(int(k))
            if not t or not m or k in lk:
                continue
            if not clean(dos_text(m["table"], m["entry_id"])):
                continue
            out.append((scn, k, "", t))
    return out


def apply_and_heal(cand, rounds=3):
    """넣고 → 깨진 것만 되돌리고 → 다시. 배치가 밀려 **연쇄로 깨지므로** 한 번으론 안 끝난다."""
    keep = {(s, k): t for s, k, _d, t in cand}
    todo = list(keep)
    for scn in {s for s, _k in todo}:
        ids = [k for s, k in todo if s == scn]

        def drop_t(d, ids=ids):
            for k in ids:
                if k in d:
                    d[k].pop("t", None)
                    if not d[k]:
                        del d[k]

        _write(scn, drop_t)
    reverted = []
    for i in range(rounds):
        rc, drops = build_drops()
        bad = [(s, k) for (s, k) in drops if (s, k) in keep and (s, k) not in reverted]
        if not bad:
            return rc, reverted
        print(f"  라운드 {i + 1}: 탈락 {len(bad)}건 되돌림")
        for scn in {s for s, _k in bad}:
            ids = [k for s, k in bad if s == scn]

            def put_back(d, scn=scn, ids=ids):
                for k in ids:
                    d.setdefault(k, {})["t"] = keep[(scn, k)]

            _write(scn, put_back)
        reverted += bad
    rc, _ = build_drops()
    return rc, reverted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", type=float, default=0.70)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--games", default="ED1")
    ap.add_argument("--flip", action="store_true", help="배정 있는 블록을 전부 정발로")
    ap.add_argument("--scenes", default="")
    a = ap.parse_args()

    if a.flip:
        scenes = set(a.scenes.split(",")) if a.scenes else None
        cand = flip_all(tuple(a.games.split(",")), scenes)
        print(f"  정발로 되돌릴 블록 {len(cand)}건")
        if a.dry or not cand:
            return 0
        rc, rev = apply_and_heal(cand)
        print(f"  최종 정발 {len(cand) - len(rev)}건 · 자체번역 유지 {len(rev)}건 · 빌드 {'✅' if rc == 0 else '❌'}")
        for s, k in rev[:20]:
            print(f"     유지 {s} jp{k}")
        return 0

    cand, skipped = candidates(a.sim, tuple(a.games.split(",")))
    by_scn = collections.Counter(s for s, _k, _d, _t in cand)
    print(f"  자동 채택 후보 {len(cand)}건 (어간 {a.sim}+ · 1:1)")
    for s, n in sorted(by_scn.items()):
        print(f"     {s} {n}")
    for why, n in skipped.most_common():
        print(f"  – 뺀 것: {why} {n}")
    if a.dry or not cand:
        return 0

    keep = {(s, k): t for s, k, _d, t in cand}
    for scn in by_scn:
        ids = [k for s, k, _d, _t in cand if s == scn]

        def drop_t(d, ids=ids):
            for k in ids:
                d[k].pop("t", None)
                if not d[k]:
                    del d[k]

        _write(scn, drop_t)
    print(f"\n  {len(cand)}건 적용 — 빌드로 검증한다")

    rc, drops = build_drops()
    bad = [(s, k) for (s, k) in drops if (s, k) in keep]
    if bad:
        print(f"  ⚠ 넣었더니 탈락한 자리 {len(bad)}건 — 우리 문안으로 되돌린다")
        for s, k in bad:
            print(f"     {s} jp{k}: {drops[(s, k)]}")
        for scn in {s for s, _k in bad}:
            ids = [k for s, k in bad if s == scn]

            def put_back(d, scn=scn, ids=ids):
                for k in ids:
                    d.setdefault(k, {})["t"] = keep[(scn, k)]

            _write(scn, put_back)
        rc, _ = build_drops()
    print(f"  최종 채택 {len(cand) - len(bad)}건 · 빌드 {'✅' if rc == 0 else '❌ 남은 실패는 사람이 본다'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
