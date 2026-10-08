"""정본 — 게임이 보는 **단 하나의 입구**. 고유명사(사전)와 공통 문안을 함께 든다. 플랫폼 공용.

마스터 2026-10-08: 처음엔 사전(`shared/glossary`, 고유명사)과 정본(그 밖의 공통 문안)을 따로 뒀다가, 같은 날
**「정본 안에 사전이 들어 있는 방식으로 — 게임들은 정본 하나만 보면 된다」**로 합쳤다.
ED1·ED2 문안은 PS1 번역으로, ED3 는 새턴 번역으로 시작했고 **PS1 을 포함한 전 기종이 원문이 같을 때 이걸
따른다** — PS1 의 사본이 아니라 정본이 하나다.

    shared/canon/
      nouns/eiyuu.json   고유명사 — ED1·ED2 공통 세계(인물·지명·아이템·몬스터). 편마다 두 벌 두지 않는다
      nouns/ed3.json     고유명사 — ED3
      ed1/ed2/ed3.json   공통 문안 — 메뉴 라벨(ui) · 화자 호칭(speaker) · 시스템 · 전투 · 장 제목

    from canon import lookup, table
    lookup("ルディア", "place", "ed2")       # '루디아'   (ED1·ED2 는 nouns/eiyuu 에서)
    lookup("その他", "ui", "ed1")            # '기타'
    table("speaker", "ed3")                  # {JP: KR}

⚠ 작품마다 파일이 하나다(`ed1` · `ed2` · `ed3`) — 같은 원문이 ED1 과 ED2 에서 다르게 옮겨진 전투
문구가 있다(PS1 실측 10-08: 4건). 사전처럼 `eiyuu` 하나로 합치면 그 구별이 사라진다.
⚠ 운영은 사전과 같다 — 워커는 안 고친다, 관리자가 main 에서(마스터 확인 뒤), 원문이 같을 때만 적용.
"""

import collections
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE = {}
TITLES = ("ed1", "ed2", "ed3")
LABELS = ("ui", "speaker", "chapter")  # 줄(칸) 전체로 재는 범주 — chapter = 장 제목(마스터 10-08)
PHRASES = ("system", "battle")  # 문장 속 조각으로 재는 범주


# 작품 → 고유명사 파일. ED1·ED2 는 같은 세계라 한 벌(`eiyuu`)을 같이 쓴다 — 편마다 두면 한쪽만 고쳐진다
#   (PS1 v1.0.0 에 옛 몬스터 이름 15종이 나간 게 그 꼴이었다, 10-07).
# ⚠ ED4 고유명사(`nouns/ed4.json`)는 ps1-ed3+4 의 자기 표를 그대로 옮겨 둔 것이다(10-08, 게임 폴더에 표 금지) —
#   ED4 는 ED3 뒤라 아직 검토 전이고 공통 문안 파일(`ed4.json`)도 없다.
WORLD = {"ed1": "eiyuu", "ed2": "eiyuu", "eiyuu": "eiyuu", "ed3": "ed3", "ed4": "ed4"}


def _read(path):
    if path not in _CACHE:
        with open(os.path.join(_HERE, path), encoding="utf-8") as f:
            _CACHE[path] = json.load(f)
    return _CACHE[path]


def load(title):
    """공통 문안 파일(`ed1`·`ed2`·`ed3`) 원본. 고유명사는 `nouns(title)`."""
    if title in _CACHE:  # 테스트가 가짜 데이터를 꽂는 자리
        return _CACHE[title]
    return _read(f"{title}.json")


def nouns(title="eiyuu"):
    """고유명사 파일 원본 — `ed1`·`ed2`·`eiyuu` → `nouns/eiyuu.json`, `ed3` → `nouns/ed3.json`."""
    return _read(f"nouns/{WORLD.get(title, title)}.json")


