#!/usr/bin/env python3
"""**화자 프로필** — 인물표(`docs/ed<N>-story-bible.md`)를 쓰기 위한 재료를 뽑는다.

**왜.** 검수가 내리는 판정은 「이 대사가 이 인물답나 · 이 상대에게 이 말투가 맞나」다.
줄거리 요약은 거기 거의 안 쓰이고, 쓰이는 건 **인물표**다 — 누가 누구고 어떤 말투인가.
그 재료는 **이미 우리 손에 있다**: `script/` 에 화자 라벨이 214종 붙어 있고 JP 원문은
`work/derived/scn_jp/` 에 있다. 요약 에이전트에게 게임 파일을 다시 읽힐 이유가 없다.

🔴 **정발은 안 읽는다.** 요약이 정발 유래면 그 요약을 보고 내리는 검수 판정도 정발 유래가
된다(policy.md 「자체 번역」). 여기서 보여 주는 우리 문안은 **A·B 시대만**이다.

⚠ 산출물은 `work/review/` 다 — **JP 원문이 통째로 들어가니 커밋 금지**. 커밋되는 건
이걸 읽고 사람·에이전트가 쓴 `docs/ed<N>-story-bible.md` 뿐이고, 거기엔 대사를 인용하지 않는다.

  python3 tools/speaker_profile.py                  # 전체 → work/review/speaker_profile.md
  python3 tools/speaker_profile.py --min 20         # 20블록 이상인 화자만(주요 인물)
  python3 tools/speaker_profile.py --game ED1       # 한 편만 (⚠ ED2 는 씬 순서가 미확정)
"""

import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import audit_provenance as A
from common import OUT_DIR, REVIEW_DIR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = 8  # 화자마다 보여 줄 대사 수 — 말투는 여덟 줄이면 드러난다


def scn_key(name):
    return (name[:3], int(name[6:]))


def load(game=None):
    """{화자: {씬: [(eid, jp, ours|None)…]}} — ours 는 A·B 시대만."""
    era = A.scan()
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for path in sorted(
        glob.glob(os.path.join(ROOT, "script", "ED*SCN*.json")),
        key=lambda p: scn_key(os.path.basename(p)[:-5]),
    ):
        scn = os.path.basename(path)[:-5]
        if game and not scn.startswith(game):
            continue
        jp_path = os.path.join(OUT_DIR, "scn_jp", f"{scn}.json")
        if not os.path.exists(jp_path):
            continue
        with open(path, encoding="utf-8") as f:
            cur = json.load(f)
        with open(jp_path, encoding="utf-8") as f:
            jp = {str(e["entry_id"]): e.get("text", "") for e in json.load(f)["entries"]}
        per = era.get(scn, {})
        mine = set(per.get("A 작업 중", ())) | set(per.get("B 자체번역", ()))
        for eid, v in cur.items():
            s = v.get("s")
            if not s or not jp.get(eid):
                continue
            by[s][scn].append((int(eid), jp[eid], v.get("t") if eid in mine else None))
    return by


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=1, help="이 블록 수 미만인 화자는 뺀다")
    ap.add_argument("--game", choices=("ED1", "ED2"), help="한 편만")
    a = ap.parse_args()

    by = load(a.game)
    rows = sorted(by.items(), key=lambda kv: -sum(len(x) for x in kv[1].values()))
    rows = [(s, d) for s, d in rows if sum(len(x) for x in d.values()) >= a.min]

    os.makedirs(REVIEW_DIR, exist_ok=True)
    name = f"speaker_profile{'_' + a.game if a.game else ''}.md"
    p = os.path.join(REVIEW_DIR, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write("# 화자 프로필 — ⚠ JP 원문 포함, 커밋 금지\n\n")
        f.write(
            "인물표(`docs/ed<N>-story-bible.md`)의 재료다. `KR` 은 **우리가 쓴 문안만**(A·B 시대).\n\n"
        )
        for s, per in rows:
            tot = sum(len(x) for x in per.values())
            scns = " · ".join(
                f"{k}({len(v)})" for k, v in sorted(per.items(), key=lambda kv: scn_key(kv[0]))
            )
            f.write(f"## {s} — {tot}블록\n\n등장: {scns}\n\n")
            # 씬을 고루 훑는다 — 한 씬에서만 뽑으면 그 장면의 말투로 굳는다
            flat = [
                (k, *e)
                for k, v in sorted(per.items(), key=lambda kv: scn_key(kv[0]))
                for e in sorted(v)
            ]
            step = max(1, len(flat) // SAMPLES)
            for scn, eid, jp, ours in flat[::step][:SAMPLES]:
                f.write(f"- `{scn}:{eid}`\n  - JP {jp}\n")
                if ours:
                    f.write(f"  - KR {ours}\n")
            f.write("\n")
    print(
        f"  화자 {len(rows)} · 블록 {sum(sum(len(x) for x in d.values()) for _, d in rows)} → {os.path.relpath(p, ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
