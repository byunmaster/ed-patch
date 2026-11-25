"""줄·쪽 나눔 전면 규칙 2-16 (docs/translation-rules.md) — 조판기와 지표 검사기가 **같은 판정**을 쓰도록 한 곳에 둔다.

    ① 문장 중간 손 개행은 공백으로 읽는다            `soften_hand`
    ② 줄이 넘칠 때 이 줄에서 시작한 절이 다음 줄에 통째로 들어가면 절째 내린다   `clause_down` / `clause_split`
    ③ 쪽 끝 한 어절 고아 · 문장 중간에서 한 낱말로 끝나는 쪽 금지               `check_page_*` (쪽 가르기는 `patch_scn.best_cut`)
    ④ 띄어 쓴 고유명사·굳은 명사구는 한 줄 (조판기 `_keep` 의 붙임 공백)
    ⑤ 이름 변수 뒤 조각은 이름 폭을 넣고 잰다 (조판기 `_TOKENS`·`measure`)

⚠ 판정의 뼈대(경계 세기 · 접속어 · 앞에 남는 폭 하한)는 sfc-ed2 `typeset.py` 의 것을 옮겼다 — 슬롯 폭만 이 게임 눈금(전각 14.0)으로 환산했다.
"""

import re

COLS = (
    14.0  # 창 한 줄 — typeset_scn.COLS 와 같은 값(순환 임포트를 피해 여기 두고 조판기가 맞춰 쓴다)
)
SENT_FIRST = True  # 2-10 — 문장 경계는 짧은 앞 줄 가드를 안 탄다. 가능하면이지 항상은 아니다(마스터 11-05): 창이 늘면 조판기가 끈다
MIN_LEFT = 5.5  # 줄을 끊고 앞에 남는 폭이 이보다 짧으면(낱말 하나쯤) 그 자리에선 안 끊는다 (sfc 20/50 단위 ≈ 줄의 40%)
_END_RE = re.compile(r"[.!?…~」』][\"')]*$")
_CONN_RE = re.compile(
    r"(?:아서|어서|여서|해서|려서|러서|라서|워서|니까|으니|면서|으며|하며|지만|는데|인데|으나|다가|도록|려고|므로|고|며|면)$"
)
_CONJ = {
    "그리고",
    "하지만",
    "그러나",
    "그래서",
    "게다가",
    "그러면",
    "그런데",
    "그러니",
    "그렇다면",
    "그러므로",
    "따라서",
    "그렇지만",
    "그래도",
    "그러자",
}  # 문장 머리 접속어 — 뒤 말에 붙는다(경계 아님)
SENT_END = ".!?…~」』"


def bkind(word):
    """절 경계의 세기 — 3 문장 끝 > 2 쉼표(「오,」처럼 두 음절 이하는 제외) > 1 연결어미 > 0 아님."""
    if not word:
        return 0
    if _END_RE.search(word):
        return 3
    if word.endswith(","):
        return 2 if len(word.rstrip(",")) > 2 else 0
    return 1 if (word not in _CONJ and _CONN_RE.search(word)) else 0


def wsum(words, wf):
    """어절들을 공백으로 이은 폭."""
    return sum(wf(w) for w in words) + 0.5 * max(0, len(words) - 1)


def clause_split(words, nxt_words, wf, cols=COLS, bonded=None):
    """줄 `words` 다음에 `nxt_words`(뒤따르는 줄들의 어절, 문단 끝까지)가 올 때 — 절째 내려야 하는 자리 `kk`(words[kk:] 가 다음 줄로) 또는 None.

    경계를 센 것부터(문장 끝 > 쉼표 > 연결어미) 보고, 그 경계 뒤에서 시작한 절(다음 경계 어절까지)이 한 줄에 다 들어가면 내린다.
    줄 끝 어절이 이미 경계면 안 건드린다(이미 절 끝에서 끊긴 줄).
    `bonded(앞 어절, 뒤 어절)` 이 참이면(본용언+보조용언처럼 한 덩어리) 그 경계에서는 안 끊는다 — 「돕고 싶은」을 「돕고 / 싶은」으로 가르지 않는다."""
    n = len(words)
    if n < 2 or bkind(words[-1]):
        return None
    for kind in (3, 2, 1):
        kk = next(
            (
                j
                for j in range(n - 1, 0, -1)
                if bkind(words[j - 1]) == kind and not (bonded and bonded(words[j - 1], words[j]))
            ),
            None,
        )
        # 🔴 문장 경계(kind 3)는 앞이 짧아도 내린다 — 번역 규칙 2-10(마스터 10-10): 한 줄에 들어가는 문장을 두 줄로 쪼개지 않는다
        #    (「그러십니까? 그것 참 / 아쉽군요.」 → 「그러십니까? / 그것 참 아쉽군요.」). 짧은 앞 줄 가드는 절·쉼표 경계에만 쓴다.
        if kk is None or ((kind != 3 or not SENT_FIRST) and wsum(words[:kk], wf) < MIN_LEFT):
            continue
        run = list(words[kk:])
        for q, x in enumerate(nxt_words):
            run.append(x)
            if bkind(x) and not (bonded and q + 1 < len(nxt_words) and bonded(x, nxt_words[q + 1])):
                break
        if wsum(run, wf) <= cols:
            return kk
    return None


