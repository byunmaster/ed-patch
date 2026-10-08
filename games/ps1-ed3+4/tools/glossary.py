"""고유명사 정본 — 읽기의 **유일한 통로**.

정본은 `shared/canon/nouns/` 이고, 여기 있는 건 로더뿐이다. 표기를 코드에 다시 쓰지 않는다
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

# 🔴 **자기 표가 없다** — 표기는 `shared/canon`(정본, 고유명사는 `nouns/<작품>.json`)에서 읽는다(마스터 10-07·10-08 「워커는 독자 데이터를
#    못 갖는다」). ED3 는 게임 폴더에 **열쇠 목록**(`glossary_keys_ed3.json` — 실행파일 낱말 표에 실제 있는 원문, 값 없음)만 둔다.
#    열쇠를 제한하는 까닭: 정본 전체(1,000+)를 돌려주면 `hangul_map` 이 쓰는 글자 집합이 커져 글리프 자리 배정이 바뀐다(= 이미지 바이트가
#    바뀐다). ED4 는 열쇠 목록이 아직 없어 `nouns/ed4.json` 전체를 읽는다(보류 중 — 열 때 같은 전환).
KEYS = {"ed3": "glossary_keys_ed3.json"}
_SHARED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "shared")


def _canon():
    # ⚠ 맨 **뒤**에 붙인다 — 이 파일 이름(`glossary`)이 공용 옛 패키지 `shared/glossary` 에 가려지지 않게(`script.py` 와 같은 이유)
    if _SHARED not in sys.path:
        sys.path.append(_SHARED)
    import canon

    return canon


def exists(disc):
    """그 디스크의 고유명사 정본이 있나 — ED3 는 열쇠 목록, ED4 는 정본 `nouns/ed4.json`."""
    if disc in KEYS:
        return os.path.exists(os.path.join(common.ROOT, KEYS[disc]))
    try:
        _canon().nouns(disc)
        return True
    except OSError:
        return False


def load(disc):
    """{"disc", "categories": {갈래: {원문: 우리 표기}}, "evidence": {원문: 근거}} — ED3 는 열쇠 × 정본, ED4 는 정본 전체."""
    if disc not in _cache:
        nouns = _canon().nouns(disc)
        ev = nouns.get("_evidence") or nouns.get("evidence") or {}
        if disc in KEYS:
            with open(os.path.join(common.ROOT, KEYS[disc]), encoding="utf-8") as f:
                doc = json.load(f)
            cats = {}
            for kind, keys in doc["keys"].items():
                src = nouns["categories"][kind]
                missing = [jp for jp in keys if jp not in src]
                if missing:  # 열쇠가 정본에 없다 — 조용히 빼면 그 낱말이 일본어로 남는다
                    raise KeyError(f"{disc}/{kind}: 정본에 없는 열쇠 {len(missing)} — {missing[:5]}")
                cats[kind] = {jp: src[jp] for jp in keys}
        else:
            cats = {k: dict(v) for k, v in nouns["categories"].items()}
        have = {jp for d in cats.values() for jp in d}
        _cache[disc] = {"disc": disc, "categories": cats, "evidence": {jp: v for jp, v in ev.items() if jp in have}}
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
    """정본에서 직접 한 낱말 — 열쇠 목록 밖의 자리(슬롯 지명 보충)용. 없으면 None."""
    return _canon().lookup(jp, kind, disc)
