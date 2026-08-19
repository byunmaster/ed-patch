#!/usr/bin/env python3
"""같은 JP 원문을 **이미 다시 쓴 자리**가 있으면 사본에 그대로 옮긴다.

⚠ 「원문이 같으면 문안도 같아야 한다」(ed1-status). 손으로 다시 적으면 같은 원문에 다른
문안이 붙는다 — SCN3 도구점 한 벌에서만 31곳이 그랬다.

⚠ **인자는 「본문에 있을 때만」 뺀다**(2026-08-19 수리). 예전엔 JP 어디든 `%s`·`%d` 가
보이면 통째로 뺐는데, 그중 대부분이 **맨 앞 이름창**(`{c}%s{c}`, 904블록)이라 우리 문안엔
센티널이 아예 없다 — 안전한데 버려지고 있었다. 실측: 재작성 249건을 넣었는데 291건이
남았다(전파가 37건뿐). 본문에 박힌 인자만 빼면 그 구멍이 닫힌다.

⚠ **출처는 A·B 두 시대 다**다(같은 날 수리). 예전엔 「A 작업 중」만 봐서, 커밋하는 순간
그 문안이 B 가 되며 **전파원에서 빠졌다** — 커밋 뒤 첫 배치가 늘 헛돌던 이유다.

  python3 tools/rewrite_dupfill.py
"""

import json
import os
import re
import sys

sys.path.insert(0, "tools")
os.environ.setdefault("LOCK_BYPASS", "1")
import audit_provenance as A
from common import OUT_DIR

# 맨 앞 이름창(`{c}…{c}`)은 엔진이 붙이는 자리라 우리 문안에 안 들어간다.
_NAME = re.compile(r"^\{c\}[^{]*\{c\}")


def propagatable(jp):
    """이 JP 원문은 **사본에 그대로 옮겨도 되는가.**

    본문에 인자(`%s`·`%d`)가 박힌 블록만 뺀다 — 거기선 보이지 않는 센티널 자리가
    문안마다 달라 그대로 옮기면 어긋난다. ⚠ 이 판정을 청커(`rewrite_chunk`)도 쓴다 —
    둘이 어긋나면 청커가 「전파될 것」이라 믿고 뺀 블록이 **아무도 안 채운 채 남는다.**
    """
    if not jp:
        return False
    return "\\x25" not in _NAME.sub("", jp)


def _load(scn):
    """(정본, {eid: JP 원문})"""
    with open(f"script/{scn}.json", encoding="utf-8") as f:
        cur = json.load(f)
    with open(f"{OUT_DIR}/scn_jp/{scn}.json", encoding="utf-8") as f:
        jp = {str(e["entry_id"]): e.get("text", "") for e in json.load(f)["entries"]}
    return cur, jp


data = A.scan()
done = {}  # jp원문 → 다시 쓴 문안
for scn, per in data.items():
    cur, jp = _load(scn)
    for kind in ("A 작업 중", "B 자체번역"):
        for eid in per.get(kind, ()):
            s = jp.get(eid, "")
            if propagatable(s) and (cur.get(eid) or {}).get("t"):
                done.setdefault(s, set()).add(cur[eid]["t"])
uniq = {k: next(iter(v)) for k, v in done.items() if len(v) == 1}

n = 0
for scn, per in data.items():
    p = f"script/{scn}.json"
    cur, jp = _load(scn)
    hit = 0
    for eid in per.get("C 전환 이전", ()):
        s = jp.get(eid, "")
        if s in uniq:
            cur[eid]["t"] = uniq[s]
            hit += 1
    if hit:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)
        print(f"  {scn}: 사본 {hit}건")
        n += hit
print(f"사본 채움 {n}건 (기지 원문 {len(uniq)})")
