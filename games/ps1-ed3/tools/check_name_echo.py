#!/usr/bin/env python3
"""이름창≠본문 메아리 검사(F4) — **화자 이름이 본문 첫머리에 또 찍히지 않나.**

    python3 tools/check_name_echo.py --disc ed3

대사창은 이름(첫 행)과 본문(아랫 행)이 따로 나간다. 번역 본문이 「크리스: 안녕」·「크리스 「안녕」」처럼 **이름으로 시작**하면
화면에 이름이 두 번 나온다(소설식 표기가 새어 들어온 것). 번역 정본의 본문 조각 중 **그 멤버 앞머리 이름(정본 speaker·사전 인물)으로
시작하고 곧 `:`·`：`·`「`·`『`·`-` 가 오는 것**을 잡는다. ⚠ 화자를 몰라 본문 첫 낱말이 우연히 이름과 같은 경우(「크리스는 …」)는 안 센다
— 이름 바로 뒤가 표기 부호일 때만이다(오탐 0 이 목표).
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import glossary
import script as script_canon


def speaker_names(disc):
    names = set(glossary.load(disc)["categories"].get("person", {}).values())
    if disc == "ed3":
        sys.path.append(os.path.join(os.path.dirname(os.path.dirname(common.ROOT)), "shared"))
        import canon

        names |= set(canon.table("speaker", disc).values())
    return sorted((n for n in names if len(n) >= 2), key=len, reverse=True)


def echoes(disc, rows=None):
    names = speaker_names(disc)
    if not names:
        return [], 0
    pat = re.compile("^(?:" + "|".join(re.escape(n) for n in names) + r")\s*[:：「『\-－]")
    bad, n = [], 0
    for (_a, member), lines in (rows if rows is not None else script_canon.load(disc)).items():
        for i, row in sorted(lines.items()):
            n += 1
            if pat.match(row["kr"].lstrip("")):
                bad.append(f"{member}#{i}: {row['kr'][:30]!r}")
    return bad, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3")
    a = ap.parse_args()
    bad, n = echoes(a.disc)
    print(f"{a.disc}: 이름 메아리 — 옮긴 {n}줄 중 본문이 이름 표기로 시작하는 것 {len(bad)}")
    for m in bad[:20]:
        print(f"  🔴 {m}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
