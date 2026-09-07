"""고유명사 정본 — **JP 원문 → 우리 표기**. 플랫폼 공용.

정발 문안을 옮기던 시절에는 저본이 표기를 대신 맞춰 줬다. **자체 번역으로 돌아서면
(유저 확정 2026-08-18) 이 표가 유일한 기준점**이다 — 그리고 같은 세계관인 새턴·PCE 가
그대로 물려받는다. 그래서 게임이 아니라 `shared/` 에 둔다(둘째 소비자가 실재한다).

    from glossary import lookup, table
    lookup("ルディア")            # '루디아'  (범주를 안 가리면 전부에서 찾는다)
    lookup("カース", "monster")   # '카스'
    diff_labels({"その他": "그외"})  # LabelCheck(diff=[('その他','기타','그외')], unmatched=[])
    table("item")                # {JP: KR} — 순서는 정본 파일 그대로

⚠ **범주별로 둔다.** 같은 JP 가 범주에 따라 다른 것을 가리킨다(`カース` = 아이템 커스 /
몬스터 카스). 평탄한 표로 합치면 그 구별이 조용히 사라진다.

⚠ **문장은 여기 오지 않는다.** 단어 수준이라 저작권 대상이 아닌 것만 둔다.
"""

import collections
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


# ⚠ **장음 부호가 자료마다 다르다** — 정본이 `リ－ダ－`(전각 하이픈 U+FF0D)로 들고 있는데
#   게임은 `リーダー`(장음 U+30FC)로 든다. 같은 말인데 열쇠가 안 맞아 **조용히 안 재진다**
#   (sfc-ed1 실측 2026-09-08 — `メッセージ`·`リーダー` 둘이 그 이유로 빠졌다).
#   ⇒ 별칭에 하나씩 올리지 말고 **잴 때 정규화한다.** 별칭은 낱말을 잇는 것이지 부호를
#     잇는 자리가 아니다.
_DASH = str.maketrans({"－": "ー", "‐": "ー", "‑": "ー", "―": "ー", "─": "ー", "-": "ー"})


def _norm(k):
    """열쇠 정규화 — 장음 부호만 맞춘다. 뜻을 건드리지 않는다."""
    return k.translate(_DASH)


LabelCheck = collections.namedtuple("LabelCheck", "diff unmatched")


def diff_labels(mine, category="ui", title="eiyuu"):
    """게임 라벨을 정본과 견준다 — `(다른 것, 못 견준 것)`.

    `mine` 은 게임의 **{JP 원문: 우리 표기}** 다.

    🔴 **돌려주는 값이 둘인 이유** — 종전엔 다른 것만 돌려줬고, 정본에 없는 열쇠는
    **조용히 건너뛰었다.** 그래서 **가나 전용 게임에서 44 중 6 만 견주고도 「갈린 데
    둘뿐」으로 보였다**(sfc-ed1 실측 2026-09-08 — 정본 열쇠가 한자 `捨てる` 인데 그
    게임은 `すてる` 다). **검사기 자신의 커버리지**를 안 보면 초록불이 거짓말을 한다
    (`docs/patcher-checklist.md` 의 그 축).
    ⇒ **`unmatched` 를 반드시 같이 본다.** 비었는지가 아니라 **몇 개를 못 견줬는지**가
      그 초록불의 값을 정한다.

    ⚠ 열쇠는 `_aliases` 를 거쳐 정규화된다 — 같은 말의 가나·한자 표기를 이어 준다.
    ⚠ 정본에 없는 라벨은 **갈린 게 아니라 없는 것**이다. 게임에만 있는 라벨이 정상이므로
      `unmatched` 는 실패가 아니라 **읽을 값**이다.

    🔴 **한 원문이 자리마다 다른 말이면 열쇠가 `원문@자리` 다**(`強さ@전투커맨드`). 맨
    `強さ` 는 정본에 **없고**, 그래서 자리를 안 댄 채로 물으면 `unmatched` 로 나온다 —
    평면으로 담으면 셋이 한 말로 뭉개지고 원문으로 뿌리면 파티 메뉴가 「강함」으로
    덮인다(실측 사고: 능력치 창에 「상태 6」, 2026-08-14). **틀린 잣대로 재느니 안 재는
    게 낫다.**

    ⚠ **칸이 다르면 갈라 쓸 수 있다** — 정본은 표기를 정할 뿐이고, 안 들어가는 게임은
    줄여 쓰고 **자기 대장에 적는다**(이름 정본과 같은 규약). 그러니 이 함수는 **다름을
    알릴 뿐 옳고 그름을 말하지 않는다** — 게이트가 그 판단을 한다.
    """
    raw = load(title)["categories"][category]
    alias = load(title).get("_aliases", {})
    canon = {_norm(k): v for k, v in raw.items()}
    alias = {_norm(k): _norm(v) for k, v in alias.items()}
    diff, unmatched = [], []
    for jp, ours in mine.items():
        k = _norm(jp)
        key = k if k in canon else alias.get(k)
        if key is None or key not in canon:
            unmatched.append(jp)
        elif canon[key] != ours:
            diff.append((jp, canon[key], ours))
    return LabelCheck(diff, unmatched)


def all_names(title="eiyuu"):
    """[(범주, JP, KR)] — 전수 검사용."""
    return [(c, jp, kr) for c, d in load(title)["categories"].items() for jp, kr in d.items()]
