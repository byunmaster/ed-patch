"""2인칭 「그대」 금지 — 대사에서 「그대」(2인칭)를 쓰지 않는다(마스터 11-12 「q8 적용하자. 대사에서 그대는 좀 잘 안어울리는거같아」, 10-29 Q8).

반말 → 「너」, 하게 → 「자네」, 존대 윗사람·처음 보는 이 → 2인칭을 빼고 이름·호칭. 부사 「그대로」는 대상이 아니다.
대상: 대사 정본(`patch_scn.load_canon`)과 자리별 덮어쓰기(`script/scn_at.json`). 엔딩·스태프롤 시구는 대사가 아니라 여기 범위 밖.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared"))

import common
import patch_scn as S

RX = re.compile(r"그대(?!로)")


def main():
    bad = [("키 " + k, v) for k, v in S.load_canon(quiet=True).items() if isinstance(v, str) and RX.search(v)]
    at = json.load(open(os.path.join(common.GAME_DIR, "script", "scn_at.json"), encoding="utf-8"))
    for site, v in at.items():
        if site != "_doc" and isinstance(v, str) and RX.search(v):
            bad.append((site, v))
    print(f"  2인칭 「그대」 — 대사 {len(bad)}곳 (0 이어야 한다)")
    for s, v in bad[:10]:
        print(f"    ❌ {s}: {v}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
