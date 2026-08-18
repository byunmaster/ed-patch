#!/usr/bin/env python3
"""ED2 배정 검토 — JP 블록과 **제안된 정발 엔트리**를 나란히 띄우고, 판정을 정본에 박는다.

**왜.** ED2 는 ED1 과 같은 「정발 퍼스트」로 간다(유저 확정 2026-08-13) — 정발 문안을
배정으로 물고, **오역이거나 어색한 자리만** 정발 어투로 우리가 다시 쓴다. 그런데 배정
제안은 믿을 게 못 된다:

- 의미정렬(LaBSE)은 **이 레포에서 걷어냈다**(2026-08-12, 비결정성이 빌드를 갈랐다).
  남은 건 구조 정렬(`align_jp_kr`, 화자·길이·순서 Smith-Waterman)뿐이고 10초면 돈다.
- 그 제안의 **절반 이상이 `low_confidence`** 다(ED2 13씬 5,227쌍 중 2,835건, 실측).
- ED1 로 잰 의미정렬 재현율조차 77.4% 였다 — **다섯에 하나는 좌표가 틀린다.**

그래서 제안은 **바닥재**고, 화면에 나가는 것은 사람이 읽고 통과시킨 것만이어야 한다.
`align_map.json` 은 「검토된 배정」이라는 뜻을 지켜야 하므로 이 도구를 거쳐서만 넣는다.

⚠ **출력은 `work/review/` 로만 간다**(gitignore). 정발 문안이 그대로 찍히므로
**커밋 절대 금지**다.

  python3 tools/ed2_align_review.py ED2SCN1              # 검토표 → work/review/
  python3 tools/ed2_align_review.py ED2SCN1 --range 0 80 # 그 구간만
  python3 tools/ed2_align_review.py ED2SCN1 --kr T_000   # 정발 표를 통째로 (런 대조)
  python3 tools/ed2_align_review.py ED2SCN1 --apply d.json  # 판정을 정본에 박는다
  python3 tools/ed2_align_review.py --status             # 씬별 진행률

판정 파일(`d.json`)은 `{"12": "ED2/T_040#3", "13": null, …}` — 값이 `null` 이면
**배정하지 않는다**(대응 정발이 없다는 판정이고, 그 블록은 `script/` 에 우리가 쓴다).
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from align_jp_kr import ALIGN_DIR, load_jp_scene, load_kr_scene
from common import REVIEW_DIR, ROOT

ALIGN_MAP = os.path.join(ROOT, "align_map.json")


def kr_entries(scn):
    """{(표, 엔트리): 정발 본문} — **그 씬 그룹의 표만**. `align_jp_kr` 과 같은 적재기를 쓴다
    (정규화·화자 승계가 어긋나면 제안과 검토표가 다른 것을 보게 된다)."""
    n = int(scn.replace("ED2SCN", ""))
    out = {}
    for table, blocks in load_kr_scene("ED2", n).items():
        for b in blocks:
            out[(table, b["id"])] = b["body"]
    return out


def _flat(s, n=None):
    s = re.sub(r"\{[a-z]\}", " ", s or "").replace("\\x07", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s if n is None else s[:n]


def load_proposals(scn):
    n = int(scn.replace("ED2SCN", ""))
    p = os.path.join(ALIGN_DIR, f"ED2_SCN{n}.json")
    if not os.path.exists(p):
        raise SystemExit(f"제안이 없다 — `python3 tools/align_jp_kr.py` 로 먼저 만든다 ({p})")
    doc = json.load(open(p, encoding="utf-8"))
    # ⚠ 정발 쪽만 있고 JP 짝이 없는 항목이 섞여 있다(`jp: null`) — 건너뛴다.
    return {q["jp"]["entry_id"]: q for q in doc["pairs"] if q.get("jp") and q.get("kr")}


def review(scn, lo=0, hi=1 << 30):
    n = int(scn.replace("ED2SCN", ""))
    jp = {b["id"]: b for b in load_jp_scene("ED2", n)}
    prop = load_proposals(scn)
    kr = kr_entries(scn)
    done = json.load(open(ALIGN_MAP, encoding="utf-8")).get(scn, {})
    lines = []
    for eid in sorted(jp):
        if not (lo <= eid < hi):
            continue
        b = jp[eid]
        body = _flat(b.get("body"))
        if not body:
            continue
        mark = "✅" if str(eid) in done else "  "
        lines.append(f"{mark} jp{eid}  [{b.get('speaker') or '-'}]")
        lines.append(f"      JP  {body}")
        q = prop.get(eid)
        if q:
            coord = (q["kr"]["table"], q["kr"]["entry_id"])
            flag = "⚠low" if "low_confidence" in q.get("flags", []) else "  "
            lines.append(
                f"      제안 {flag} {coord[0]}#{coord[1]} ({q['score']:.2f})  "
                f"{_flat(kr.get(coord), 90)}"
            )
        else:
            lines.append("      제안 — 없음")
        lines.append("")
    out = os.path.join(REVIEW_DIR, f"{scn}_review.txt")
    os.makedirs(REVIEW_DIR, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"{out}  ({len([x for x in lines if x.startswith(('✅', '  jp'))])} 블록)")
    return out


def apply(scn, path):
    """판정을 `align_map.json` 에 박는다 — 값이 null 이면 배정하지 않는다."""
    dec = json.load(open(path, encoding="utf-8"))
    n = int(scn.replace("ED2SCN", ""))
    jp = {b["id"]: b for b in load_jp_scene("ED2", n)}
    doc = json.load(open(ALIGN_MAP, encoding="utf-8"))
    sec = doc.setdefault(scn, {})
    add = drop = 0
    for eid, coord in dec.items():
        if coord is None:
            if sec.pop(str(eid), None) is not None:
                drop += 1
            continue
        table, _, ent = coord.partition("#")
        # ⚠ speaker 는 **필수**다 — 빠지면 배정을 읽는 쪽이 KeyError 로 죽는다.
        sec[str(eid)] = {
            "table": table,
            "entry_id": int(ent),
            "speaker": jp.get(int(eid), {}).get("speaker") or "",
        }
        add += 1
    doc[scn] = {k: sec[k] for k in sorted(sec, key=int)}
    with open(ALIGN_MAP, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print(f"{scn}: 배정 {add}건 반영 · 해제 {drop}건 · 누계 {len(sec)}건")


def show_table(scn, table):
    """정발 표 하나를 순서대로 — JP 런과 나란히 놓고 사람이 대응을 짓는다.

    ⚠ 제안은 **한 칸씩 밀리는 일이 잦다**(구조 정렬이 JP 리메이크 추가분을 못 흡수한다).
    한 블록씩 보면 그 밀림이 안 보이므로, 표를 통째로 띄워 **런 단위로** 맞춘다."""
    n = int(scn.replace("ED2SCN", ""))
    for t, blocks in sorted(load_kr_scene("ED2", n).items()):
        if table not in t:
            continue
        print(f"── {t}  {len(blocks)}엔트리")
        for b in blocks:
            print(f"  #{b['id']:<4} [{b['speaker'] or '-'}] {b['body'][:96]}")


def status():
    doc = json.load(open(ALIGN_MAP, encoding="utf-8"))
    print(f"{'씬':<10}{'JP블록':>8}{'배정':>8}{'진행':>8}")
    for n in range(1, 14):
        scn = f"ED2SCN{n}"
        jp = [b for b in load_jp_scene("ED2", n) if _flat(b.get("body"))]
        got = len(doc.get(scn, {}))
        print(f"{scn:<10}{len(jp):>8}{got:>8}{got / max(1, len(jp)) * 100:>6.1f}%")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or "--status" in a:
        status()
    elif "--apply" in a:
        apply(a[0], a[a.index("--apply") + 1])
    elif "--kr" in a:
        show_table(a[0], a[a.index("--kr") + 1])
    elif "--range" in a:
        i = a.index("--range")
        review(a[0], int(a[i + 1]), int(a[i + 2]))
    else:
        review(a[0])
