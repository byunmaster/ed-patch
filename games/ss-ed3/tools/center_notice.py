"""안내 화면 문구를 **원문과 같은 중심**에 놓는다.

🔴 예산의 절반에 맞추면 안 된다 — 문자열마다 예산이 달라서 화면에서 제각각이 된다
  (유저 지적 2026-09-01: 「jp는 중앙정렬인데 우리는 제각각」).
  원문은 **줄마다 중심이 20~21**(바이트, 전각=2)로 일정하다 — 그 중심을 그대로 쓴다.

    앞 공백(바이트) = round(원문 중심 − 우리 내용 / 2)

⚠ 안쪽에 **공백이 두 칸 이상** 이어지는 줄은 건드리지 않는다 — 메뉴 항목 자리다.
⚠ 예산을 넘으면 앞 공백을 줄여서라도 넣는다(안 들어가면 그 줄은 통째로 안 붙는다).
"""

import json
import re
import sys

sys.path.insert(0, "games/ss-ed3/tools")
import common as C
import typeset as T

#   화면끼리 중심을 맞추려고 손으로 정한 앞 공백 (바이트).
#   ⓘ CD2 안내 — **원문 중심 21.0** 에 넷을 모은다. 첫 줄은 예산이 31B 뿐이라
#     「이것은 디스크２입니다.」(22B)로는 못 닿아 **「현재 …」(20B)로 줄였다.**
FIXED = {
    "현재 디스크２입니다.": 11,
    "이 디스크에서 시작할 수 있는": 7,
    "기록이 없습니다.": 13,
    "디스크１로 바꿔 넣어 주세요.": 7,
}

P = "games/ss-ed3/script/system.json"
doc = json.load(open(P, encoding="utf-8"))
with C.open_disc(1) as d:
    blob = d.read("/0.BIN")

n = skip = 0
for jp, kr in list(doc["notice"].items()):
    body = kr.strip(" ")
    if re.search(r"  +", body):
        skip += 1
        continue
    pat = jp.encode("cp932", "ignore")
    at = blob.find(pat)
    if at < 0:
        skip += 1
        continue
    end = at + len(pat)
    pad = 0
    while end + pad < len(blob) and blob[end + pad] == 0:
        pad += 1
    budget = len(pat) + max(0, pad - 1)

    jlead = len(jp) - len(jp.lstrip(" "))
    center = jlead + T.body_bytes(jp[jlead:]) / 2
    w = T.body_bytes(body)
    lead = max(0, round(center - w / 2))
    if lead + w > budget:
        lead = max(0, budget - w)
    if lead + w > budget:
        print(f"  ⚠ 넘침 {body!r}")
        skip += 1
        continue
    #   🔴 **한 화면의 줄끼리 중심이 맞아야 한다** — 예산이 빠듯한 줄은 앞 공백이 잘려
    #     혼자 왼쪽으로 밀린다(실측: CD2 안내 넉 줄이 167·174·177·173 px 로 흩어졌다).
    #     ⇒ 그런 줄이 있는 화면은 **가장 낮은 중심에 나머지를 맞춘다.**
    #     화면 묶음을 코드가 모르니, 겹치는 자리는 아래 표로 손수 못 박는다.
    lead = FIXED.get(body, lead)
    new = " " * lead + body
    if new != kr:
        doc["notice"][jp] = new
        n += 1
json.dump(doc, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
open(P, "a", encoding="utf-8").write("\n")
print(f"원문 중심에 맞춤 {n}줄 · 건너뜀 {skip}")