def mid_sentence_nl(kr):
    """문장 중간 손 개행의 수 — 앞이 문장 끝·개행·`%` 표지가 아니고 뒤에 글이 이어지는 `\\n`."""
    n = 0
    for m in re.finditer(r"\n", kr):
        before, after = kr[: m.start()], kr[m.end() :]
        if (
            not before
            or not after
            or before[-1] in SENT_END + "\n%"
            or after[0] in "\n% "
            or re.search(r"%[csd]$", before)
        ):
            continue
        if not before.rstrip(" "):
            continue
        n += 1
    return n


def soften_hand(kr):
    """① 문장 중간 손 개행 → 공백. 문장 끝·빈 줄·창 표지 둘레의 개행은 번역자가 정한 자리라 둔다.
    `\\t` 정렬·빈 줄(`\\n\\n`) 블록(장 끝 카드 등)은 통째로 둔다 — 조판기가 원래 손대지 않는 꼴이다."""
    if not kr or "\t" in kr or "\n\n" in kr or "\n" not in kr:
        return kr

    def sub(m):
        before, after = kr[: m.start()], kr[m.end() :]
        if (
            not before.rstrip(" ")
            or not after
            or before[-1] in SENT_END + "\n%"
            or after[0] in "\n% "
            or re.search(r"%[csd]$", before)
        ):
            return "\n"
        return " "

    return re.sub(r"\n", sub, kr)


# ── ④′ [명사+명사] 굳은 구 (e) — 형태소 분석기 없이, 앞 어절이 조사·어미·관형형·부사로 안 끝나면 명사로 본다 (md-ed1 `linebreak.py` 의 판정)
_NOT_NOUN_END = set(
    "은는이가을를의에도로와과만서고며면니다요죠까나네데지자게어아해라러든께야군걸들"
)
_NOT_NOUN = {
    "가장", "특히", "모두", "한층", "우선", "역시", "대체", "여태", "지금", "이제", "계속", "완전히", "원래", "여기", "그리", "또다시", "냉큼",
    "모조리", "빨리", "우리", "너희들", "여러분", "정말", "아주", "매우", "너무", "다시", "아직", "벌써", "이미", "결코", "반드시", "제발",
    "어서", "함께", "같이", "그냥",
}  # fmt: skip
_JOSA = "은는이가을를의에도로와과만"


def _tail(w):
    return w.rstrip("」』)\"'")


def _adnominal(w):
    c = w[-1]
    if c in "던는":
        return True
    o = ord(c) - 0xAC00
    return 0 <= o < 11172 and o % 28 in (4, 8)  # 받침 ㄴ·ㄹ(관형형 -ㄴ/-ㄹ)


def noun_noun(wa, wb):
    """앞 어절 `wa`·뒤 어절 `wb` 가 [명사+명사] 꼴인가 (오탐은 줄 수가 안 늘 때만 묶으니 해가 작다)."""
    wa, wb = wa.replace("", " "), wb.replace("", " ")
    if not wa or not wb or wa in _NOT_NOUN or _tail(wa) != wa:
        return False
    if wa[-1] in _NOT_NOUN_END or wa[-1] in ".,!?…」" or _adnominal(wa):
        return False
    return not (wb[-1] in "다요죠까" or wb[0] in "그이저")


def stem(w):
    return w.rstrip(_JOSA + ".,!?…」") or w


_PHRASES = None


def phrases(texts=None):
    """같은 [앞 어절, 뒤 어절 줄기] 이음이 대사 전량에 두 번 이상 나온 명사 구 (반복이 구라는 증거). `texts` 는 문안 문자열들 — 처음 한 번만 센다."""
    global _PHRASES
    if _PHRASES is None:
        import collections
        import itertools

        cnt = collections.Counter()
        for t in texts or ():
            ws = re.sub(r"%[csd]|[\x00-\x1f]", " ", t).split()
            for x, y in itertools.pairwise(ws):
                if noun_noun(x, y):
                    cnt[(x, stem(y))] += 1
        _PHRASES = {k for k, n in cnt.items() if n >= 2}
    return _PHRASES
