#!/usr/bin/env python3
"""인사 「これは」 직역 검사 — 「이거 이거」·「이거 ○○ 왕자님」·「이거 정말 감사합니다」 가 우리 줄에 나가면 실패.

    python3 scripts/check/check_greeting.py --game sfc-ed2          # 요약
    python3 scripts/check/check_greeting.py --game sfc-ed2 --list   # 걸린 자리 전부

규칙 정본은 `rpg-translate` 「인사·감탄사는 화자마다 갈라 쓴다 — 다만 이식판끼리는 맞춘다」(마스터 09-08):
인사 `これは(これは)` 는 화자에 따라 이런, / 허허, / 아이고, / 아니, 이게 누구십니까 / 어이쿠, 로 옮긴다.
- 왜 게이트인가: 09-08 에 PS1 은 다 걷었는데 규칙이 스킬 문서에만 있어 다른 기종 넷에 50줄이
  그대로 남았다(10-20 style 전수 검수, 마스터 「이거 이거 는 제발 좀 안나오게 하자」).
- 잣대: **원문이 인사 꼴**(`これはこれは` · `これは` 뒤에 호칭 `さま·様·王子·殿·どの·さん`)인데 우리 줄에 「이거」가
  인사 자리로 나가면 걸린다. 「これは難しい」 같은 지시어(정말 「이것은」)는 원문 꼴이 달라 안 걸린다.
- 🔴 번역 규칙 4-10(마스터 10-24 「이거 자체가 상대를 하대하는 듯한 느낌이야」 · 란도 포함): 고맙다·실례 인사
  (`これはどうも`·`これは 失礼`)와 이름이 토큰으로 든 줄(`이거, {D0:2B}.` — 10-24 sfc-ed1 이 손으로 찾았다)까지 본다.
- 어댑터는 이름 검사와 같은 것(`games/<게임>/tools/names_corpus.py` 의 `pairs()`).

종료 코드: 0 = 없음(또는 어댑터 없음 — 어댑터 없음은 이름 검사가 이미 실패시킨다) · 1 = 걸림.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_names import _adapter

# 원문 인사 꼴 — 겹친 これは, 또는 これは 뒤 짧은 이름 + 호칭
_JP_GREET = re.compile(
    r"これは[、,　 ]*これは"
    r"|これは[、,　 ]*[^\s　。！？!?、]{0,12}?(?:さま|様|王子|殿|どの|さん|嬢|姫|殿下|閣下)"
    # 4-10(마스터 10-24) — 사람을 맞는 감탄사 전반: 고맙다·실례 · 이름이 토큰으로 든 호칭(おうじ)
    r"|これは[、,　 ]*(?:どうも|失礼|しつれい|ありがと|すみません|おうじ|おひめ|国王|王妃|陛下|\{[^{}]*\})"
)
# 우리 줄의 인사 자리 「이거」 — 줄·문장 머리의 「이거 이거」 또는 「이거, ○○ 왕자/님/아가씨…」 꼴
#   (10-20 sfc-ed2 「이거 {플로라} 아가씨」를 「님」만 보다 놓쳤다)
_KR_GREET = re.compile(
    r"(?:^|[\s¶↵⏎.!?…「」}])이거[ ,…]*(?:이거|[^\s,…]{1,12}\s?(?:왕자|님|아가씨|공주|나리|씨|양|군)"
    # 4-10 — 「이거 정말 감사합니다」·「이거 실례했습니다」·「이거 국왕 폐하」·이름 토큰 「이거, {D0:2B}.」
    r"|(?:정말\s)?감사|고맙|실례|죄송|국왕|왕비|폐하|\{[^{}]*\})"
)


def hits(pairs):
    for where, jp, kr, *_ in pairs:
        if not jp or not kr:
            continue
        if _JP_GREET.search(jp) and _KR_GREET.search(kr):
            yield where, jp, kr


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    mod = _adapter(a.game)
    if mod is None:
        print(f"인사 직역 검사 [{a.game}] — 어댑터 없음(이름 검사 몫)")
        return 0
    found = list(hits(mod.pairs()))
    print(f"인사 직역 검사 [{a.game}] — 「これは」 인사를 「이거」로 옮긴 줄 {len(found)}")
    for where, _jp, kr in found if a.list else found[:10]:
        print(f"  ✗ {where}  {kr[:60]!r}")
    if not a.list and len(found) > 10:
        print(f"  … 외 {len(found) - 10} (--list)")
    if found:
        print(
            "  → rpg-translate 「인사·감탄사는 화자마다 갈라 쓴다」 — PS1 같은 씬·같은 화자 줄에 맞춘다"
        )
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