def _phrase_cats(title):
    """공통 문안 범주. `eiyuu`(편을 안 가린 옛 부름)는 ED1 위에 ED2 에만 있는 열쇠를 더한다."""
    if title == "eiyuu":
        out = {c: dict(v) for c, v in load("ed1")["categories"].items()}
        for c, v in load("ed2")["categories"].items():
            for k, x in v.items():
                out.setdefault(c, {}).setdefault(k, x)
        return out
    if (title in WORLD and os.path.exists(os.path.join(_HERE, f"{title}.json"))) or title in _CACHE:
        return load(title)["categories"]
    return {}


def _cats(title):
    """고유명사 범주 + 공통 문안 범주. 이름이 겹치지 않는다(person·place·item·monster… / ui·speaker·…)."""
    cats = {}
    if WORLD.get(title):
        cats.update(nouns(title)["categories"])
    cats.update(_phrase_cats(title))
    return cats


def categories(title="ed1"):
    return tuple(_cats(title))


def table(category, title="ed1"):
    """{JP: KR} — 파일 순서를 지킨다(도구가 순서에 기대는 자리가 있다)."""
    return dict(_cats(title).get(category, {}))


def lookup(jp, category=None, title="ed1"):
    """JP → 우리 표기. 범주를 안 주면 전부에서 찾는다. 못 찾으면 None."""
    cats = _cats(title)
    if category:
        return cats.get(category, {}).get(jp)
    for c in cats.values():
        if jp in c:
            return c[jp]
    return None


def aliases(title="ed1"):
    """같은 원문의 다른 표기(가나↔한자 등) → 정본 열쇠. 고유명사 별칭 + 문안 별칭."""
    out = dict(nouns(title).get("_aliases", {})) if WORLD.get(title) else {}
    for t in ("ed1", "ed2") if title == "eiyuu" else (title,):
        if t in WORLD and t != "eiyuu" and os.path.exists(os.path.join(_HERE, f"{t}.json")):
            out.update(load(t).get("_aliases", {}))
    return out


def all_names(title="ed1"):
    """[(범주, JP, KR)] — 고유명사만, 전수 검사용."""
    return [(c, jp, kr) for c, d in nouns(title)["categories"].items() for jp, kr in d.items()]


# ⚠ **장음 부호가 자료마다 다르다** — `リ－ダ－`(전각 하이픈)과 `リーダー`(장음)는 같은 말이다(sfc 실측 09-08).
#   별칭에 하나씩 올리지 말고 **잴 때 정규화한다.**
_DASH = str.maketrans({"－": "ー", "‐": "ー", "‑": "ー", "―": "ー", "─": "ー", "-": "ー"})


def _norm(k):
    """열쇠 정규화 — 장음 부호만 맞춘다. 뜻을 건드리지 않는다."""
    return k.translate(_DASH)


LabelCheck = collections.namedtuple("LabelCheck", "diff unmatched")


def diff_labels(mine, category="ui", title="ed1"):
    """게임 라벨 `{JP: 우리 표기}` 를 정본과 견준다 — `(다른 것, 못 견준 것)`.

    🔴 **`unmatched` 를 반드시 같이 본다** — 정본에 없는 열쇠를 조용히 건너뛰면 가나 전용 게임에서 44 중 6 만
    견주고도 「갈린 데 둘뿐」으로 보였다(sfc 실측 09-08). 열쇠는 별칭·장음 정규화를 거친다.
    자리가 붙은 열쇠(`強さ@전투커맨드`)는 자리를 대야 견준다 — 맨 `強さ` 는 `unmatched` 다.
    """
    raw = table(category, title)
    canon_ = {_norm(k): v for k, v in raw.items()}
    alias = {_norm(k): _norm(v) for k, v in aliases(title).items()}
    diff, unmatched = [], []
    for jp, ours in mine.items():
        k = _norm(jp)
        key = k if k in canon_ else alias.get(k)
        if key is None or key not in canon_:
            unmatched.append(jp)
        elif canon_[key] != ours:
            diff.append((jp, canon_[key], ours))
    return LabelCheck(diff, unmatched)


