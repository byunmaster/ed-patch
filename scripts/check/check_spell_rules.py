#!/usr/bin/env python3
"""맞춤법 규칙 검사 — 등급을 기계적으로 올려 생긴 비문은 실패, 붙여 쓸 한 단어를 띄운 꼴은 알림.

    python3 scripts/check/check_spell_rules.py --game sfc-ed1          # 요약
    python3 scripts/check/check_spell_rules.py --game sfc-ed1 --list   # 걸린 자리 전부

- 실패(비문): 「-옵시다」 — 청유 「-ㅂ시다」에 「-옵-」을 끼운 꼴(가시옵시다·하옵시다). 표준어에 없는 어미다.
  10-23 ss-ed1+2 가 라이아스를 하옵니다로 올리며 「가시지요」를 「가시옵시다」로 지어냈다(마스터 「문법에도 안맞네」).
- 알림(문맥 확인): 표준국어대사전에서 한 단어인 말을 띄운 꼴 — 잘되다·지나가다·한마디·은제품.
  🔴 일괄 치환하지 않는다 — 「그것 참」처럼 문맥(원문 주어)에 따라 띄움이 맞는 말이 있다(마스터 10-23
  「원문대조해서 상황에 맞게 해야지」). 그래서 실패가 아니라 알림이고, 「그것 참」은 목록에 넣지 않는다.
- 어댑터는 이름 검사와 같은 것(`games/<게임>/tools/names_corpus.py` 의 `pairs()`).

종료 코드: 0 = 비문 없음(알림만 있거나 어댑터 없음) · 1 = 비문 있음.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_names import _adapter

# 비문 — 실패
FAIL = [
    ("「-옵시다」 비문(청유형에 「-옵-」)", re.compile(r"[가-힣]옵시다")),
]
# 한 단어인데 띄운 꼴 — 알림(문맥 확인)
NOTE = [
    ("잘되다(한 단어)", re.compile(r"잘 (?:됐|되었|되어|된다|되는|될)")),
    ("지나가다(한 단어)", re.compile(r"지나 (?:가|간|갈|갔)")),
    ("한마디(한 단어)", re.compile(r"한 마디")),
    ("은제품(한 단어)", re.compile(r"은 제품")),
]


def scan(pairs, rules):
    for where, _jp, kr, *_ in pairs:
        if not kr:
            continue
        for label, rx in rules:
            m = rx.search(kr)
            if m:
                yield where, label, kr, m.start()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    mod = _adapter(a.game)
    if mod is None:
        print(f"맞춤법 규칙 검사 [{a.game}] — 어댑터 없음(이름 검사 몫)")
        return 0
    pairs = list(mod.pairs())
    bad = list(scan(pairs, FAIL))
    note = list(scan(pairs, NOTE))
    print(f"맞춤법 규칙 검사 [{a.game}] — 비문 {len(bad)} · 띄어쓰기 알림 {len(note)}")
    for tag, rows in (("✗", bad), ("ⓘ", note)):
        for where, label, kr, i in rows if a.list else rows[:10]:
            print(f"  {tag} {where}  {label}  …{kr[max(0, i - 12) : i + 16]!r}")
        if not a.list and len(rows) > 10:
            print(f"  … 외 {len(rows) - 10} (--list)")
    if note:
        print("  → 알림은 원문과 대조해 문맥에 맞게(일괄 치환 금지 — 번역 규칙 · 마스터 10-23)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
