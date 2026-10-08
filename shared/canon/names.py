"""이름 검사 — **원문에 사전 이름이 있는 자리에서, 우리 문안이 사전 표기를 쓰는가.**

    from canon.names import audit
    r = audit([("ED1SCN3#12", jp_line, kr_line), ...])
    r.units, r.translated, len(r.hits), r.mismatches

🔴 **왜 공용인가**(마스터 2026-10-07 — 「워커는 독자 데이터를 못 갖는다」). 게임마다 자기 대조
검사가 있었는데 **보는 범위가 제각각**이었다 — sfc 는 사전 표 항목(374)만 글자 그대로 비교해
**전투 문장 속 이름**(히라가나 꼴)을 원천적으로 못 봤고, md 는 번역된 9/225 블록만 찾고 「0건」을
보고했고, PS1 은 `battle.json` 이 사전보다 먼저 읽혀 **v1.0.0 에 옛 이름 15종이 나갔다.**
잣대 하나를 공용에 두고, 게임은 **「원문 줄 · 우리 줄」 쌍만** 내놓는다(어댑터).

🔴 **원문이 같을 때만 잰다**(마스터 2026-10-07). 원문에 사전 열쇠가 없으면 그 줄은 이 검사의
대상이 아니다 — 기종마다 원문이 다른 이름을 쓰면(SFC 는 그 섬을 처음부터 「ニルギド」라 부른다)
사전을 들이밀지 않는다. ⚠ **같은 말의 다른 표기는 같은 원문이다**(같은 날 마스터 — 「炎の剣」과
「ほのおのつるぎ」). 그 연결은 `_aliases` 가 든다 — 가나↔한자를 **기계로 바꾸지 않는다**(읽기를
모르는 변환은 엉뚱한 낱말을 잇는다).

⚠ **분모를 같이 돌려준다.** 「어긋남 0」은 **몇 줄을 봤는지**와 같이 읽어야 값이 있다
(`docs/patcher-checklist.md` 「검사기 자신의 커버리지」). 미번역 줄은 `translated` 에서 빠진다.

⚠ 안 재는 열쇠 — 한 글자(`男`·`船` …, 낱말 속에 너무 흔하다) · 자리 열쇠(`強さ@전투커맨드`,
문장에선 자리를 모른다) · 사전 `_no_check`(일반 낱말에 묻히는 짧은 이름 — ED3 `コール`·`ランド` …).
몇 개를 안 쟀는지도 돌려준다(`skipped_keys`).

⚠ **작품마다 사전이 다르다** — `eiyuu`(ED1·ED2) · `ed3`. 어댑터가 `TITLE` 로 고른다.
"""

import collections

from . import _norm
from . import nouns as load

Hit = collections.namedtuple("Hit", "where category jp canon ok")
Report = collections.namedtuple(
    "Report", "units translated hits mismatches pending skipped_keys unlabeled"
)

MIN_KEY = 2
LABEL_CATS = ("ui",)

# 가타카나 낱말 경계 — 가타카나만으로 된 열쇠는 앞뒤가 가타카나면 **다른 낱말 속**이다.
#   실측(pce 2026-10-07): 파티원 `ロー` 가 몬스터 `キャリオンクローラー` 속에서 7번 잡혔다.
#   ⚠ 한자 열쇠엔 경계를 안 둔다 — `ルディア城` 처럼 붙어서 한 이름이 되는 게 정상이다.
_KATA = set(
    "ァアィイゥウェエォオカガキギクグケゲコゴサザシジスズセゼソゾタダチヂッツヅテデトドナニヌネノ"
    "ハバパヒビピフブプヘベペホボポマミムメモャヤュユョヨラリルレロヮワヰヱヲンヴヵヶーｰ"
    # 반각 가타카나(ｦ~ﾟ) — sfc 원문이 반각이라 `ﾛｰ` 가 `ｷｬﾘｵﾝｸﾛｰﾗｰ` 속에서 잡혔다(10-07)
    + "".join(chr(c) for c in range(0xFF66, 0xFFA0))
)
# ⚠ 가운뎃점은 이름 **안**에는 있어도(`ア・バータル`) 경계로는 안 친다 — `ジュリオ・クリス` 의 두 이름이 산다.
# 몬스터 기호 꼬리 — 사전엔 `…Ａ` 꼴만 있는데 문장엔 맨 이름이 나온다(pce 같은 날). 맨 열쇠를 만들어 잰다.
_SUFFIX = "ＡＢＣＤABCD"


