#!/usr/bin/env python3
"""{"SCN:eid": "문안"} 을 여러 씬에 한 번에 얹는다 — **재작성이라 기존 `t` 를 덮는다.**

⚠ 얹은 뒤 반드시 둘을 돌린다 — `rewrite_dupfill.py`(같은 원문 사본 전파)와
`build.py`(구조 게이트). 에이전트 출력이 실제로 물린 자리가 넷이다:
`ctrl_seq`(창 수) · `fmt_excess`(인자 초과) · `anchor_tail_size`(제자리 길이) ·
`encode`(폰트에 없는 글자 — 줄표 `—` 를 쓰면 걸린다).

🔴 **얹은 자리를 `rewrite_log.json` 에 남긴다**(2026-08-19). 재작성 결과가 옛 문안과
**글자까지 같아지는 일이 흔하다** — 「같은 원문이면 같은 문안」이 규칙이라 자연히 수렴한다
(실측: 한 배치 41건 중 32건). 그러면 이력만 보는 `audit_provenance` 가 「안 고쳤다」와
구별을 못 해 계속 「정발 유래」로 센다. 예전엔 좌표를 손으로 등록했는데(19건) 200건 넘게는
못 한다.

⚠ **이 기록의 뜻은 「이 블록은 옛 문안을 가린 페이로드에서 다시 썼다」**다. 그 보증은
`rewrite_payload` 가 준다(대상 블록은 JP 원문만 준다). 그러니 **손으로 이 파일에 좌표를
적지 마라** — 그 순간 「정발을 세탁하는 장부」가 된다.

  python3 tools/rewrite_apply.py <번역.json>
"""

import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "rewrite_log.json")

with open(sys.argv[1], encoding="utf-8") as f:
    new = json.load(f)
per = collections.defaultdict(dict)
for k, v in new.items():
    scn, _, eid = k.partition(":")
    per[scn][eid] = v

log = {}
if os.path.exists(LOG):
    with open(LOG, encoding="utf-8") as f:
        log = json.load(f)

for scn, tbl in per.items():
    p = f"script/{scn}.json"
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    for eid, t in tbl.items():
        # ⚠ **빈 문안은 안 받는다**(2026-08-19). 이름판만 있는 블록(`{c}이름{c}{c}`)에
        #    에이전트가 빈 문자열을 내면 조판기가 「창은 있는데 줄이 0」에서 죽는다
        #    (`krwrap.pack_groups_target` 의 `max()` 가 빈 리스트를 받는다). 그런 블록은
        #    애초에 `t` 를 두지 않는 게 맞다 — 이름창은 다른 층이 그린다.
        if not t or not t.strip():
            print(f"  ⚠ {scn}:{eid} 빈 문안 — 건너뛴다(이름판 전용 블록으로 보인다)")
            continue
        d.setdefault(eid, {})["t"] = t
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    log[scn] = sorted(set(log.get(scn, [])) | set(tbl), key=int)
    print(f"  {scn}: {len(tbl)}건 재작성")

with open(LOG, "w", encoding="utf-8") as f:
    json.dump({"_doc": "재작성한 좌표 — 옛 문안을 가린 페이로드에서 썼다는 기록", **log}, f,
              ensure_ascii=False, indent=1)
print(f"  기록 {sum(len(v) for k, v in log.items() if not k.startswith('_'))}건 → rewrite_log.json")
