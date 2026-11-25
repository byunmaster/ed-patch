"""줄·쪽 나눔 지표 — 번역 규칙 2-16 (마스터 10-26). 씬 대사 전량의 **조판 결과**(`script/MAP*.json` 의 `\\n`·`\\f`)로 센다.

    python3 games/ss-ed3/tools/check_linebreak.py             # 지표 a/b/c/d 와 블록 수
    python3 games/ss-ed3/tools/check_linebreak.py --show N    # 걸린 예 N 개 (종류별)
    python3 games/ss-ed3/tools/check_linebreak.py --check     # 기준선(`script/linebreak_baseline.json`)보다 늘면 실패
    python3 games/ss-ed3/tools/check_linebreak.py --freeze    # 지금 값을 기준선에 쓴다(줄었을 때만)

지표(블록 = 한 대사 문안, 쪽 = `\\f` 로 가른 구간, 줄 = `\\n` 로 가른 구간 · 줄 폭은 전각 17):
  a  쪽 끝 한 어절 고아 — 문장이 안 끝났는데 쪽이 **한 어절짜리 줄**로 끝난다
  b  문장 중간에서 덩어리를 가르는 쪽 — 문장이 안 끝났는데 쪽 끝 어절이 다음 쪽 첫 어절과 한 덩어리
     (`krwrap.split_reason`: 본용언+보조용언 · 관형형 고아 · 속격+체언 등)다(a 와 겹치지 않게 센다)
  c  문장 중간 손 개행 — 줄을 끝내고 다음 줄 첫 어절이 **앞 줄에 들어가는데** 끊었다
     (예외: 앞 줄이 절 경계로 끝나고 뒤 절이 앞 줄 남는 칸에 안 들어가면 절째 내린 것이라 정상)
  d  절째 내리면 들어가는데 쪼갠 줄 — 폭 때문에 끊긴 자리에서, 이 줄에서 시작한 절(쉼표·연결어미 뒤부터)이
     다음 줄과 합쳐 한 줄에 다 들어가는데(앞에 6.5칸 이상 남는다) 절 한가운데서 끊었다
  e  [명사+명사] 굳은 구가 줄 끝·첫머리로 갈린 곳 — 앞 어절이 조사·어미·관형형·부사로 안 끝나고(형태소 분석기 없이 꼴로 판정)
     같은 [앞 어절, 뒤 어절 줄기] 이음이 대사 전량에 2회 이상 나온다(반복이 구라는 증거 — md-ed1 `linebreak.py` 와 같은 판정)
  h  창 분배 — 대사창(쪽)이 둘 이상인 단위에서 마지막 창에 **한 어절만** 남았다(앞 창이 문장 도중에 끝난 경우)
  h2 창 분배 — 쪽 수를 안 늘리고 쪽 끝을 문장 끝·절 경계에만 두고도 창 줄 수 차를 1 이하로 나눌 수 있는데 지금은 2 이상 벌어진 단위
쪽 끝은 문장 끝 > 절 경계에만 둔다 — 조사·관형형으로 끝나는 쪽은 금지한다(`page_cut_ok`, 퇴행 f 에도 든다).
세는 대상은 대화창 문안뿐이다(나레이션·음성 자막은 2-14·2-15 가 우선). 이름 변수(`<01><28>`)는 폭 0 으로 센다.
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import center_narration as CN
import common as C
import typeset as T

sys.path.insert(0, os.path.join(C.GAME_DIR, "..", ".."))
sys.path.insert(0, os.path.join(C.GAME_DIR, "..", "..", "shared"))
import itertools

from shared.text import krwrap

SCRIPT = os.path.join(C.GAME_DIR, "script")
BASELINE = os.path.join(SCRIPT, "linebreak_baseline.json")
WINDOW_RESTORE = os.path.join(SCRIPT, "window_restore_2_17.json")  # 규칙 2-17 「원문 창 우선」으로 갈라 2-16 지표에서 뺀 블록
ORIG_PAGES = os.path.join(SCRIPT, "linebreak_orig_pages.json")  # 원판 쪽 나눔을 따른 블록 — h2 에서 뺀다(규칙 2-6)
GLUE = "\ue000"  # reflow_script 와 같은 자리표시 — 띄어 쓴 정본 이름 속 공백(폭은 반각 공백)
WIDTH = T.WIN_COLS
MIN_LEFT = 6.5  # 줄을 끊고 앞에 남는 줄이 이보다 좁으면(낱말 하나 정도) 그 자리에서는 끊지 않는다(전각 칸 — 줄 폭의 약 40%)
KINDS = ("a", "b", "c", "d", "e", "h", "h2")

END_RE = re.compile(r"[.!?…~」』][)'\"’”]*$")
CONN_RE = re.compile(
    r"(?:가서|와서|나서|아서|어서|여서|해서|려서|러서|라서|워서|니까|으니|면서|으며|하며|지만|는데|인데|으나|다가|도록|려고|므로|해도|어도|아도|여도|라도|거나|든지|기에|고|며|면)$"
)
CONJ = {"그리고", "하지만", "그러나", "그래서", "게다가", "그러면", "그런데", "그러니", "그렇다면", "그러므로", "따라서", "그렇지만", "그래도", "그러자"}  # fmt: skip


def _cw(ch):
    return 0.5 if ch == GLUE else T.char_cols(ch)


def wcols(s):
    return sum(_cw(c) for c in s)


def fits(line):
    """엔진이 이 줄을 접지 않나 — `typeset.fold` 와 같은 자(줄 끝 글자가 시작하는 자리 ≤ 16.0)."""
    return len(T.fold(line.replace(GLUE, " "))) == 1


def bkind(word):
    """절 경계의 세기 — 3 문장 끝 > 2 쉼표(두 글자 이하 감탄사 「오,」 제외) > 1 연결어미 > 0 아님."""
    plain = re.sub(r"[)'\"’”」』]+$", "", word)
    if END_RE.search(word):
        return 3
    if plain.endswith(","):
        return 2 if len(plain.rstrip(",")) > 2 else 0
    return 1 if (plain not in CONJ and CONN_RE.search(plain)) else 0


def _extra_bond(prev, nxt):
    """`krwrap.split_reason` 에 아직 없는 덩어리 — 「~ㄹ지도 모르다」 · 「해 두다/버리다/보다/주다」 꼴(공용에 넣을 후보)."""
    p = prev.rstrip(".,!?…」』)")
    if (p.endswith(("지도", "지"))) and nxt[:1] == "모":
        return "-ㄹ지도 모르다"
    if len(p) <= 2 and p[-1:] in "해아어여" and nxt[:1] in "두둬놓놔뒀보봐주줘버":
        return "-어 두다/보다/주다/버리다"
    if p.endswith("고") and len(p) >= 2 and nxt[:1] in "있계싶":
        return "-고 있다/싶다"
    if (
        len(p) >= 2
        and p[-1] in "와과"
        and nxt.startswith(("달리", "같이", "함께", "더불", "마찬가지"))
    ):
        return "-와/과 달리·같이·함께"
    #   관형형 + 의존명사(「들을 땐」 · 「끝날 때까지」 · 「있는 한」 · 「없는 한」) — 줄이 의존명사 앞에서 갈리면 뜻이 바뀌거나(「있는 한 병사」) 토막으로 읽힌다(10-28 검수)
    if len(p) >= 2 and _DEP_N.match(nxt) and (p[-1] in "는은" or _adnominal(p)):
        return "관형형+의존명사"
    #   수·단위 · 「~년 전」 — 숫자와 단위, 햇수와 「전」 을 가르지 않는다
    if (re.search(r"(?:\d+|[몇백천만억])$", p) and nxt[:1] in "년개명살번일월시분초원") or (p.endswith("년") and nxt.startswith("전")):
        return "수+단위"
    #   🔴 이름·직함 뒤 호칭은 앞 말에 붙여 읽는다(10-28 문안 검수 「라프↵씨를」 · 「쥬리오↵군에게」 · 「죠리나↵왕비」 16곳) — 호칭이 줄 머리에 오면 따로 선 낱말로 읽힌다
    if _TITLE.match(nxt.rstrip(".,!?…」』)")) and not END_RE.search(prev) and prev.rstrip(".,!?…」』)")[-1] not in "은는이가을를의에도로와과만서고며면니다요죠까나네데지자게어아해라러든께야걸들":
        return "이름+호칭"
    return None


_DEP_N = re.compile(r"^(?:때|땐|한|뿐|만큼|대로|듯|데|바)(?:까지만?|는|도|가)?[.,!?…」』)]*$")
_JOSA_T = r"(?:은|는|이|가|을|를|께|께서|도|만|의|와|과|에게|한테|께는|이라는|이란|이라고)"
#   짧은 호칭(씨·님·군·양·공)은 맨몸으로도, 긴 직함(할머니 집 처럼 뒤 명사가 따를 수 있는 말)은 조사가 붙었을 때만 묶는다
_TITLE = re.compile(rf"^(?:(?:씨|님|군|양|공){_JOSA_T}?|(?:왕비|할아버지|할머니|아저씨|선생님){_JOSA_T})$")


def bonded(prev, nxt):
    if not (prev and nxt):
        return False
    nxt = nxt.replace(GLUE, " ")
    return bool(krwrap.split_reason(prev, nxt) or _extra_bond(prev, nxt))


JOSA_END = "을를이가은는도만"
_ADV_I = {"같이", "많이", "가까이", "높이", "깊이", "일찍이", "굳이", "특히", "역시", "이미"}


def josa_end(word):
    """줄 끝에 주어·목적어만 남는 꼴 — 절 경계로 끝나는 말(「해도」 등)은 아니다."""
    w = word.rstrip(".,!?…」』)")
    if w in _ADV_I:  # 「같이」·「많이」 — 끝 글자가 이지만 조사가 아니라 부사다
        return False
    return len(w) >= 2 and w[-1] in JOSA_END and bkind(word) == 0


_NOT_NOUN_END = set(
    "은는이가을를의에도로와과만서고며면니다요죠까나네데지자게어아해라러든께야군걸들"
)
_NOT_NOUN = {
    "가장", "특히", "모두", "한층", "우선", "역시", "대체", "여태", "지금", "이제", "계속", "완전히", "원래", "여기", "그리", "또다시",
    "냉큼", "모조리", "빨리", "우리", "너희들", "여러분", "정말", "아주", "매우", "너무", "다시", "아직", "벌써", "이미", "결코",
    "반드시", "제발", "어서", "함께", "같이", "그냥", "달리", "더불어",
}  # fmt: skip
_JOSA = "은는이가을를의에도로와과만"
_PHRASES = None


def _adnominal(w):
    c = w[-1]
    if c in "던는":
        return True
    o = ord(c) - 0xAC00
    return 0 <= o < 11172 and o % 28 in (4, 8)  # 받침 ㄴ·ㄹ(관형형 -ㄴ/-ㄹ)


def noun_noun(wa, wb):
    """앞 어절이 명사 꼴이고 뒤 어절이 서술어·지시어로 시작하지 않는다(오탐은 묶어도 줄 수가 안 늘 때만이라 해가 작다)."""
    wa, wb = wa.replace(GLUE, " "), wb.replace(GLUE, " ")
    if not wa or not wb or wa in _NOT_NOUN or END_RE.search(wa):
        return False
    if wa[-1] in _NOT_NOUN_END or wa[-1] in ".,!?…」)" or _adnominal(wa):
        return False
    return not ((wb[-1] in "다요죠까" and not wb.endswith("니까")) or wb[0] in "그이저")


def stem(w):
    w = re.sub(r"(니까|이다|입니다|이에요|예요|이야|이고|이라)$", "", w)
    return w.rstrip(_JOSA + ".,!?…」") or w


def phrases():
    """대사 전량에서 같은 [앞 어절, 뒤 어절 줄기] 이음이 두 번 이상 나온 명사 구."""
    global _PHRASES
    if _PHRASES is None:
        import collections
        import itertools

        cnt = collections.Counter()
        for _key, v in blocks():
            ws = T.visible(v).replace("\n", " ").replace(T.PAGE, " ").split()
            for x, y in itertools.pairwise(ws):
                if noun_noun(x, y):
                    cnt[(x, stem(y))] += 1
        _PHRASES = {k for k, n in cnt.items() if n >= 2}
    return _PHRASES


def split_phrase(wa_last, wb_first):
    return noun_noun(wa_last, wb_first) and (wa_last, stem(wb_first)) in phrases()


def _row_list(text):
    out = []
    for pg in T.visible(text).replace("\r", "\n").split(T.PAGE):
        out += [r.strip(" ") for r in pg.split("\n") if r.strip()]
    return out


def _breaks(text):
    """줄·쪽 경계에서 갈린 [앞 어절, 뒤 어절] 쌍 모음."""
    rows = _row_list(text)
    out = set()
    for a, b in itertools.pairwise(rows):
        wa, wb = _words(a), _words(b)
        if wa and wb:
            out.add((wa[-1], wb[0]))
    return out


_FW_LATIN = {c + 0xFEE0: c for c in (*range(0x41, 0x5B), *range(0x61, 0x7B), *range(0x30, 0x3A))}


def regress(old, new):
    """f — 조판을 바꿨더니 **나빠진** 자리. 2-16 이 오히려 해치는 꼴을 센다.
    ① 새로 생긴 끊김(전에는 안 끊기던 [앞, 뒤] 쌍)이 덩어리를 가른다(`split_reason` · 굳은 명사구)
    ② 전에는 한 줄 안에 통째로 있던 문장이 후에는 여러 줄로 갈렸다.
    🔴 전각 영문(`ＮＰＣ`)은 반각(`NPC`)과 **한 낱말로** 견준다 — 약어를 전각으로 바꾼 줄이 「문장이 갈렸다」로 잡히던 오탐(10-26)."""
    old, new = old.translate(_FW_LATIN), new.translate(_FW_LATIN)
    out = []
    was = _breaks(old)
    for pair in sorted(_breaks(new) - was):
        if bonded(*pair) or split_phrase(*pair):
            out.append(f"{pair[0]}⏎{pair[1]}")
        elif josa_end(pair[0]) and not END_RE.search(pair[0]):  # 목적어·주어만 줄 끝에 새로 남음
            out.append(f"{pair[0]}⏎{pair[1]} (조사 끝)")

    #   ③ 문장 도중 줄 끝 가운데 절 경계가 아닌 것이 단위 안에서 늘었다(「있으면 좋으련만⏎」→「있으면⏎좋으련만 …」 꼴)
    def mid_nonclause(t):
        rows = _row_list(t)
        n = 0
        for a, _b in itertools.pairwise(rows):
            wa = _words(a)
            if wa and not END_RE.search(a) and bkind(wa[-1]) == 0:
                n += 1
        return n

    if mid_nonclause(new) > mid_nonclause(old):
        out.append(f"절 경계 아닌 줄 끝 {mid_nonclause(old)}→{mid_nonclause(new)}")
    new_rows = [r.replace(" ", "") for r in _row_list(new)]

    #   ④ 쪽 경계(창 끝)를 문장 끝·절 경계 밖으로 옮겼다 — 전에 문장 끝이던 쪽 끝을 문장 도중으로 옮기는 이동 포함
    def cut_rows(t):
        return [
            pg.rstrip().rsplit("\n", 1)[-1].strip(" ")
            for pg in T.visible(t).split(T.PAGE)[:-1]
            if pg.strip()
        ]

    oc, nc = cut_rows(old), cut_rows(new)
    if sum(1 for r in nc if not page_cut_ok(r)) > sum(1 for r in oc if not page_cut_ok(r)):
        out.append("쪽 끝이 절 경계 밖으로 이동")
    if sum(1 for r in nc if not END_RE.search(r)) > sum(1 for r in oc if not END_RE.search(r)):
        out.append("문장 끝이던 쪽 끝이 문장 도중으로 이동")
    olds = _row_list(old)
    for ri, row in enumerate(olds):
        starts = ri == 0 or bool(END_RE.search(olds[ri - 1]))  # 문장을 이 줄에서 시작한다
        sents = krwrap.split_sentences(row)
        if (
            starts
            and len(sents) == 1
            and END_RE.search(row)
            and not any(row.replace(" ", "") in r for r in new_rows)
        ):
            out.append(f"문장 갈림: {row}")
    #   ⑤ 전에 한 줄 안에 통째로 있던 절(두 어절 이상)이 후에는 여러 줄로 갈렸다
    for row in olds:
        ws = _words(row)
        seg = []
        for wi, w in enumerate(ws):
            seg.append(w)
            if bkind(w) >= 1 or wi == len(ws) - 1:
                last_open = (
                    wi == len(ws) - 1 and bkind(w) == 0
                )  # 줄 끝에서 열린 채 끝난 토막은 앞 줄에서 이어진 것일 수 있다
                if len(seg) >= 2 and not last_open and not any("".join(seg) in r for r in new_rows):
                    out.append(f"절 갈림: {' '.join(seg)}")
                seg = []

    #   덩어리를 가른 줄 끝(「하면⏎되나요」)을 **고치는** 이동은 절 단위 규칙(③·⑤)보다 앞선다 — 덩어리를 푸는 값이 더 크다
    def bonded_cuts(t):
        return sum(1 for pr in _breaks(t) if bonded(*pr))

    if bonded_cuts(new) < bonded_cuts(old):
        out = [m for m in out if not m.startswith(("절 경계 아닌", "절 갈림", "문장 갈림"))]
    return out


def page_cut_ok(row):
    """이 줄 뒤에서 쪽을 끊어도 되나 — 문장 끝이거나 절 경계(쉼표·연결어미)일 때만."""
    row = row.strip()
    if not row:
        return True
    if END_RE.search(row):
        return True
    w = _words(row)
    return bool(w) and bkind(w[-1]) >= 1


def balanced_possible(rows, P):
    """같은 쪽 수 P 로 (쪽 끝은 page_cut_ok 인 자리만) 줄 수 차 ≤1 로 나눌 수 있나."""
    import itertools

    n = len(rows)
    if P < 2 or n > 18 or n < P:
        return False
    for cuts in itertools.combinations(range(1, n), P - 1):
        if not all(page_cut_ok(rows[c - 1]) for c in cuts):
            continue
        b = (0, *cuts, n)
        sz = [b[i + 1] - b[i] for i in range(P)]
        if max(sz) <= 3 and max(sz) - min(sz) <= 1:
            return True
    return False


ITEM_RX = re.compile(r"<01><([0-9A-Fa-f]{2})>(을\(를\)|이\(가\)|은\(는\)|과\(와\)|으\(로\))?")
JOSA_PH = {
    "을(를)": "\ue0f0",
    "이(가)": "\ue0f1",
    "은(는)": "\ue0f2",
    "과(와)": "\ue0f3",
    "으(로)": "\ue0f4",
}
FULL_PH = "\ue0ff"


def expand_names(text):
    """인라인 아이템 코드(`<01><번호>`)를 **실제 이름 폭의 낱말**로 바꿔 돌려준다 — `(바뀐 문안, 되돌리기 함수)`. 번역 규칙 2-16 ⑤.

    이름은 PARAM 아이템 이름(사전에 없으면 전각 8자=최악), 병기 조사 `을(를)` 은 빌드 때 한 글자로 줄어 한 칸으로 센다.
    자리표시는 이름 첫 글자 자리에 코드마다 다른 사설 문자(`\ue100+`)를 두고 나머지는 같은 폭의 글자로 채운다 — 되돌릴 때 통째로 바꾼다.
    첫 글자가 전각이 아닌 이름이 있으면 바꾸지 않는다(`(원문, 항등)`)."""
    if "<01>" not in text:
        return text, lambda t: t
    import inline_josa as J

    names = J.item_names()
    table = {}
    ids = {}

    def one(m):
        iid = int(m.group(1), 16)
        name = names.get(iid, "가" * 8)
        if ord(name[0]) < 0x80:
            raise ValueError
        idx = ids.setdefault(iid, len(ids))
        body = chr(0xE100 + idx) + "".join(
            GLUE if c == " " else ("x" if ord(c) < 0x80 else FULL_PH) for c in name[1:]
        )
        ph = body + (JOSA_PH[m.group(2)] if m.group(2) else "")
        table[ph] = m.group(0)
        return ph

    try:
        new = ITEM_RX.sub(one, text)
    except ValueError:
        return text, lambda t: t

    def restore(t):
        for ph, orig in table.items():
            t = t.replace(ph, orig)
        return t

    return new, restore


def names():
    import canon

    return sorted({kr for _, _, kr in canon.all_names("ed3") if " " in kr}, key=len, reverse=True)


def protect(s, nms):
    for n in nms:
        if n in s:
            s = s.replace(n, n.replace(" ", GLUE))
    return s


def _words(row):
    return [w for w in row.split(" ") if w]


def clause_tail(wa, wb):
    """줄 끝에서 끊긴 자리 `wa | wb` 에서, **마지막 절 경계 뒤 앞 줄 어절 + 뒤 줄의 그 절 끝까지**가 한 줄에 드는 후보.
    `(경계 색인, 내릴 줄 문자열)` 또는 None."""
    for i in range(
        len(wa) - 2, -1, -1
    ):  # 앞 줄 끝 어절(i = len-1)은 경계가 아니다 — 거기서는 끊겨 있다
        if bkind(wa[i]) == 0 or bonded(wa[i], wa[i + 1]):
            continue
        head = " ".join(wa[: i + 1])
        if wcols(head) < MIN_LEFT:
            continue
        tail = list(wa[i + 1 :])
        for w in wb:
            tail.append(w)
            if bkind(w) >= 1:
                break
        line = " ".join(tail)
        if fits(line):
            return i, line
    return None


def scan(text, nms=()):
    """한 블록 → `{종류: [설명]}`."""
    out = {k: [] for k in KINDS}
    text, _ = expand_names(text)
    text = protect(T.visible(text).replace("\r", "\n"), nms)
    pages = []
    for pg in text.split(T.PAGE):
        rows = [r.strip(" ") for r in pg.split("\n") if r.strip()]
        if rows:
            pages.append(rows)
    if len(pages) >= 2:
        last = pages[-1]
        prev_end = pages[-2][-1]
        if (
            len(last) == 1
            and len(_words(last[0])) == 1
            and len(re.sub(r"[.,!?…〜~]", "", last[0])) > 2
            and not END_RE.search(prev_end)
        ):
            out["h"].append(f"{prev_end}▼{last[0]}")
        sz = [len(p) for p in pages]
        if max(sz) - min(sz) >= 2 and balanced_possible([r for p in pages for r in p], len(pages)):
            out["h2"].append("/".join(map(str, sz)))
    for pi, rows in enumerate(pages):
        for ri in range(len(rows) - 1):
            a, b = rows[ri], rows[ri + 1]
            if END_RE.search(a):
                continue
            #   괄호 속말은 원문이 **한 덩이 = 한 줄**이다(10-28 검수) — 괄호가 닫히고 다음 괄호가 열리는 줄바꿈은 일부러 낸 것이라 손 개행이 아니다
            if a.endswith(")") and b.startswith("("):
                continue
            wa, wb = _words(a), _words(b)
            if not wa or not wb:
                continue
            if split_phrase(wa[-1], wb[0]):
                out["e"].append(f"{a}⏎{b}")
            first = wb[0]
            if fits(a + " " + first):
                nxt_clause = []
                for w in wb:
                    nxt_clause.append(w)
                    if bkind(w) >= 1:
                        break
                cl = " ".join(nxt_clause)
                ok = bkind(wa[-1]) >= 1 and not fits(a + " " + cl)
                #   첫 어절을 올리면 다음 끊김이 덩어리를 가르는 경우(「벌써⏎순례를」 꼴)는 앞 줄을 일찍 끊은 게 맞다
                #   앞 줄을 채워 가다 보면 끊기는 자리(탐욕)가 덩어리를 가르면 조판기는 한두 낱말 일찍 끊는다 — 그 경우도 정상이다
                j = len(wa)
                while j < len(wa) + len(wb) and fits(" ".join((wa + wb)[: j + 1])):
                    j += 1
                allw = wa + wb
                if j < len(allw) and any(
                    bonded(allw[m - 1], allw[m]) or split_phrase(allw[m - 1], allw[m])
                    for m in (j, j - 1)
                    if m > len(wa)
                ):
                    ok = True
                if not ok:
                    out["c"].append(f"{a}⏎{b}")
            elif clause_tail(wa, wb):
                out["d"].append(f"{a}⏎{b}")
        if pi + 1 < len(pages):
            last, nxt = rows[-1], pages[pi + 1][0]
            if END_RE.search(last):
                continue
            wl, wn = _words(last), _words(nxt)
            if (
                len(wl) == 1 and len(re.sub(r"[.,!?…〜~]", "", wl[0])) > 2
            ):  # 「앗」「엇?」 같은 한두 글자 감탄은 한 박자(쪽)다 — 고아가 아니다
                out["a"].append(f"{last}▼{nxt}")
            elif wl and wn and bonded(wl[-1], wn[0]):
                out["b"].append(f"{last}▼{nxt}")
    return out


def blocks():
    narr = {(n, str(i)) for n, i, _ in CN.targets()}
    for f in sorted(glob.glob(os.path.join(SCRIPT, "MAP*.json"))):
        n = os.path.basename(f)
        with open(f, encoding="utf-8") as fh:
            doc = json.load(fh)
        for k, v in doc.items():
            if k.startswith("_") or not isinstance(v, str) or (n, k) in narr:
                continue
            if "\n" not in v and "\f" not in v:
                continue
            yield f"{n[:-5]}#{k}", v


def measure():
    nms = names()
    tot = {k: 0 for k in KINDS}
    blk = {k: 0 for k in KINDS}
    ex = {k: [] for k in KINDS}
    n = 0
    with open(ORIG_PAGES, encoding="utf-8") as fh:
        orig_h2 = set(json.load(fh)["h2"])
    exempt = _restore_keys()
    for key, v in blocks():
        n += 1
        if key in exempt:  # 2-17: 원문 창이 문장 한복판에서 갈리면 우리도 거기서 가른다 — 지표(쪽 끝 한 어절 등)는 허용분
            continue
        r = scan(v, nms)
        if key in orig_h2:
            r["h2"] = []
        for k in KINDS:
            if r[k]:
                blk[k] += 1
                tot[k] += len(r[k])
                ex[k].append((key, r[k][0]))
    return n, tot, blk, ex


def _restore_keys():
    if not os.path.exists(WINDOW_RESTORE):
        return set()
    with open(WINDOW_RESTORE, encoding="utf-8") as fh:
        return set(json.load(fh)["blocks"])


def fewer_windows():
    """규칙 2-17 「적음」 축 — 원문(`work/derived/map_jp`)보다 창(`\\f` 구간)이 적은 블록 키. 원문이 없으면 None(못 쟀다)."""
    jp_dir = os.path.join(C.OUT_DIR, "map_jp")
    if not os.path.isdir(jp_dir):
        return None
    out = []
    for f in sorted(glob.glob(os.path.join(SCRIPT, "MAP*.json"))):
        n = os.path.basename(f)
        jp_path = os.path.join(jp_dir, n)
        if not os.path.exists(jp_path):
            continue
        with open(jp_path, encoding="utf-8") as fh:
            jb = json.load(fh)["blocks"]
        with open(f, encoding="utf-8") as fh:
            doc = json.load(fh)
        for i, j in enumerate(jb):
            k = doc.get(str(i))
            if not isinstance(k, str) or not j["text"]:
                continue
            if k.count("\f") < j["text"].count("\f"):
                out.append(f"{n[:-5]}#{i}")
    return out


def _load_base():
    with open(BASELINE, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument(
        "--f", metavar="REF", help="퇴행 f — REF 의 script/ 와 지금을 견줘 나빠진 자리를 센다"
    )
    a = ap.parse_args()
    if a.f:
        import subprocess

        if subprocess.run(
            ["git", "rev-parse", "--verify", "-q", f"{a.f}^{{commit}}"],
            capture_output=True,
            check=False,
        ).returncode:
            #   기준 ref 는 이 저장소 안에만 있다(`backup/…`, 원격엔 안 올린다) — 없으면 못 쟀다고 크게 알린다
            print(f"  ⚠ 퇴행 f 는 못 쟀다 — 기준 {a.f} 가 이 저장소에 없다")
            return
        f = 0
        shown = 0
        for fn in sorted(glob.glob(os.path.join(SCRIPT, "MAP*.json"))):
            stem = os.path.basename(fn)
            old = json.loads(
                subprocess.run(
                    ["git", "show", f"{a.f}:games/ss-ed3/script/{stem}"],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            )
            with open(fn, encoding="utf-8") as fh:
                new = json.load(fh)
            for k, v in new.items():
                if (
                    isinstance(v, str)
                    and isinstance(old.get(k), str)
                    and v != old[k]
                    and not k.startswith("_")
                ):
                    bad = regress(old[k], v)
                    f += len(bad)
                    if bad and shown < a.show:
                        shown += 1
                        print(f"    f {stem[:-5]}#{k}  {bad[0]}")
        print(f"  퇴행 f ({a.f} 대비) {f}")
        if a.check and f:
            sys.exit(1)
        return
    n, tot, blk, ex = measure()
    print(
        f"  줄·쪽 나눔 지표 [ss-ed3 · 씬 대사 {n:,} 블록]  "
        + " · ".join(f"{k} {tot[k]}({blk[k]}블록)" for k in KINDS)
    )
    for k in KINDS:
        for key, s in ex[k][: a.show]:
            print(f"    {k} {key}  {s}")
    if a.freeze:
        old = _load_base() if os.path.exists(BASELINE) else {}
        new = {k: min(tot[k], old.get(k, tot[k])) if old else tot[k] for k in KINDS}
        with open(BASELINE, "w", encoding="utf-8") as fh:
            json.dump(new, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print(f"  기준선 → {new}")
        return
    fw = fewer_windows()
    if fw is None:
        print("  ⓘ 창 수 「적음」 은 못 쟀다 — work/derived/map_jp 가 없다")
    else:
        print(f"  창 수 「적음」(원문보다 창이 적은 블록, 규칙 2-17) {len(fw)}")
        for key in fw[: max(a.show, 5)]:
            print(f"    적음 {key}")
        if a.check and fw:
            print("  ❌ 원문보다 창이 적은 블록이 있다 — 원문 창대로 가른다(규칙 2-17)")
            sys.exit(1)
    if a.check:
        if not os.path.exists(BASELINE):
            print("  ❌ 기준선이 없다 — --freeze 로 만든다")
            sys.exit(1)
        base = _load_base()
        bad = [k for k in KINDS if tot[k] > base.get(k, 0)]
        if bad:
            print(
                "  ❌ 기준선보다 늘었다: "
                + ", ".join(f"{k} {base.get(k, 0)}→{tot[k]}" for k in bad)
            )
            sys.exit(1)
        shrunk = [k for k in KINDS if tot[k] < base.get(k, 0)]
        print(
            "  ✅ 기준선 이하"
            + (f" — 줄었다({', '.join(shrunk)}): --freeze 로 내린다" if shrunk else "")
        )


if __name__ == "__main__":
    main()