# 전각 숫자·로마자 → 반각 — 문안은 반각으로 쓰고 화면이 전각으로 그리는 게임이 있다(ss-ed3 `２층`/`2층` 49건, 10-07).
_HALF = str.maketrans(
    {chr(0xFF10 + i): chr(0x30 + i) for i in range(10)}
    | {chr(0xFF21 + i): chr(0x41 + i) for i in range(26)}
    | {chr(0xFF41 + i): chr(0x61 + i) for i in range(26)}
)


def _flat(t):
    """띄어쓰기·줄바꿈을 지우고 전각 숫자·로마자를 반각으로 — 줄바꿈이 이름을 가르는 자리(`붉은\n슬라임`,
    ss-ed1+2) · 숫자 폭만 다른 자리(`２층`/`2층`, ss-ed3)가 같은 표기다."""
    return "".join(t.split()).translate(_HALF)


# ── 대사 속 지명 꼴 (마스터 판정 2026-09-27 「두 기종 공통, 대사에만」 · 10-07 「대사·비대사를 나눠라」) ──
# 사전 place 값은 **지명 칸 꼴**(HUD·워프·입장 배너 — 붙여 쓴다). 대사는 아래 셋으로 띄운다:
#   ① 「성」·「섬」은 붙인다 — `루디아성`·`해적섬`
#   ② 「~의」 뒤는 띄운다 — `바람의 탑`·`사피아의 호수`·`나락의 입`
#   ③ 나머지 종류 말은 띄운다 — `크루즈 마을`·`베르가 광산`·`네리아 항구`
# 정본은 docs/naming.md 「지명 접미」 절. 첫 구현은 새턴 `games/ss-ed1+2/tools/names.py` 였다(둘째 소비자 = 이 검사).
KIND_WORDS = (
    "초가집",
    "마을",
    "항구",
    "요새",
    "광산",
    "동굴",
    "호수",
    "통로",  # ED3 地下通路 → 대사 「지하 통로」(10-07)
    "섬",
    "성",
    "탑",
    "묘",
    "집",
    "길",
    "방",
)
ATTACHED_KINDS = ("성", "섬")
DIALOG, SLOT = "dialog", "slot"


def dialog_place(kr):
    """지명 칸 꼴 → 대사 꼴. 이미 띄었거나 규칙에 안 걸리면 그대로."""
    if not kr or " " in kr or "　" in kr or kr.endswith(ATTACHED_KINDS):
        return kr
    i = kr.rfind("의", 1, len(kr) - 1)
    if i > 0:
        return kr[: i + 1] + " " + kr[i + 1 :]
    for w in KIND_WORDS:
        if kr.endswith(w) and len(kr) > len(w):
            return kr[: -len(w)] + " " + w
    return kr


def _spaced(t):
    """대사 비교용 — 공백·전각 공백·줄바꿈을 모두 반각 공백 하나로(줄바꿈은 띄어쓰기 자리에서 난다)."""
    return " ".join(t.split()).translate(_HALF)


def _key(t):
    """열쇠 정규화 — 장음 부호를 맞추고 공백을 지운다(원문 쪽과 같은 규칙이어야 맞는다).
    ⚠ 원문만 공백을 지우면 `やさしそうな おばあさん` 같은 띈 열쇠가 영영 안 맞는다."""
    return _flat(_norm(t))


def _is_letter(c):
    """가나·한자·한글·영문자 — 이것과 붙어 있으면 낱말 속이다(라벨 판정)."""
    return c.isalpha()


_PARTICLE = set("のをはがにともでへや")


def _standalone(s, i, j):
    """라벨이 **낱말 하나로** 서 있나 — 앞은 구분자, 뒤는 구분자·끝 또는 「조사 한 글자 + 구분자·끝」.

    일본어는 조사가 붙어 쓰인다 — `、すばやさの４つ` 의 라벨은 살리고(md 실측), 대사 속
    `はいどうぞ`·`そのため`·`いいえまだ`·`守るもの` 는 뒤에 낱말이 이어지니 뺀다(ss-ed1+2 실측 42건,
    2026-10-07). 앞 경계만 보던 때는 이 넷이 다 라벨로 잡혔다.
    """
    if i > 0 and _is_letter(s[i - 1]):
        return False
    if j == len(s) or not _is_letter(s[j]):
        return True
    return s[j] in _PARTICLE and (j + 1 == len(s) or not _is_letter(s[j + 1]))


def _kata_only(k):
    return all(c in _KATA or c == "・" for c in k)


def _hira_only(k):
    return all("\u3041" <= c <= "\u309f" for c in k)


