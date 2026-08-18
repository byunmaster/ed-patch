"""고유명사 정본 — **JP 원문 → 우리 표기**. 플랫폼 공용.

정발 문안을 옮기던 시절에는 저본이 표기를 대신 맞춰 줬다. **자체 번역으로 돌아서면
(유저 확정 2026-08-18) 이 표가 유일한 기준점**이다 — 그리고 같은 세계관인 새턴·PCE 가
그대로 물려받는다. 그래서 게임이 아니라 `shared/` 에 둔다(둘째 소비자가 실재한다).

    from glossary import lookup, table
    lookup("ルディア")            # '루디아'  (범주를 안 가리면 전부에서 찾는다)
    lookup("カース", "monster")   # '카스'
    table("item")                # {JP: KR} — 순서는 정본 파일 그대로

⚠ **범주별로 둔다.** 같은 JP 가 범주에 따라 다른 것을 가리킨다(`カース` = 아이템 커스 /
몬스터 카스). 평탄한 표로 합치면 그 구별이 조용히 사라진다.

⚠ **문장은 여기 오지 않는다.** 단어 수준이라 저작권 대상이 아닌 것만 둔다.
"""

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE = {}


def load(title="eiyuu"):
    if title not in _CACHE:
        with open(os.path.join(_HERE, f"{title}.json"), encoding="utf-8") as f:
            _CACHE[title] = json.load(f)
    return _CACHE[title]


def categories(title="eiyuu"):
    return tuple(load(title)["categories"])


def table(category, title="eiyuu"):
    """{JP: KR} — 정본 파일의 순서를 지킨다(도구가 순서에 기대는 자리가 있다)."""
    return dict(load(title)["categories"][category])


def lookup(jp, category=None, title="eiyuu"):
    """JP 표기 → 우리 표기. 못 찾으면 None."""
    cats = load(title)["categories"]
    if category:
        return cats[category].get(jp)
    for c in cats.values():
        if jp in c:
            return c[jp]
    return None


def all_names(title="eiyuu"):
    """[(범주, JP, KR)] — 전수 검사용."""
    return [(c, jp, kr) for c, d in load(title)["categories"].items() for jp, kr in d.items()]