def pending(title):
    """마스터 판정 대기 — `{범주: {원문: [후보…]}}`."""
    return {k: v for k, v in load(title).get("_pending", {}).items() if not k.startswith("_")}


def kr_texts(title="ed1"):
    """화면에 나가는 우리 표기만 — 글리프 커버리지용(고유명사 + 문안). 자리표(`{name}`)·열쇠는 뺀다."""
    return [_SLOT.sub("", v) for c in _cats(title).values() for v in c.values()]


# ── 문장 조각(system·battle) 대조 ──────────────────────────────────────────────
_SLOT = re.compile(r"\{(name|item|spell|n|m|unit)\}")
# 병기 조사 — 게임이 런타임에 접은 꼴(「은」·「는」)도, 병기 그대로(「은(는)」)도 같은 것으로 친다
_PAIR = re.compile(r"(은|이|을|과|와|으로)\((는|가|를|와|과|로)\)")


def _jp_pattern(key):
    """원문 열쇠 → 정규식. 자리표는 아무 글자열(최소)."""
    parts = _SLOT.split(key)
    out = []
    for i, p in enumerate(parts):
        if i % 2:
            # 수 자리(`{n}`·`{m}`)는 숫자만 — `{n}下がった` 가 「ﾎﾟｲﾝﾄ下がった」에 걸렸다(md 실측 10-08)
            out.append("[0-9０-９]+" if p in ("n", "m") else ".+?")
        else:
            out.append(re.escape(p))
    return "".join(out)


def _kr_pattern(val):
    """우리 값 → 정규식. 자리표는 아무 글자열, 병기 조사는 셋 중 아무거나, 공백은 느슨하게."""
    out = []
    pos = 0
    for m in re.finditer(
        r"\{(?:name|item|spell|n|m|unit)\}|(은|이|을|과|와|으로)\((는|가|를|와|과|로)\)|\s+", val
    ):
        out.append(re.escape(val[pos : m.start()]))
        tok = m.group(0)
        if tok.startswith("{"):
            out.append(".+?")
        elif tok.strip() == "":
            out.append(r"\s*")
        else:
            a, b = m.group(1), m.group(2)
            out.append(f"(?:{re.escape(tok)}|{a}|{b})")
        pos = m.end()
    out.append(re.escape(val[pos:]))
    return "".join(out)


_PARTICLES = set("をはがにのとでもへや")


def _flat(s):
    return re.sub(r"\s+", "", s or "")