def _slot_forms(data):
    """{정규화 원문: {칸 꼴…}} — `원문@자리` 열쇠의 값. 칸(slot 갈래)에선 이것도 정답이다.

    칸 폭 때문에 정본 표기가 안 들어가는 자리는 정본에 `원문@자리` 로 그 칸의 꼴을 둔다(마스터 10-08 —
    「재배치로 가능하면 재배치하고 안되면 제안이나 내 제안으로」, 예: `オビス３の杖@아이템칸` = 「오비스3 지팡이」).
    대사 갈래에선 안 받는다 — 대사엔 칸이 없다.
    """
    out = {}
    for tbl in data["categories"].values():
        for jp, kr in tbl.items():
            if "@" in jp:
                out.setdefault(_key(jp.split("@", 1)[0]), set()).add(kr)
    return out


def _keys(data):
    """{정규화 원문: (범주, 정본 열쇠, {정본 표기…})} + 안 잰 열쇠 수.

    같은 원문이 범주마다 다르면(`カース` = 아이템 커스 / 몬스터 카스) 문장에선 어느 쪽인지
    모르므로 **어느 표기든** 받는다.
    """
    keys, skipped = {}, 0
    quiet = set(data.get("_no_check", ()))
    for cat, tbl in data["categories"].items():
        for jp, kr in tbl.items():
            if len(jp) < MIN_KEY or "@" in jp or jp in quiet:
                skipped += 1
                continue
            k = _key(jp)
            if k in keys:
                keys[k][2].add(kr)
            else:
                keys[k] = (cat, jp, {kr})
    # 맨 이름 — 꼬리를 뗀 원문이 사전에 따로 없을 때만, 우리 표기도 같은 꼬리를 뗀다
    for cat, tbl in data["categories"].items():
        for jp, kr in tbl.items():
            if len(jp) > MIN_KEY and jp[-1] in _SUFFIX and kr.rstrip()[-1:] in _SUFFIX:
                base, kbase = _key(jp[:-1]), kr.rstrip()[:-1].rstrip()
                if base not in keys and base not in quiet and kbase:
                    keys[base] = (cat, jp[:-1], {kbase})
    for alias, target in data.get("_aliases", {}).items():
        a, t = _key(alias), _key(target)
        if "@" in alias or len(alias) < MIN_KEY or t not in keys or a in keys:
            continue
        keys[a] = keys[t]
    return keys, skipped


def _speaker_only(data):
    return [_key(k) for k in data.get("_speaker_only", {}).get("keys", ())]


def _pending(data):
    return {
        _key(jp)
        for cat, tbl in data.get("_pending", {}).items()
        if not cat.startswith("_")
        for jp in tbl
    }


def find(jp_text, keys):
    """원문에서 사전 열쇠를 **긴 것부터, 겹치지 않게** 찾는다 — `[(시작, 정규화 열쇠)]`.

    짧은 열쇠가 긴 이름 속에서 따로 잡히지 않게 한다(`ルディア` 가 `ルディア城` 안에서 또
    잡히면 한 이름이 둘로 센다).
    """
    s = _flat(_norm(jp_text))
    # 줄바꿈·공백 자리(지운 뒤 글자 위치) — 히라가나만으로 된 열쇠(가나 별칭 `てした`)는 그걸 못 넘는다:
    #   `けっして　したごころ`(전각 공백 = 일본어 원문의 낱말 구분)가 `てした` 로 잡혔다(sfc 실측 10-08). 한자·가타카나 이름은 원문이 줄 중간에서
    #   끊기도 해(`붉은⏎슬라임`) 그대로 넘게 둔다.
    breaks, n = set(), 0
    for ch in _norm(jp_text):
        if ch.isspace():
            breaks.add(n)  # 줄바꿈 · 전각 공백(일본어 원문의 낱말 구분) · 공백
        else:
            n += 1
    taken = [False] * len(s)
    out = []
    for k in sorted(keys, key=len, reverse=True):
        i = s.find(k)
        while i != -1:
            j = i + len(k)
            inside = _kata_only(k) and (
                (i > 0 and s[i - 1] in _KATA) or (j < len(s) and s[j] in _KATA)
            )
            # 열쇠 자체가 띈 말(`やさしい おばば`)이면 그 띄어쓰기는 넘어도 된다
            if _hira_only(k) and any(b in breaks for b in range(i + 1, j)):
                v = keys[k] if isinstance(keys, dict) else None
                orig = v[1] if isinstance(v, tuple) and len(v) > 1 else ""
                if not any(c.isspace() for c in str(orig)):
                    inside = True
            if not inside and not any(taken[i:j]):
                out.append((i, k))
                for t in range(i, j):
                    taken[t] = True
            i = s.find(k, i + 1)
    return sorted(out)


