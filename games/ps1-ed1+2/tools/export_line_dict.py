#!/usr/bin/env python3
"""**JP 원문 → 우리 문안 사전** — 플랫폼을 옮겨도 살아남는 유일한 산출물.

**왜.** 08-18 자체 번역 전환의 근거가 이것이다(policy.md) — 배정표(`align_map`)는 씬 분할·창
구조가 달라 새턴·PCE 로 **한 줄도 안 넘어가지만**, 문장 자체는 같은 원작 대사라 그대로 쓴다.
지금 문안은 `script/<씬>.json` 에 **eid** 로 박혀 있어 그대로는 못 옮긴다 — 원문으로 키를
바꿔 두면 그때 바로 붙는다. 이 레포 안에서 이미 증명되고 있다: `rewrite_dupfill` 이 같은
키로 ED1↔ED2 를 오가며 하루에 1,200건 넘게 전파했다.

🔴 **A·B 시대 문안만 담는다**(`audit_provenance`). 「C 전환 이전」은 **정발 유래**라
(policy.md 「전환은 아직 미완」) 그걸 실으면 다음 플랫폼으로 오염을 퍼뜨린다.

⚠ **키는 JP 원문의 sha1 이다 — 평문이 아니다.** 루트 CLAUDE.md 「문장급 문안은 코드에
임베드 금지」는 팔콤 일문에도 걸린다. `textmap/*.json` 이 같은 이유로 sha1 키를 쓴다.
원문은 각 플랫폼의 `originals/` 에서 나오므로 사전에는 있을 필요가 없다.

⚠ **자리**: 지금은 게임 아래다. `shared/` 로 올리는 건 **둘째 타이틀이 실재할 때**다 —
루트 CLAUDE.md 「두 번째 소비자가 생길 때 추상화한다. 기준은 언젠가 쓸 것 같다가 아니라
지금 둘째가 있는가」. `shared/glossary` 도 ED3 스캔이라는 소비자가 생기고서 올라갔다.
그리고 공용은 `main` 에서만 고친다(게임 브랜치에서 고치면 다른 게임이 조용히 바뀐다).

  python3 tools/export_line_dict.py            # → line_dict.json (커밋 가능, sha1 키)
  python3 tools/export_line_dict.py --review   # → work/review/line_dict_plain.md (평문, 커밋 금지)
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import audit_provenance as A
from common import OUT_DIR, REVIEW_DIR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "line_dict.json")
# 인자 센티널 — 담되 **표시**한다. 자리가 플랫폼마다 달라 그대로는 못 붙인다.
FMT = re.compile(r"[\x17\x1a\x1b]")


def key(jp):
    """JP 원문 → sha1 앞 16자. ⚠ 공백을 지우고 잰다 — 이식판은 줄나눔이 다르다."""
    return hashlib.sha1(re.sub(r"\s+", "", jp).encode("utf-8")).hexdigest()[:16]


def collect():
    """{sha1: {"t": 문안, "n": 블록수, "fmt": 인자 있음}} · 평문 대조표"""
    era = A.scan()
    out, plain, split = {}, {}, 0
    for path in sorted(glob.glob(os.path.join(ROOT, "script", "ED*SCN*.json"))):
        scn = os.path.basename(path)[:-5]
        jp_path = os.path.join(OUT_DIR, "scn_jp", f"{scn}.json")
        if not os.path.exists(jp_path):
            continue
        with open(path, encoding="utf-8") as f:
            cur = json.load(f)
        with open(jp_path, encoding="utf-8") as f:
            jp = {str(e["entry_id"]): e.get("text", "") for e in json.load(f)["entries"]}
        mine = set(era.get(scn, {}).get("A 작업 중", ())) | set(
            era.get(scn, {}).get("B 자체번역", ())
        )
        for eid in mine:
            s, t = jp.get(eid, ""), (cur.get(eid) or {}).get("t")
            if not s or not t:
                continue
            k = key(s)
            if k in out and out[k]["t"] != t:
                split += 1  # 같은 원문에 두 문안 — dupfill 이 놓친 자리
                continue
            e = out.setdefault(k, {"t": t, "n": 0})
            e["n"] += 1
            if FMT.search(t):
                e["fmt"] = True
            plain.setdefault(k, (s, t))
    return out, plain, split


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", action="store_true", help="평문 대조표도 뜬다(커밋 금지)")
    a = ap.parse_args()

    d, plain, split = collect()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"_doc": __doc__.split("\n")[0], "lines": d}, f, ensure_ascii=False, indent=1)
    blocks = sum(e["n"] for e in d.values())
    fmt = sum(1 for e in d.values() if e.get("fmt"))
    print(f"  고유 원문 {len(d)} · 블록 {blocks} · 인자 포함 {fmt} → {os.path.relpath(OUT, ROOT)}")
    if split:
        print(f"  ⚠ 같은 원문에 두 문안 {split}건 — `check_same_jp` 로 본다")

    if a.review:
        os.makedirs(REVIEW_DIR, exist_ok=True)
        p = os.path.join(REVIEW_DIR, "line_dict_plain.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# JP 원문 ↔ 우리 문안 (평문) — ⚠ 커밋 금지\n\n")
            f.writelines(
                f"- `{k}`\n  - JP {s}\n  - KR {t}\n" for k, (s, t) in sorted(plain.items())
            )
        print(f"  평문 대조표 → {os.path.relpath(p, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