def audit(pairs, title):
    """게임의 「원문 줄 · 우리 줄」을 정본으로 잰다 — 이름 검사와 같은 `Report` 꼴.

    - **ui · speaker** 는 이름 검사 잣대(`canon.names.audit`)를 그대로 쓴다 — 라벨은 칸에서만·구분자 사이,
      화자 호칭은 줄 전체가 그 열쇠일 때만(이름 칸).
    - **system · battle** 은 문장 조각이다 — 원문 열쇠(자리표 포함)가 원문 줄에 있으면 우리 줄에 정본 값
      (자리표·병기 조사·공백을 느슨하게)이 있어야 한다.
    판정 대기(`_pending`)인 열쇠는 어느 값이든 통과시키고 `pending` 으로 따로 센다.
    """
    from .names import Hit, Report
    from .names import audit as _names_audit

    data = load(title)
    cats = data["categories"]
    pend = pending(title)
    labels = {
        "categories": {c: cats.get(c, {}) for c in LABELS},
        "_speaker_only": {"keys": list(cats.get("speaker", {}))},
        "_aliases": data.get("_aliases", {}),
        "_pending": {c: pend.get(c, {}) for c in LABELS},
    }
    pairs = list(pairs)
    r = _names_audit(pairs, title=title, data=labels)
    hits, mism, pendhits = list(r.hits), list(r.mismatches), list(r.pending)
    # 판정 대기 라벨은 실패로 안 친다
    pend_keys = {k for c in LABELS for k in pend.get(c, {})}
    mism = [h for h in mism if h.jp not in pend_keys]

    phrases = []
    # 칸 꼴 — `원문@자리` 의 값도 그 원문의 정답으로 받는다(칸이 모자란 기종, 마스터 확인 값 10-08)
    slot_alts = {}
    for c in PHRASES:
        for k, v in cats.get(c, {}).items():
            if "@" in k:
                slot_alts.setdefault((c, k.split("@", 1)[0]), []).append(v)
    for c in PHRASES:
        for k, v in cats.get(c, {}).items():
            if "@" in k:
                continue
            lit = max(_SLOT.split(k)[::2], key=len)
            # 글자(가나·한자)가 셋 미만인 열쇠도 안 잰다 — `{name}⏎･ ･ ･ ･`(이름창+말줄임)·`{name}には ･ ･ ･` 가
            #   장면 대사에 우연히 붙었다(PS1 실측 10-08: 12건)
            if sum(1 for ch in k if "\u3041" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff") < 3:
                continue
            if len(_flat(lit)) < 4:
                continue  # 너무 짧은 조각(「しかし {name}」·「{name}だ!!」)은 씬 대사 한 줄과도 똑같다
            # 🔴 **줄 전체로** 잰다 — 조각을 문장 속에서 찾으면 씬 대사의 「しかし」·「何もない」까지 걸린다
            #   (PS1 실측 10-08: 자기 씨앗으로 쟀는데 263 어긋남, 전부 씬 대사). 엔진이 이름 뒤에 붙여 찍는
            #   조각(`をもっていた。`)은 앞에 이름 자리가 숨어 있다.
            jp_k = _flat(k)
            # 숨은 이름 자리는 **이름처럼 생긴 것**만 — 짧고 문장부호·공백이 없다(「催眠術を使った。」 같은
            #   대사 한 줄이 「を使った。」 조각에 걸렸다, ss-ed1+2 실측 10-08)
            head = r"[^。、！？!?\s]{1,10}?" if jp_k[:1] in _PARTICLES else ""
            kr_head = ".*?" if head else ""
            phrases.append(
                (
                    c,
                    k,
                    v,
                    _flat(lit),
                    re.compile("^" + head + _jp_pattern(jp_k) + "$"),
                    re.compile("^" + kr_head + _kr_pattern(_flat(v)) + "$"),
                )
            )
    # 구체적인 열쇠 먼저 — 자리표를 뺀 글자 수로 센다. 원문 길이로 세면 「しかし{name}では…」(자리표 6자)가
    #   「しかし何もないでは…」보다 앞서 같은 줄을 먼저 잡았다(PS1 실측 10-08)
    phrases.sort(key=lambda t: -len(_SLOT.sub("", t[1])))
    for item in pairs:
        where, jp, kr = item[:3]
        if kr is None:
            continue
        fj = _flat(jp)
        for c, k, v, lit, jre, kre in phrases:
            if lit not in fj or not jre.search(fj):
                continue
            alts = pend.get(c, {}).get(k)
            fk = _flat(kr)
            ok = bool(kre.search(fk)) or any(
                re.search("^.*?" + _kr_pattern(_flat(a)) + "$", fk)
                for a in (alts or []) + slot_alts.get((c, k), [])
            )
            h = Hit(where, c, k, v, ok)
            hits.append(h)
            if alts:
                pendhits.append(h)
            elif not ok:
                mism.append(h)
            break  # 한 줄엔 가장 긴 열쇠 하나만 — 「しかも {name}も一緒だ!!」 줄을 짧은 「{name}も一緒だ!!」 가 또 재지 않게
    return Report(r.units, r.translated, hits, mism, pendhits, r.skipped_keys, r.unlabeled)
