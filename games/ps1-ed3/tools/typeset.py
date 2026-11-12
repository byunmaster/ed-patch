"""조판 — 우리 문안을 이 게임의 창 규격에 맞춰 줄로 나눈다.

엔진은 **자동 개행을 안 한다** — 줄바꿈은 문안 안의 `0x01`(=`\\n`)이 정한다(ED3 PoC 실측).
그래서 「몇 칸까지 되나」는 코드가 아니라 **원본이 실제로 쓴 값**에서 온다.

    ED3  줄 최대 30칸 · 창 최대 5줄   (조각 33,958 · 줄 44,834 실측)
    ED4  줄 최대 35칸 · 창 최대 5줄   (조각 24,390 · 줄 33,524 실측)

🔴 **상수를 원본에서 다시 잰다**(`--check`). 「24칸」으로 알고 있던 값이 실은 30/35 였다 —
   앞서 잰 것은 표본이 좁았다. 상수를 박아 두기만 하면 언제 틀렸는지 모른다.

⚠ 이건 **상한이지 목표가 아니다.** 원본이 30칸을 쓴 자리가 58줄뿐이니(0.13%), 그 폭을
   기본으로 삼으면 대부분의 창에서 글자가 창 밖으로 나갈 수도 있다 — 창은 자리마다 다르다.
   ⇒ 조판은 **그 조각의 원문이 쓴 폭**을 넘지 않게 맞추는 것이 1급이고, 상한은 그 위의 뚜껑이다.
"""

import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import common

from shared.text import krwrap

# 원본이 실제로 쓴 상한 (`--check` 가 다시 잰다)
# 🔴 **조각 하나 = 줄 하나**다(2026-09-07). 0x01 을 줄바꿈으로 읽던 때는 「5줄」이 나왔는데
#    그건 쉼표였다 — 실측 다시: ED3 30칸/1줄 · ED4 37칸/1줄.
LIMITS = {
    "ed3": {"width": 30, "lines": 1},
    "ed4": {"width": 37, "lines": 1},
}
# 대사에서 부호 뒤 공백을 지우던 규약(`docs/reference/translation-conventions.md`, 옛 값 ".,")은 **ED3 에선 접는다**(마스터 10-07).
# 이유: 부호가 반 칸(6px)이 되며 「부호 12px 하나」가 「부호 6px + 공백 6px」과 폭이 같아졌다 — 공백을 남겨도 한 줄 폭이 그대로고,
#   지우면 「티나,내일」처럼 붙어 읽기 나쁘다(실측 캡처 `halfspace/P01`). ED4 는 엔진 패치가 없어 부호가 12px 라 아직 옛 규약이 맞다.
STRIP_AFTER = {"ed3": "", "ed4": ".,"}


CELL_PX = 12  # 화면에서 코드 하나가 차지하는 가로 픽셀 (`font.PITCH`)
# 코드별 폭(px). 🔴 엔진 패치(`engine_patch`)가 있는 디스크만 12 가 아닌 값을 가질 수 있다 —
#   공백 8px → 6px(반 칸): 유저 판정 2026-09-07 은 「한글 전각·공백만 반각」, 마스터 10-07 「대사창 공백 반각」 — 8px 는 2/3 칸이라 절반(6px)으로 내린다.
# 반각(6px): 공백 · `. , ? !` · `( )` — `… ～` 는 전각 유지(마스터 10-07: 점 셋 한 글리프·반각이면 모양이 안 남). 「」『』 는 대사 조각에서 반각(마스터 10-26).
WIDTHS = {"ed3": {c: 6 for c in " .,?!()「」『』"}, "ed4": {}}  # 「」『』: 대사 조각에서는 반 칸 글리프(font.KAGI, 마스터 10-26)
# 한 줄에 들어가는 글리프 수의 상한 = 스프라이트 격자 열 수(`engine_patch.COLS`). 패치 없으면 None.
COLS = {"ed3": 24, "ed4": None}  # 🔴 32 가 아니다 — `engine_patch.COLS` 머리말 참조(▼ 결함)


def cell_width(ch, disc="ed3"):
    """이 게임의 슬롯 폭 — 공백만 8/12, 나머지 1.

    ⚠ 공용 기본값(`krwrap.default_cell_width`)은 공백을 **0.5**로 센다. 그건 PS1 ED1+2 의
      규격이고 여기선 틀린다 — 이 게임엔 공백 코드가 아예 없어서 **빈 글리프를 한 자리
      구워 쓴다**(`hangul_map.EXTRA`). 엔진 패치가 공백을 6px(반 칸)로 보내니 그만큼(1/2)이다.
    """
    return WIDTHS[disc].get(ch, CELL_PX) / CELL_PX


def width_cells(text, disc="ed3"):
    """한 줄의 폭(칸, 소수). 부호 뒤 공백 제거 전 값이라 안전측이다."""
    return sum(cell_width(ch, disc) for ch in text)


