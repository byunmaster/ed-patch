"""고유명사 정본 — 읽기의 **유일한 통로**.

`glossary_<disc>.json` 이 정본이고, 여기 있는 건 로더뿐이다. 표기를 코드에 다시 쓰지 않는다
(DRY: 지식은 한 곳, 나머지는 포인터 — 루트 CLAUDE.md 「설계 원칙」).

방침(새턴 ED3 과 같다, 유저 확정 2026-08-25):

| 무엇                          | 어디서                          |
| ----------------------------- | ------------------------------- |
| **인물 · 지명**               | **정발** (`kr_corpus` 로 센다)  |
| 아이템 · 마법 · 몬스터 · 계급 | **자체 번역** (원문 기준)       |
| 대사 · 설명문                 | 자체 번역 (여긴 안 온다)        |

🔴 **고유명사만 여기 온다.** 문장급은 `script/`(아직 없음) 몫이고 저작권 규율도 다르다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

KINDS = ("person", "place", "monster", "item", "spell", "rank")
# 정발을 따르는 갈래 — 나머지는 자체 번역이라 정발에 없어도 정상이다.
FROM_OFFICIAL = ("person", "place")

_cache = {}


def path(disc):
    return os.path.join(common.ROOT, f"glossary_{disc}.json")


def load(disc):
    if disc not in _cache:
        with open(path(disc), encoding="utf-8") as f:
            _cache[disc] = json.load(f)
    return _cache[disc]


def flat(disc):
    """{원문: 우리 표기} — 갈래를 합친 평면 사전."""
    out = {}
    for d in load(disc)["categories"].values():
        out.update(d)
    return out


def kind_of(disc, jp):
    for k, d in load(disc)["categories"].items():
        if jp in d:
            return k
    return None
