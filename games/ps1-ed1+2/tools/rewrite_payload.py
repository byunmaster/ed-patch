#!/usr/bin/env python3
"""재작성 페이로드 — **현재 문안(정발 유래)을 감춘다.**

**왜.** 전환 이전 문안은 정발 유래라 그것을 보고 고치면 그게 곧 「정발을 고쳐 쓰기」이고,
policy.md 「규율」이 안전하지 않다고 못 박은 바로 그 짓이다. 그래서 **대상 블록은 JP
원문만** 준다. 이웃은 문맥용인데 **자체 번역분(A·B 시대)일 때만** 우리 문안을 보여 준다.

🔴 **페이로드로 가리는 것만으로는 부족하다**(2026-08-19 실측). 같은 세션에서 앞서 그
문안을 읽었으면 문맥이 이미 오염돼 있다 — 74건 중 2건이 옛 문안과 글자까지 같아졌고
그중 하나가 그 경우였다. **번역은 그 문안을 본 적 없는 별도 에이전트에게 넘긴다**
(유저 확정 2026-08-19: 롬분석 세션과 번역 세션을 가른다). 이 파일이 그 경계다.

  python3 tools/rewrite_payload.py <최소자> <최대자> <출력.json> <씬…>
  python3 tools/rewrite_payload.py 20 40 /tmp/p.json ED2SCN1      # ② 통
"""

import json
import os
import re
import sys

sys.path.insert(0, "tools")
os.environ.setdefault("LOCK_BYPASS", "1")
import audit_provenance as A
from common import OUT_DIR

MINLEN = int(sys.argv[1])  # 이번 통의 하한(③=40)
MAXLEN = int(sys.argv[2])  # 상한(없으면 큰 수)
out_path = sys.argv[3]
scenes = sys.argv[4:]

data = A.scan()
rows = []
for scn in scenes:
    per = data.get(scn, {})
    old = set(per.get("C 전환 이전", ()))
    mine = set(per.get("B 자체번역", ())) | set(per.get("A 작업 중", ()))
    with open(f"script/{scn}.json", encoding="utf-8") as f:
        cur = json.load(f)
    with open(f"{OUT_DIR}/scn_jp/{scn}.json", encoding="utf-8") as f:
        jp = {str(e["entry_id"]): e for e in json.load(f)["entries"]}
    for eid, e in sorted(jp.items(), key=lambda kv: int(kv[0])):
        v = cur.get(eid)
        if not v or e.get("kind") != "block":
            continue
        t = v.get("t") or ""
        n = len(re.sub(r"\s", "", t))
        r = {"scn": scn, "eid": eid, "speaker": v.get("s") or "", "jp": e["text"]}
        if eid in old and MINLEN <= n < MAXLEN:
            r["todo"] = True  # ⚠ 현재 문안은 넣지 않는다
        elif eid in mine:
            r["ours"] = t  # 자체 번역분만 문맥으로
        rows.append(r)

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)
todo = [r for r in rows if r.get("todo")]
print(f"대상 {len(todo)}블록 · 고유 원문 {len({r['jp'] for r in todo})} → {out_path}")