def audit(pairs, title="eiyuu", data=None):
    """`pairs` = `[(자리, 원문 줄, 우리 줄 또는 None[, 갈래])]`. None 은 미번역 — 분모에만 든다.

    갈래(마스터 10-07 「대사·비대사를 나눠라」): `"dialog"`(대사) · `"slot"`(HUD·워프·배너·메뉴·표 —
    비대사). **대사 속 지명은 띄어쓰기까지 본다**(`dialog_place`). 그 밖은 띄어쓰기를 무시한다 —
    칸은 기종마다 띄어쓰기 규칙이 따로 있다(새턴 HUD 전각 공백 등). 갈래를 안 준 줄은 예전처럼
    띄어쓰기를 무시하고 `unlabeled` 로 센다(어댑터가 갈래를 붙이면 0 이 된다).
    조사가 붙는 건 부분 일치라 저절로 받는다.
    """
    data = data or load(title)
    keys, skipped = _keys(data)
    slot_forms = _slot_forms(data)
    pend = _pending(data)
    units = translated = 0
    hits, pending = [], []
    unlabeled = 0
    for item in pairs:
        where, jp, kr = item[:3]
        kind = item[3] if len(item) > 3 else None
        units += 1
        if kr is None:
            continue
        translated += 1
        if kind is None:
            unlabeled += 1
        flat = _flat(kr)
        spaced = _spaced(kr)
        s = _flat(_norm(jp))
        speaker = set(_speaker_only(data))
        for i, k in find(jp, keys):
            cat, canon_jp, canon = keys[k]
            # 라벨(ui)은 **앞이 글자가 아닐 때만** 잰다 — 문장 속 `はい`(時は+いつでも)·동사 `守る`
            #   는 라벨이 아니다(md 실측 2026-10-07). 줄 전체로 좁혔더니 `HP・攻撃力・すばやさ` 같은
            #   나열 속 라벨이 빠졌다(같은 날) — 그래서 「줄 전체」가 아니라 「구분자 사이」다.
            # 🔴 라벨은 **칸에서만** 잰다 — 대사 갈래의 はい·いいえ·うん 은 대답이지 메뉴 라벨이 아니다
            #   (마스터 10-07 「대답·감탄사는 전 기종 똑같이 적용되는 거야?」 — 줄마다 예외를 적는 대신
            #   규칙 하나로). 갈래 없는 줄만 아래 경계 규칙으로 가른다.
            # 숫자로 끝나는 열쇠(`その１`) 뒤에 한자가 붙으면 수량 표현이다 — `その１本`(그 한 가닥)은 이름이 아니다
            #   (ss-ed3 실측 · 마스터 판정 10-07)
            nxt = s[i + len(k) : i + len(k) + 1]
            if k[-1:].isdigit() and nxt and "\u4e00" <= nxt <= "\u9fff":
                continue
            if cat in LABEL_CATS and kind == DIALOG:
                continue
            if cat in LABEL_CATS and not _standalone(s, i, i + len(k)):
                continue
            # 「~の町長」·「~の村長」은 직함(시장·촌장)이지 지명이 아니다 — `マスクーンの町` 가 `町長` 속에서
            #   잡혔다(ss-ed1+2·PS1 실측 2026-10-07)
            if cat == "place" and k[-1:] in ("町", "村") and s[i + len(k) : i + len(k) + 1] == "長":
                continue
            # 역할 보통명사(아이·상인·할아버지…)는 **화자 이름 칸에서만** — 줄 전체가 그 열쇠일 때
            #   별칭으로 들어온 열쇠(`とうぞく`→盗賊)도 정본 열쇠로 본다 — `だいとうぞくゲイル` 속 `とうぞく` 를
            #   화자 호칭으로 뜯어 읽었다(sfc 실측 10-08)
            if (k in speaker or _key(canon_jp) in speaker) and s != k:
                continue
            if kind == DIALOG and cat == "place":
                # 대사 속 지명은 **띄어쓰기까지** 본다(대사 꼴) — 칸 꼴로 붙여 쓰면 어긋남
                # 사전 `_dialog_as_is` — 규칙대로 띄우면 안 되는 한 낱말(`天儀室` 천의실, 마스터 10-07)
                as_is = canon_jp in data.get("_dialog_as_is", {}).get("keys", ())
                want = set(canon) if as_is else {dialog_place(c) for c in canon}
                ok = any(_spaced(w) in spaced for w in want)
                hits.append(Hit(where, "place@대사", canon_jp, "/".join(sorted(want)), ok))
            else:
                want = set(canon) | (slot_forms.get(k, set()) if kind == SLOT else set())
                ok = any(_flat(c) in flat for c in want)
                hits.append(Hit(where, cat, canon_jp, "/".join(sorted(want)), ok))
            if k in pend or _key(canon_jp) in pend:
                pending.append(hits[-1])
    mism = [h for h in hits if not h.ok]
    return Report(units, translated, hits, mism, pending, skipped, unlabeled)
