#!/usr/bin/env python3
"""ED2 번역 작업대 — JP 블록 옆에 **정발 후보**를 놓고 보여 준다.

배정(블록↔엔트리 묶기)은 하지 않는다. 의미정렬 제안이 화면 기준 62% 라 **후보로는 값이
있지만 자동 승격은 못 한다**(틀리는 38%가 엉뚱한 대사를 물어 온다 — `docs/ed2-status.md` §12).
그래서 문안은 `script/ED2SCN*.json` 에 직접 쓰고, 이 도구는 쓸 때 곁에 두는 참고다.

⚠ 출력에 **정발 문안이 찍힌다** — `work/review/` 밖으로 내보내지 말 것(저작권 규칙).

  python3 tools/ed2_script_draft.py ED2SCN1            # 아직 안 쓴 블록만
  python3 tools/ed2_script_draft.py ED2SCN1 --from 23 --n 60
  python3 tools/ed2_script_draft.py --status           # 씬별 진행
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from align_jp_kr import SCN_JP_DIR, load_jp_scene, load_kr_scene
from common import OUT_DIR, ROOT

ALIGN_DIR = os.path.join(OUT_DIR, "align")
SCRIPT_DIR = os.path.join(ROOT, "script")


def _raw(scn):
    """{jp_id: 원문} — **서식 인자(`%s`·`%d`)가 보이는 쪽**을 쓴다.

    ⚠ `load_jp_scene` 의 `body` 는 제어·인자를 걷어낸 것이라 **`%s` 가 안 보인다.** 그걸 보고
    옮기면 인자를 통째로 잃는다(상점 매입 `%s는 %d Gold가 되는데` 가 실제로 그랬다).
    인자 개수는 구조 계약이라 하나만 어긋나도 화면이 깨진다.
    """
    with open(os.path.join(SCN_JP_DIR, f"{scn}.json"), encoding="utf-8") as f:
        doc = json.load(f)
    out = {}
    for e in doc["entries"]:
        t = (e.get("text") or "").replace("\\x25\\x73", "%s").replace("\\x25\\x64", "%d")
        out[e["entry_id"]] = t.replace("\\x25\\x63", "%c")
    return out


def _script(scn):
    p = os.path.join(SCRIPT_DIR, f"{scn}.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _cands(scn):
    """{jp_id: (정발 문안, 점수)} — 의미정렬 제안. 없으면 빈 dict."""
    n = int(scn.replace("ED2SCN", ""))
    p = os.path.join(ALIGN_DIR, f"ED2_SCN{n}.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        pairs = json.load(f)["pairs"]
    kr = {}
    for t, bs in load_kr_scene("ED2", n).items():
        for b in bs:
            kr[(t, b["id"])] = b["body"]
    out = {}
    for q in pairs:
        j = (q.get("jp") or {}).get("entry_id")
        if j is None or not q.get("kr"):
            continue
        out[j] = (kr.get((q["kr"]["table"], q["kr"]["entry_id"]), ""), q.get("score", 0))
    return out


def status():
    print(f"{'씬':<10}{'블록':>7}{'정본':>7}{'남음':>7}  진행")
    for n in range(1, 14):
        scn = f"ED2SCN{n}"
        jp = [b for b in load_jp_scene("ED2", n) if b.get("body")]
        got = len(_script(scn))
        print(f"{scn:<10}{len(jp):>7}{got:>7}{len(jp) - got:>7}  {got / max(1, len(jp)):>6.1%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene", nargs="?")
    ap.add_argument("--from", dest="start", type=int, default=0)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status or not a.scene:
        status()
        return
    n = int(a.scene.replace("ED2SCN", ""))
    done, cand, raw = _script(a.scene), _cands(a.scene), _raw(a.scene)
    shown = 0
    for b in load_jp_scene("ED2", n):
        if not b.get("body") or str(b["id"]) in done or b["id"] < a.start:
            continue
        c, sc = cand.get(b["id"], ("", 0))
        t = raw.get(b["id"], b["body"])
        mark = " ⚠인자" if ("%s" in t or "%d" in t) else ""
        print(f"jp{b['id']}|{b['speaker'] or ''}{mark}|{t}")
        print(f"   후보({sc:.2f}) {c}")
        shown += 1
        if shown >= a.n:
            break


if __name__ == "__main__":
    main()
