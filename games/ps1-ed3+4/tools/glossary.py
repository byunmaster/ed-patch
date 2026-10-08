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

# 🔴 ED3 는 **자기 표가 없다** — 표기는 `shared/glossary/ed3.json`(사전)에서 읽는다(마스터 10-07 「워커는 독자 데이터를
#    못 갖는다」). 게임 폴더엔 **열쇠 목록**(`glossary_keys_ed3.json` — 실행파일 낱말 표에 실제 있는 원문, 값 없음)만 둔다.
#    열쇠를 제한하는 까닭: `flat()` 이 사전 전체(1,000+)를 돌려주면 `hangul_map` 이 쓰는 글자 집합이 커져 글리프 자리
#    배정이 바뀐다(= 이미지 바이트가 바뀐다). ED4 는 아직 사전이 없어 옛 표(`glossary_ed4.json`) 그대로다.
KEYS = {"ed3": "glossary_keys_ed3.json"}
_SHARED = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "shared",
    "glossary",
)


def path(disc):
    return os.path.join(common.ROOT, KEYS.get(disc, f"glossary_{disc}.json"))


def _shared(disc):
    with open(os.path.join(_SHARED, f"{disc}.json"), encoding="utf-8") as f:
        return json.load(f)


def load(disc):
    """{"disc", "categories": {갈래: {원문: 우리 표기}}, "evidence": {원문: 근거}} — ED3 는 열쇠 × 사전."""
    if disc not in _cache:
        with open(path(disc), encoding="utf-8") as f:
            doc = json.load(f)
        if disc in KEYS:
            sh = _shared(disc)
            cats = {}
            for kind, keys in doc["keys"].items():
                src = sh["categories"][kind]
                missing = [jp for jp in keys if jp not in src]
                if missing:  # 열쇠가 사전에 없다 — 조용히 빼면 그 낱말이 일본어로 남는다
                    raise KeyError(f"{disc}/{kind}: 사전에 없는 열쇠 {len(missing)} — {missing[:5]}")
                cats[kind] = {jp: src[jp] for jp in keys}
            have = {jp for d in cats.values() for jp in d}
            doc = {
                "disc": disc,
                "categories": cats,
                "evidence": {jp: v for jp, v in sh.get("_evidence", {}).items() if jp in have},
            }
        _cache[disc] = doc
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


def lookup_shared(disc, jp, kind):
    """사전에서 직접 한 낱말 — 열쇠 목록 밖의 자리(슬롯 지명 보충)용. 없으면 None."""
    return _shared(disc)["categories"].get(kind, {}).get(jp)