def _extra_lines():
    """{원문 지문: 줄 수} — 한 줄 예산인 조각 중 **두 줄로 푸는 것**(`extra_lines.json`, 지문만 — 원문은 안 둔다).

    엔진엔 대사 개행이 없고 글자가 **격자 24칸째에서 저절로 접힌다**(시험 롬 실측 10-18, 접히는 자리는 글자 수(공백 포함)로 정해진다 —
    슬롯 폭이 아니다). 그래서 24글리프를 넘는 번역은 한 줄로 못 맞추지만, 첫 줄을 **공백 글리프로 24칸까지 채우면** 다음 어절이
    둘째 줄 머리에서 시작한다(`pad_rows`). 창은 4행이라 둘째 줄이 창 안에 그려지고 쪽 넘김도 정상이다."""
    path = os.path.join(common.ROOT, "extra_lines.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


EXTRA_LINES = _extra_lines()


def pad_rows(text, disc):
    """두 줄 조각을 **구울 꼴**로 — 첫 줄을 공백 글리프로 격자 열까지 채우고 개행은 없앤다(엔진이 24칸째에서 접는다).

    줄이 하나뿐이면 그대로다. 줄 수는 `extra_lines.json` 이 정한 조각만 둘이 된다."""
    rows = text.split("\n")
    if len(rows) == 1:
        return text
    cols = COLS[disc]
    if len(rows) != 2 or not cols or len(rows[0]) > cols:
        raise TypesetError(f"두 줄을 격자에 못 맞춘다: {text!r}")
    return rows[0] + " " * (cols - len(rows[0])) + rows[1]


def budget(disc, jp, floor=0):
    """(폭, 줄 수) — **그 조각의 원문이 쓴 만큼**. 상한을 넘지 않는다.

    창은 자리마다 다르다(대사창·간판·설명문). 원문이 그 창에서 몇 칸을 썼는지가
    우리가 아는 가장 정확한 증거다 — 상한만 보고 넓게 잡으면 창 밖으로 나간다.
    """
    lim = LIMITS[disc]
    ls = jp.split("\n")
    w = max((len(x) for x in ls), default=1)
    # 🔴 **폭은 그 조각이 아니라 창이 정한다.** 조각별로 잡으면 원문이 우연히 짧은 자리에서
    #    허수 예산이 나온다 — 같은 화자가 연달아 말하는 창들이 4·19·15·21칸으로 널뛴다.
    #    인게임 실측(2026-09-07, `SC000!FT0000` 크리스 엄마 창): 프레임 안쪽 25~331px ·
    #    글자 피치 12px · 글자 시작 34 ⇒ **약 24칸**. 그 멤버의 원문 최대가 23칸이었다.
    #    ⇒ `floor` 로 **그 멤버의 최대 폭**을 받아 바닥으로 깐다. 줄 수는 창 높이라 그대로 둔다.
    if floor:
        w = max(w, floor)
    n = min(max(len(ls), 1), lim["lines"])
    if jp is not None:
        n = max(n, EXTRA_LINES.get(hashlib.sha1(jp.encode("utf-8")).hexdigest()[:8], 0))
    return min(w, lim["width"]), n


# ── 창 단위 재조판(마스터 10-20 「어절단위 개행」 · 규칙 2-6·2-10) ──────────────────────────────────
# 한 창 = `0F 90 V (01 90 W)* 00` 시퀀스 하나이고, 조각 하나가 한 줄이다(조각이 빈 꼬리면 그 줄은 안 그려진다 — 10-20 실측).
# 원문 줄 구조를 따르지 않고 창 문장을 이어 **창 폭(24글리프)을 채워** 어절 경계에서 다시 나눈다. 쪽(=시퀀스) 경계는 그대로.
BIND = "\ue000"  # 띄어 쓴 정본 이름의 공백을 임시로 바꾸는 사적 문자(줄바꿈 금지) — 끝나면 공백으로 되돌린다


def _bind_names():
    """[(이름, 묶은 이름)] — 정본 nouns 중 공백이 든 이름(긴 것부터)."""
    from shared import canon

    names = sorted(
        {kr for _c, _jp, kr in canon.all_names("ed3") if " " in kr}, key=len, reverse=True
    )
    return [(n, n.replace(" ", BIND)) for n in names]


_BOUND = None


def _cw(ch, disc):
    return cell_width(" " if ch == BIND else ch, disc)


def _fits(line, disc, cols):
    return len(line) <= cols and sum(_cw(c, disc) for c in line) <= cols


# ── 줄 나눔 규칙 2-16(마스터 10-26) — ② 절째 내리기 · ③ 끝 줄 한 어절 고아 방지. 판정은 지표 검사기(`wrap_metrics`)와 **같은 함수**다.
CONJ = {
    "그리고",
    "그러나",
    "하지만",
    "그래서",
    "그런데",
    "그러면",
    "그럼",
    "게다가",
    "그러니",
}  # 문장 머리 접속어 — 쉼표가 붙어도 절 경계 아님
# 연결어미 — 본용언+보조용언과 겹치는 「-고」·「-며」 는 뺀다(보조용언 쪽은 `split_reason` 도 막는다)
CONNECT = re.compile(
    r"(지만|는데|인데|니까|으니|면서|으면서|으나|라서|해서|어서|아서|려고|이며|으며)$"
)
MIN_HEAD = 10.0  # 절 앞에 이만큼(칸)은 남아야 절째 내린다 — 앞 줄이 너무 짧게 남으면 안 한다


_ADN_BOUND = re.compile(
    r"^(때|것|수|적|줄|데|바|뿐|만큼|대로|듯|채|척|양)(은|는|이|가|을|를|도|만|만은|에|의|로|까지|부터|보다|처럼)?[.,!?…]*$"
)


def bonded(a, b):
    """두 어절 사이에서 줄·쪽을 끊으면 붙여 쓸 덩어리가 갈리나 — 공용 `krwrap.split_reason` + 조사가 붙은 의존명사 꼬리(「왔을⏎때만은」)를 이쪽에서 먼저 막는다
    (공용에 「만은」 꼴이 없어 못 잡는다 — board/krwrap-deferred.md 후보)."""
    why = krwrap.split_reason(a, b)
    if why:
        return why
    if a and _adnominal(a) and _ADN_BOUND.match(b):
        return "관형형+의존명사"
    return None


def clause_bound(words, k):
    """words[k] 뒤가 절 경계인가(문장 끝·쉼표·연결어미). 붙여 쓸 덩어리가 갈리는 자리·「오,」 같은 두 음절 이하 쉼표·문장 머리 접속어는 아니다."""
    if k + 1 >= len(words):
        return False
    wd = words[k]
    if bonded(wd, words[k + 1]):
        return False
    bare = wd.rstrip(".,!?…~」』)")
    if krwrap.is_sentence_end(wd):
        return True
    if wd.endswith(","):
        return not (bare in CONJ or len(bare) <= 2)
    return bool(CONNECT.search(wd))


def clause_split(a, b, disc, cols):
    """줄 a(다음 줄 b 로 이어짐)에서 시작한 마지막 절이 b 에 통째로 들어가는데 쪼갰으면 (남길 앞부분, 내릴 절 앞머리) — 아니면 None."""
    aw, bw = a.split(), b.split()
    if not aw or not bw or krwrap.is_sentence_end(a) or bonded(aw[-1], bw[0]):
        return None
    ks = [k for k in range(len(aw) - 1) if clause_bound(aw, k)]
    if not ks:
        return None
    k = ks[-1]
    head = " ".join(aw[: k + 1])
    j = 0
    while j < len(bw) - 1 and not clause_bound(bw, j):
        j += 1
    clause = " ".join(aw[k + 1 :] + bw[: j + 1])
    if j == len(bw) - 1 and not krwrap.is_sentence_end(b):
        return None  # 절이 그다음 줄로 또 이어진다
    if width_cells(head) >= MIN_HEAD and _fits(clause, disc, cols):
        return head, " ".join(aw[k + 1 :])
    return None


def clause_violations(rows, disc="ed3", cols=24):
    return sum(1 for i in range(len(rows) - 1) if clause_split(rows[i], rows[i + 1], disc, cols))


# [명사+명사] 굳은 구(2-16 ⑤ 추가 — 관리자 10-26) — 형태소 분석기 없이, 앞 어절이 조사·어미·관형형·부사로 안 끝나는 꼴이면 명사로 본다.
# 같은 이음 [앞 어절, 뒤 어절 줄기]가 대사 전량에 2회 이상 나와야 구로 친다(반복이 구라는 증거 — 오탐은 줄 수가 안 늘 때만 묶으니 해가 작다).
_NOT_NOUN_END = set(
    "은는이가을를의에도로와과만서고며면니다요죠까나네데지자게어아해라러든께야군걸들"
)
_NOT_NOUN = {
    "가장", "특히", "모두", "한층", "우선", "역시", "대체", "여태", "지금", "이제", "계속", "완전히", "원래", "여기", "그리", "또다시",
    "모조리", "빨리", "우리", "너희들", "여러분", "정말", "아주", "매우", "너무", "다시", "아직", "벌써", "이미", "결코", "반드시",
    "제발", "어서", "함께", "같이", "그냥",
}  # fmt: skip
_JOSA_STEM = "은는이가을를의에도로와과만"
_PHRASES = None
REJECTED = []  # 퇴행이라 거부한 창의 사유들(지표 검사기가 센다)


def _adnominal(w):
    c = w[-1]
    if c in "던는":
        return True
    o = ord(c) - 0xAC00
    return 0 <= o < 11172 and o % 28 in (4, 8)  # 받침 ㄴ·ㄹ(관형형 -ㄴ/-ㄹ)


def noun_noun(wa, wb):
    """앞 어절 wa 와 뒤 어절 wb 가 [명사+명사] 꼴인가(서술어·지시어로 시작하는 뒤는 구가 아니다)."""
    if not wa or not wb or wa in _NOT_NOUN or wa.rstrip("」』)") != wa:
        return False
    if wa[-1] in _NOT_NOUN_END or wa[-1] in ".,!?…」" or _adnominal(wa):
        return False
    return not (wb[-1] in "다요죠까" or wb[0] in "그이저")


def _stem(w):
    return w.rstrip(_JOSA_STEM + ".,!?…」") or w


def noun_phrases():
    """대사 전량에서 같은 이음이 두 번 이상 나온 [명사+명사] 구 {(앞 어절, 뒤 줄기)}."""
    global _PHRASES
    if _PHRASES is None:
        import collections
        import itertools

        import script as script_canon

        canon, _ = script_canon.load_effective("ed3")
        cnt = collections.Counter()
        for lines in canon.values():
            for row in lines.values():
                ws = row["kr"].replace("\n", " ").split()
                for x, y in itertools.pairwise(ws):
                    if noun_noun(x, y):
                        cnt[(x, _stem(y))] += 1
        _PHRASES = {k for k, n in cnt.items() if n >= 2}
    return _PHRASES


_RUN_JOSA = set("은는이가을를의에도로와과만")
_TRIGRAMS = None


def _run_word(w):
    """묶음 후보 어절 — 조사·부호로 끝나지 않는 낱말(어미 「-라」 같은 꼴도 허용: 「키타라」는 이름이다)."""
    return bool(w) and w[-1] not in _RUN_JOSA and w[-1] not in ".,!?…」』)" and w not in _NOT_NOUN


def noun_runs():
    """대사 전량에서 같은 세 어절 [앞, 가운데, 뒤 줄기]가 세 번 이상 나온 명사 덩이(별칭+이름 「키타라 악사 트로바」) {(앞, 가운데, 뒤 줄기)}."""
    global _TRIGRAMS
    if _TRIGRAMS is None:
        import collections

        import script as script_canon

        canon, _ = script_canon.load_effective("ed3")
        cnt = collections.Counter()
        for lines in canon.values():
            for row in lines.values():
                ws = row["kr"].replace("\n", " ").split()
                for a, b, c in zip(ws, ws[1:], ws[2:], strict=False):
                    if (
                        _run_word(a)
                        and _run_word(b)
                        and c[:1] not in "그이저"
                        and not _adnominal(a)
                        and not _adnominal(b)
                    ):
                        cnt[(a, b, _stem(c))] += 1
        _TRIGRAMS = {k for k, n in cnt.items() if n >= 3}
    return _TRIGRAMS


def bind_runs(para):
    """대사 전량에서 자주 이어 나온 세 어절 명사 덩이(별칭+이름 「키타라 악사 트로바」)는 줄 사이에서 안 갈리게 묶는다(관리자 10-26)."""
    ws = para.split(" ")
    tg = noun_runs()
    out, i = [], 0
    while i < len(ws):
        if i + 2 < len(ws) and (ws[i], ws[i + 1], _stem(ws[i + 2])) in tg:
            out.append(BIND.join(ws[i : i + 3]))
            i += 3
        else:
            out.append(ws[i])
            i += 1
    return " ".join(out)


def split_phrase(a, b):
    """줄 a 끝 어절과 줄 b 첫 어절이 갈린 굳은 구면 True."""
    aw, bw = a.split(), b.split()
    return bool(
        aw
        and bw
        and len(aw) >= 2
        and noun_noun(aw[-1], bw[0])
        and (aw[-1], _stem(bw[0])) in noun_phrases()
    )


def fix_phrases(rows, disc="ed3", cols=24):
    """굳은 구가 줄 끝·첫머리로 갈렸으면 앞 어절을 다음 줄로 내려 묶는다 — 같은 문장 안에서, 줄 수가 안 늘 때만."""
    rows = list(rows)
    for _ in range(len(rows)):
        for i in range(len(rows) - 1):
            if krwrap.is_sentence_end(rows[i]) or not split_phrase(rows[i], rows[i + 1]):
                continue
            aw = rows[i].split()
            j = i + 1
            while j < len(rows) - 1 and not krwrap.is_sentence_end(rows[j]):
                j += 1
            tail = _wrap_sentence(aw[-1] + " " + " ".join(rows[i + 1 : j + 1]), disc, cols)
            keep = " ".join(aw[:-1])
            if tail is None or width_cells(keep) < MIN_HEAD / 2 or len(tail) > j - i:
                continue
            rows = [*rows[:i], keep, *tail, *rows[j + 1 :]]
            break
        else:
            break
    return rows


def phrase_violations(rows):
    return sum(
        1
        for i in range(len(rows) - 1)
        if not krwrap.is_sentence_end(rows[i]) and split_phrase(rows[i], rows[i + 1])
    )


def _clause_end(row):
    """줄 끝이 절 경계(문장 끝·쉼표·연결어미)인가."""
    w = row.split()[-1] if row.split() else ""
    return krwrap.is_sentence_end(w) or w.rstrip("」』)").endswith(",") or bool(CONNECT.search(w))


def regressions(old, new):
    """[사유] — 규칙을 적용한 new 가 규칙 전 old 보다 **나빠진** 자리(퇴행). 하나라도 있으면 그 변형을 거부한다.
    ① 새로 생긴 줄 끝 끊김이 붙여 쓸 덩어리(`split_reason` — 보조용언·의존명사·관형사 고아)를 가른다
    ② 전에는 한 줄에 들던 문장이 갈렸다  ③ 전에는 절 경계에서 끝나던 줄이 절 경계가 아닌 줄로 바뀌어 늘었다."""
    old = [r for r in old if r.strip()]
    new = [r for r in new if r.strip()]
    bad = []
    pairs = {
        (a.split()[-1], b.split()[0])
        for a, b in zip(old, old[1:], strict=False)
        if a.split() and b.split()
    }
    for a, b in zip(new, new[1:], strict=False):
        if krwrap.is_sentence_end(a) or not a.split() or not b.split():
            continue
        p = (a.split()[-1], b.split()[0])
        if p not in pairs and bonded(*p):
            bad.append(f"새 끊김 {p[0]}⏎{p[1]}")
    for sent in krwrap.split_sentences(" ".join(new)):
        if any(sent in r for r in old) and not any(sent in r for r in new):
            bad.append("한 줄이던 문장이 갈렸다")
    nb = lambda rs: sum(1 for r in rs[:-1] if not _clause_end(r))  # noqa: E731
    if nb(new) > nb(old):
        bad.append(f"절 경계가 아닌 줄 끝 {nb(old)}→{nb(new)}")
    return bad


def orphan_tail(rows):
    """끝 줄이 한 어절이고 앞 줄이 같은 문장에서 이어졌다(쪽 끝 고아)."""
    rows = [r for r in rows if r.strip()]
    return len(rows) >= 2 and len(rows[-1].split()) == 1 and not krwrap.is_sentence_end(rows[-2])


def rebreak(rows, wrapfn, disc="ed3", cols=24):
    """긴 문장 하나를 나눈 줄들에 ② 절째 내리기 ③ 끝 줄 고아 방지를 적용한다. 줄 수가 늘거나 위반이 안 줄면 원래대로."""
    for _ in range(len(rows)):
        n0 = clause_violations(rows, disc, cols)
        if not n0:
            break
        for i in range(len(rows) - 1):
            sp = clause_split(rows[i], rows[i + 1], disc, cols)
            if not sp:
                continue
            head, mv = sp
            tail = wrapfn(" ".join([mv] + rows[i + 1 :]))
            if tail is None:
                continue
            new = rows[:i] + [head] + tail
            if len(new) <= len(rows) and clause_violations(new, disc, cols) < n0:
                rows = new
                break
        else:
            break
    if orphan_tail(rows):
        aw = rows[-2].split()
        if len(aw) >= 2 and not bonded(aw[-2], aw[-1]):
            cand = [*rows[:-2], " ".join(aw[:-1]), " ".join([aw[-1], rows[-1]])]
            if all(_fits(r, disc, cols) for r in cand) and clause_violations(
                cand, disc, cols
            ) <= clause_violations(rows, disc, cols):
                rows = cand
    return rows


def _wrap_sentence(sent, disc, cols):
    """한 문장을 어절 경계로 나눈다 — 폭을 반 칸씩 줄여 모든 줄이 격자 안에 들 때까지. 못 하면 None."""
    width = float(cols)
    while True:
        out = krwrap.wrap(
            sent,
            width=width,
            cell_width=lambda ch: _cw(ch, disc),
            strip_after=STRIP_AFTER[disc],
        )
        if all(_fits(x, disc, cols) for x in out) or width <= 4:
            break
        width -= 0.5
    return out if all(_fits(x, disc, cols) for x in out) else None


PAGE_ROWS = (3, 4)  # 엔진이 쪽을 넘기는 줄 수 — 이름표(화자)가 있는 창은 3줄, 없는 창은 4줄(11-06 화면 실측: FT3001 창 0·22, MT2100 창 14)


def blank_page(rows):
    """조각 수 `len(rows)` 중 글 있는 줄이 앞에 몰려 **글 없는 조각만으로 한 쪽이 서면** 참 — 엔진은 그 빈 쪽에서도 확인 키를 기다린다.
    이름표 유무를 정적으로 못 가르므로 쪽 크기 3·4 둘 다 본다(11-06: 5조각에 글 3~4줄이면 둘째 쪽이 빈 창으로 떴다)."""
    n = sum(1 for r in rows if r.strip())
    return any(n <= p * c < len(rows) for p in PAGE_ROWS for c in range(1, len(rows)))


STATS = {"sentence": 0, "clause": 0, "cols": 0, "kept": 0}  # 빈 쪽 해소 방법별 창 수(11-06 관리자 보고용 — 문장 경계 · 절 경계 · 좁은 칸 · 원 구조 유지)


def _cuts(row, clause):
    """줄 안에서 나눌 수 있는 자리 [k] (row[k] == " ") — 앞이 문장 끝이면 문장 경계, `clause` 면 쉼표·연결어미 뒤(`clause_bound`, 2-16 ②)도."""
    words = row.split(" ")
    out, pos = [], 0
    for k in range(len(words) - 1):
        pos += len(words[k])
        if (words[k] and words[k + 1]) and (
            krwrap.is_sentence_end(words[k]) or (clause and clause_bound(words, k))
        ):
            out.append(pos)
        pos += 1
    return out


def _split_blank(rows, clause):
    """빈 쪽을 줄 쪼개기로 푼다(2-17 > 2-10/2-16 — 마스터 11-06 규칙 순서): 한 줄에 두 문장 이상이면 문장 경계에서, 원래 쪽 경계에 가장 가까운 줄부터.
    `clause` 면 쉼표 뒤도 쓴다(한 문장뿐인 창). 줄이 하나 늘 때마다 꼬리 빈 조각 하나를 먹는다. 글은 안 줄인다(공백 하나가 줄 바꿈이 될 뿐)."""
    r = list(rows)
    while blank_page(r):
        if r[-1] != "":
            return None
        best = None
        for i, row in enumerate(r):
            for k in _cuts(row, clause):
                d = min(min((i + 1) % p, p - (i + 1) % p) for p in PAGE_ROWS)
                if best is None or d < best[0]:
                    best = (d, i, k)
        if best is None:
            return None
        _d, i, k = best
        r[i : i + 1] = [r[i][:k], r[i][k + 1 :]]
        r.pop()
    last = [x for x in r if x.strip()][-1]
    if " " not in last and len(last) <= 4:  # 마지막 쪽에 낱말 하나만 외롭게 남기지 않는다(고아)
        return None
    return r


def reflow(texts, disc="ed3", cols=None, rule216=True, glue=()):
    """`_reflow` 결과가 빈 쪽을 만들면 푼다 — ① 문장 경계 쪼개기 ② 절 경계(쉼표) 쪼개기 ③ 칸 수를 줄인 재조판 ④ 안 되면 None(원래 구조 유지)."""
    rows = _reflow(texts, disc, cols, rule216, glue)
    if rows is None or not blank_page(rows):
        return rows
    base = None
    for clause, name in ((False, "sentence"), (True, "clause")):
        alt = _split_blank(rows, clause)
        if alt is not None:
            if base is None:
                base = _reflow(texts, disc, cols, False, glue) or texts
            if regressions(base, alt):  # 규칙 전 조판보다 나빠지면(새 끊김) 이 방법은 쓰지 않는다
                continue
            STATS[name] += rule216
            return alt
    for c in range((cols or COLS[disc] or 24) - 1, 11, -1):
        alt = _reflow(texts, disc, c, rule216, glue)
        if alt is not None and not blank_page(alt):
            STATS["cols"] += rule216
            return alt
    STATS["kept"] += rule216
    return None


def _reflow(texts, disc="ed3", cols=None, rule216=True, glue=()):
    """창 하나의 조각들 → 같은 개수의 조각(앞에서부터 한 줄씩, 남는 꼬리는 빈 문자열). 못 하면 None(원래 구조 유지).

    규칙: 문장을 이어 놓고 ① 앞 줄 남은 칸에 문장이 **통째로** 들어가면 거기 잇고(2-10) ② 아니면 새 줄에서 시작하며 ③ 한 줄보다
    긴 문장만 어절 경계로 나눈다(2-6). 띄어 쓴 정본 이름은 한 어절로 묶는다. 줄이 조각 수보다 늘면 None.
    변수가 끼는 창(조각 앞뒤 공백 · 런타임 조사 표지 · 병기 `(이)` · 개행)은 건드리지 않는다."""
    global _BOUND
    import josa_rt

    cols = cols or COLS[disc] or 24
    if any(
        not t
        or t != t.strip(" ")
        or "\n" in t
        or josa_rt._TOKEN.search(t)
        or josa_rt._COPULA.match(t)
        or t[0] in josa_rt.MARKER_CHARS
        or t.startswith("\u3000")
        for t in texts
    ) or any(
        t.startswith("…") and not krwrap.is_sentence_end(texts[k - 1]) for k, t in enumerate(texts) if k
    ):  # 앞 조각이 문장 중간에서 끝나고 다음 조각이 「…」 로 시작하면 줄 머리 말줄임이다 — 이어 붙이면 줄 가운데 「…」 뒤가 붙는다(2-11)
        return None
    if _BOUND is None:
        _BOUND = _bind_names()
    para = " ".join(texts)
    for name, bound in _BOUND:
        para = para.replace(name, bound)
    para = bind_runs(para)
    for x, y in glue:  # 굳은 명사구로 갈린 쌍은 한 덩이로 묶어 다시 나눈다
        para = para.replace(f"{x} {y}", x + BIND + y)
    rows, cur = [], ""
    sents = []
    for sent in krwrap.split_sentences(para):
        # 「…!』입니다」 처럼 닫는 부호 바로 뒤에 글이 붙어 있으면 공유 분리기가 둘로 쪼갠다 — 원문에 공백이 없었으니 다시 붙인다(공백을 새로 넣지 않는다)
        if sents and sents[-1] + sent in para and sents[-1] + " " + sent not in para:
            sents[-1] += sent
        else:
            sents.append(sent)
    for sent in sents:
        cand = f"{cur} {sent}" if cur else sent
        if _fits(cand, disc, cols):
            cur = cand
        elif _fits(sent, disc, cols):
            rows.append(cur)
            cur = sent
        else:  # 한 줄보다 긴 문장 — 새 줄에서 시작해 어절 경계로 나눈다(2-10: 앞 줄에 통째로 안 들어가면 새 줄)
            if cur:
                rows.append(cur)
            out = _wrap_sentence(sent, disc, cols)
            if out is None:
                return None
            if rule216:
                out = rebreak(out, lambda t: _wrap_sentence(t, disc, cols), disc, cols)
            rows += out[:-1]
            cur = out[-1]
    if cur:
        rows.append(cur)
    if (
        len(rows) > len(texts) and rule216
    ):  # 문장마다 새 줄을 열면 줄이 모자란다 — 문장을 이어 채워 빽빽하게 다시 나눈다(2-16: 손 개행을 남기느니 채워 쓴다)
        dense = _wrap_sentence(para, disc, cols)
        if dense is not None:
            rows = rebreak(dense, lambda t: _wrap_sentence(t, disc, cols), disc, cols)
    if rule216:  # 묶은 덩이(BIND)를 그대로 둔 채 — 덩이 안을 구 이동이 다시 가르지 않게
        rows = fix_phrases(rows, disc, cols)
    rows = [r.replace(BIND, " ") for r in rows]
    if len(rows) > len(texts) or "".join("".join(rows).split()) != "".join("".join(texts).split()):
        return None
    rows = rows + [""] * (len(texts) - len(rows))
    if rule216:  # 퇴행이면 규칙 전 조판(없으면 원고 줄 구조)으로 되돌린다
        base = reflow(texts, disc, cols, rule216=False)
        if regressions(base or texts, rows):
            REJECTED.append(regressions(base or texts, rows))
            return base  # 규칙 전 조판(재조판을 못 타던 창이면 None — 원고 줄 구조 그대로)
        # 굳은 명사구가 갈리면(2-16 ④) 한 줄 문장(2-10)을 살리려 구를 가르면 안 된다 — 문장을 이어 채운 배치로 다시 해 보고, 그래도 갈리면 옛 배치
        orig = [r for t in texts for r in wrap(t, disc).split("\n") if r.strip()]  # 원고 구조 그대로 구운 꼴
        e0 = phrase_violations(orig)
        if phrase_violations(rows) > e0:
            pairs = tuple(
                (u.split()[-1], v.split()[0])
                for u, v in zip(rows, rows[1:], strict=False)
                if u.split() and v.split() and not krwrap.is_sentence_end(u) and split_phrase(u, v)
            )
            if pairs and not glue:
                alt = reflow(texts, disc, cols, glue=pairs)
                if (
                    alt
                    and phrase_violations([r for r in alt if r.strip()]) <= e0
                    and not regressions(base or texts, alt)
                ):
                    return alt
            dense = _wrap_sentence(para, disc, cols)
            for alt in (
                rebreak(dense, lambda t: _wrap_sentence(t, disc, cols), disc, cols) if dense else None,
                dense,
                _wrap_sentence(para, disc, cols - 2),
            ):
                alt = fix_phrases(alt, disc, cols) if alt else None
                if not alt:
                    continue
                alt = [r.replace(BIND, " ") for r in alt]
                if len(alt) > len(texts):
                    continue
                alt = alt + [""] * (len(texts) - len(alt))
                if phrase_violations([r for r in alt if r.strip()]) <= e0 and not regressions(
                    base or texts, alt
                ):
                    return alt
            REJECTED.append(["굳은 명사구가 갈림 — 옛 배치"])
            if base and phrase_violations([r for r in base if r.strip()]) <= e0:
                return base
            return None
    return rows


def _page_end(row):
    """창 끝 줄이 이야기를 끝맺는가(문장 끝·말끝 늘임) — 아니면 문장이 다음 창으로 이어진다."""
    return krwrap.is_sentence_end(row) or row.rstrip().endswith(("〜", "～", "ー"))


def balance_windows(wins, caps, disc="ed3", cols=24):
    """이어지는 창들(앞 창이 문장 중간에서 끝남)의 줄을 **창 수·글 순서를 그대로** 골고루 나눈다 — 마지막 창에 한 어절만 남는 것(h) ·
    줄 수 차가 2 이상인 것(h2)을 푼다. 창 경계는 문장 끝 > 절 경계로만 옮기고(문장 중간으로는 안 옮긴다, 관리자 10-26), 창은 조각 수(caps)를 못 넘는다.
    wins = [줄들] 또는 None(재조판을 못 타는 창 — 건드리지 않는다)."""
    wins = [list(w) if w is not None else None for w in wins]
    for i in range(len(wins) - 1):
        a, b = wins[i], wins[i + 1]
        if a is None or b is None:
            continue
        a[:] = [r for r in a if r.strip()]
        b[:] = [r for r in b if r.strip()]
        for _ in range(4):
            if len(a) < 2 or not b or _page_end(a[-1]):
                break
            new_end = a[-2]
            ok_end = krwrap.is_sentence_end(new_end) or _clause_end(new_end)
            if len(a) - len(b) >= 2 and len(b) < caps[i + 1] and ok_end:  # h2 — 줄째 내려 고르게
                b.insert(0, a.pop())
                continue
            if len(b) == 1 and len(b[0].split()) == 1:  # h — 마지막 창에 한 어절만 남았다
                aw = a[-1].split()
                if len(aw) == 1 and len(b) < caps[i + 1] and ok_end:
                    b.insert(0, a.pop())
                    continue
                if (
                    len(aw) >= 2
                    and clause_bound(aw, len(aw) - 2)
                    and _fits(aw[-1] + " " + b[0], disc, cols)
                ):
                    a[-1] = " ".join(aw[:-1])
                    b[0] = aw[-1] + " " + b[0]
                    continue
            break
    return wins


def reflow_member(texts_per_chain, disc="ed3", cols=None):
    """멤버의 창들 → 구울 줄(창마다 조각 수로 채움) 또는 None(원래 구조 유지). `texts_per_chain` 의 None 은 번역 없음·공유 조각 창.
    창 하나씩 `reflow` 하고, 이어지는 창끼리 `balance_windows` 로 고른다 — 빌드와 지표 검사기가 같은 길을 쓴다."""
    rows = [None if t is None else reflow(t, disc, cols) for t in texts_per_chain]
    caps = [len(t) if t is not None else 0 for t in texts_per_chain]
    bal = balance_windows(rows, caps, disc, cols or COLS[disc] or 24)
    out = [None if r is None else r + [""] * (c - len(r)) for r, c in zip(bal, caps, strict=True)]
    # 균형 잡기가 줄을 앞 창에서 덜어 빈 쪽을 만들면 그 창만 균형 전 줄로 되돌린다
    return [
        o if o is None or not blank_page(o) else (r if r is not None and not blank_page(r) else o)
        for o, r in zip(out, [None if r is None else r + [""] * (c - len(r)) for r, c in zip(rows, caps, strict=True)])
    ]


_FULL_KEEP = "\ue000"  # wrap() 안에서만 쓰는 전각 공백 자리표


class TypesetError(Exception):
    pass


def wrap(text, disc, jp=None, width=None, lines=None, floor=0):
    """우리 문안 → 줄로 나눈 문안(`\\n` 포함).

    `jp` 를 주면 그 조각의 원문이 쓴 폭·줄 수를 예산으로 삼는다(권장). 멤버 대사는 `floor`
    (`script.member_floors`)도 준다 — 검사기(`script.py --check`)와 **같은 자**여야 한다.

    🔴 **예산을 넘으면 운다 — 자르지 않는다.** 예전엔 넘친 줄을 `out[:lines]` 로 버렸고, 빌드가
       `floor` 없이 불러 **ED3 37줄 · ED4 59줄의 꼬리가 조용히 사라졌다**(09-27, 화면 실측:
       `...아무튼,` · `을(를)` 에서 끊김). 검사기는 `floor` 를 줘서 0건이라 했다.
    🔴 **앞뒤 공백은 지키지 않고 남긴다.** 조각은 엔진이 끼우는 아이템 이름·숫자와 **한 줄로**
       이어 붙는다(스크립트 opcode `0x04`·`0x05`·`0x07`) — `쥬리오는 ` + [아이템] 의 공백을
       `split()` 이 먹으면 `쥬리오는短剣` 으로 붙는다.
    """
    if not text.strip():
        return ""
    lead = text[: len(text) - len(text.lstrip(" \u3000"))]  # 앞 공백 — 반각·전각 모두(가운데 맞춤 줄, 마스터 11-10)
    trail = text[len(text.rstrip(" ")) :]
    if width is None or lines is None:
        w, n = (
            budget(disc, jp, floor)
            if jp is not None
            else (LIMITS[disc]["width"], LIMITS[disc]["lines"])
        )
        width = width if width is not None else w
        lines = lines if lines is not None else n
    cols = COLS[disc]
    # 🔴 줄이 전각 공백(U+3000)으로 **시작**하면 가운데 맞춤 줄이다(장 끝 문구, 마스터 11-10 「장번호[전각]제목[전각]끝」) — 줄 속 전각 공백도
    #    krwrap 이 반각으로 눌러 버리지 않게 사설 글자로 가렸다가 되돌린다. 그 밖의 줄은 종전대로(전각 공백 → 반각).
    keep_full = lead.startswith("\u3000")
    body = text[len(lead) :].replace("\u3000", _FULL_KEEP) if keep_full else text
    while True:
        out = krwrap.wrap(
            body.replace("\n", " "),
            width=width,
            cell_width=lambda ch: cell_width(ch, disc),
            strip_after=STRIP_AFTER[disc],
        )
        if keep_full:
            out = [x.replace(_FULL_KEEP, "\u3000") for x in out]
        # 🔴 슬롯 폭 안이어도 **글리프(공백 포함)가 격자 열을 넘으면** 엔진이 어절 한복판에서 접는다 — 줄 수 여유가 있을 때만
        #    폭을 반 칸씩 줄여 어절 경계에서 접는다(여유가 없으면 아래에서 운다 / 한 줄이면 `violations` 가 잡는다).
        if not cols or len(out) >= lines or max(len(x) for x in out) <= cols or width <= 4:
            break
        width -= 0.5
    if len(out) > lines:
        raise TypesetError(f"{len(out)}줄 > 예산 {lines}줄 (폭 {width:g}): {text!r}")
    res = lead + "\n".join(out) + trail
    if "".join(res.split()) != "".join(text.split()):  # 불변식: 조판은 공백·개행만 옮긴다
        raise TypesetError(f"글이 바뀌었다: {text!r} → {res!r}")
    return res


def violations(text, disc, jp=None, floor=0):
    """[사유] — 조판 규격을 어긴 자리. 빈 목록이면 통과."""
    lim = LIMITS[disc]
    w, n = budget(disc, jp, floor) if jp is not None else (lim["width"], lim["lines"])
    bad = []
    ls = text.split("\n")
    cols = COLS[disc]
    for i, line in enumerate(ls):
        wc = width_cells(line, disc)
        if wc > w:
            bad.append(f"{i + 1}행이 {wc:g}칸 (예산 {w})")
        if cols and len(line) > cols:
            bad.append(f"{i + 1}행이 {len(line)}글리프 (격자 {cols}열)")
    if len(ls) > n:
        bad.append(f"{len(ls)}줄 (예산 {n})")
    return bad


def measure(disc):
    """원본이 실제로 쓴 (줄 최대 폭, 창 최대 줄 수, 조각 수, 줄 수)."""
    import scriptmap
    import textenc

    w = n = segs = lines = 0
    for path, (lba, size) in sorted(common.iso_files(disc).items()):
        if "/SC" not in path or not path.endswith(".DAT"):
            continue
        data = common.read_lba(disc, lba, size)
        try:
            _, ents = common.arc_parse(data)
        except common.ArchiveError:
            continue
        for nm, off, sz in ents:
            if not nm.endswith(".BIN") or sz < 8:
                continue
            try:
                info = scriptmap.parse(data[off : off + sz])
            except Exception:  # noqa: BLE001, S112 — 규격 밖 멤버는 check_script 가 센다
                continue
            for _, codes in info["segments"]:
                txt = textenc.decode(codes, disc)
                if not txt.strip():
                    continue
                ls = txt.split("\n")
                segs += 1
                lines += len(ls)
                n = max(n, len(ls))
                w = max(w, max(len(x) for x in ls))
    return w, n, segs, lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--check", action="store_true", help="상수를 원본에서 다시 잰다")
    a = ap.parse_args()
    lim = LIMITS[a.disc]
    if not a.check:
        print(f"{a.disc}: 줄 {lim['width']}칸 · 창 {lim['lines']}줄 (상한)")
        return 0
    common.verify_source(a.disc)
    w, n, segs, lines = measure(a.disc)
    print(f"{a.disc}: 조각 {segs:,} · 줄 {lines:,} → 원본 최대 {w}칸 / {n}줄")
    bad = []
    if w > lim["width"]:
        bad.append(f"줄 폭 상한 {lim['width']} < 원본 {w}")
    if n > lim["lines"]:
        bad.append(f"창 줄 수 상한 {lim['lines']} < 원본 {n}")
    for m in bad:
        print(f"  🔴 {m} — 상수를 고치고 문안을 다시 조판한다")
    if not bad and (w, n) != (lim["width"], lim["lines"]):
        print(f"  ⚠ 상한이 원본보다 넉넉하다 ({lim['width']}/{lim['lines']} vs {w}/{n})")
    print(f"{a.disc}: 조판 상수 — {'🔴 원본을 못 담는다' if bad else '✅ 원본을 담는다'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
