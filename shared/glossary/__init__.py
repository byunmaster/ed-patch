"""🔴 옛 입구 — 사전은 정본(`shared/canon`) 안으로 합쳤다(마스터 2026-10-08 「정본 안에 사전이 들어 있는 방식으로,
게임들은 정본 하나만 보면 된다」). 데이터는 `shared/canon/nouns/` 에 있고 여기엔 없다.

게임 도구가 아직 `import glossary` 로 부르므로 **한 라운드만** 이 다리를 둔다 — 값·순서·동작은 옛것 그대로
(편을 안 가린 `title="eiyuu"`, ui·화자 호칭을 person 으로도 돌려주는 옛 다리 포함). 각 게임이 `canon` 으로
옮기면 이 패키지를 지운다. 새 코드는 `import canon` 만 쓴다.
"""

import collections

import canon


def load(title="eiyuu"):
    """고유명사 파일 원본 — 이제 `canon.nouns(title)`."""
    return canon.nouns(title)


# ── 임시 다리: 메뉴 라벨(ui)은 정본(shared/canon)으로 옮겼다(마스터 2026-10-08) ─────────────────
#   게임 도구가 아직 `glossary` 로 ui 를 묻는다(pce·sfc·ss-ed1+2). 사전 적용 라운드 2단계에서 각 게임이
#   `canon` 을 직접 읽게 바꾸면 이 다리를 걷는다. ⚠ 이름 검사(`names.audit`)는 `load()` 를 쓰므로 ui 를
#   **안 본다** — 라벨은 정본 검사(`scripts/check/check_canon.py`)가 잰다.
def _bridge(title):
    if title != "eiyuu":
        return {}, {}

    ui, roles = dict(canon.table("ui", "ed1")), dict(canon.table("speaker", "ed1"))
    for k, v in canon.table("ui", "ed2").items():
        ui.setdefault(k, v)
    for k, v in canon.table("speaker", "ed2").items():
        roles.setdefault(k, v)
    # 화자 호칭(옛 person 의 _speaker_only 57)도 person 으로 묻는 도구가 있다(ss-ed1+2 patch_ui 이름 칸)
    return {"ui": ui, "person": roles}, dict(canon.load("ed1").get("_aliases", {}))


def _cats(title):
    cats = dict(load(title)["categories"])
    for c, extra in _bridge(title)[0].items():
        cats[c] = {**extra, **cats.get(c, {})} if c in cats else extra
    return cats


def categories(title="eiyuu"):
    return tuple(_cats(title))


def table(category, title="eiyuu"):
    """{JP: KR} — 정본 파일의 순서를 지킨다(도구가 순서에 기대는 자리가 있다)."""
    return dict(_cats(title)[category])


def lookup(jp, category=None, title="eiyuu"):
    """JP 표기 → 우리 표기. 못 찾으면 None."""
    cats = _cats(title)
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
    raw = _cats(title)[category]
    alias = {**load(title).get("_aliases", {}), **_bridge(title)[1]}
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


def kr_texts(title="eiyuu"):
    """**화면에 나가는 우리 표기**만 — 글리프 커버리지·폰트 서브셋용.

    🔴 **정본을 손으로 훑으면 화면에 안 나가는 것이 섞인다**(pce-ed1 실측 2026-09-08).
    `_aliases` 의 **값**은 `強さ@전투커맨드` 꼴이라, 정본을 평평하게 훑던 게임이 그걸
    표시 문안으로 세어 글리프 표에 `@`·「능」·「티」가 들어갔다. 게이트가 「정본에 없는
    글자」로 울어서 잡혔다.
    ⇒ **게임마다 「밑줄로 시작하는 절은 건너뛴다」를 알 게 아니라 공용이 답을 준다.**

    ⚠ 열쇠(JP)도 안 준다 — `強さ@파티메뉴` 처럼 **자리가 붙은 열쇠**가 있고, 그것도
    화면에 나가는 글자가 아니다.
    """
    return [kr for c in _cats(title).values() for kr in c.values()]


def all_names(title="eiyuu"):
    """[(범주, JP, KR)] — 전수 검사용."""
    return [(c, jp, kr) for c, d in _cats(title).items() for jp, kr in d.items()]
