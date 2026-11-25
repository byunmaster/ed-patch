"""ED4 조판 — 우리 문안을 **대사창 24칸 격자**에 맞춰 줄·쪽으로 나눈다(ED3 `typeset` 의 ED4 몫, 규격은 `docs/wrap.md`).

엔진은 **조각 안 글자를 24칸째에서 저절로 접는다**(낱말·금칙 안 봄 — 시험 빌드 실측). 그래서 우리가 어절 단위로 나눈 줄을 엔진 접힘과 맞추려면 **각 줄을 공백 코드로
24칸까지 채워** 한 조각에 이어 붙인다(`pad_rows` — ED3 와 같은 발상). 🔴 **한 쪽은 3줄(72칸)이 한도이고 넘치는 글은 조용히 사라진다**(▼ 로 이어지지 않는다 — 시험 빌드 실측).
쪽 경계는 스크립트(`02`)가 정하므로 쪽 수는 못 늘린다 — 문안을 원래 쪽 구조(`windows`)에 맞춘다.

🔴 **줄 한도는 둘이고 둘 다 건다**(관리자 10-24): ① 글리프 24개 이하(엔진이 칸 수로 센다 — 반각 훅도 이건 못 바꾼다) ② 픽셀 폭 288 이하(`halfwidth.py` 훅이 반각을 6px 로 앉힌다).
글리프가 12px 이하니 ①을 지키면 ②는 늘 따라온다 — 그래서 줄바꿈은 글리프 수로 하고 ②는 단언으로 둔다. 반각 때문에 생기는 줄 끝 여백은 그대로 둔다
(용량은 쪽 늘리기가 받는다 — 줄바꿈 연산까지 건드리는 패치는 안 한다).
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import choice
from shared.ps1 import gmf_script as _sm
from shared.text import krwrap

COLS = 24  # 격자 열 수 = 한 줄 칸 수(조각 안에서 24칸째에 엔진이 접는다)
PAGE_LINES = 3  # 한 쪽 줄 수(차면 ▼)
CELL_PX = 12
STRIP_AFTER = ""  # 반각 훅이 섰으니 부호 뒤 공백을 지우지 않는다(번역 규칙 「공백 유지」)
LINE_PX = COLS * CELL_PX  # 288
SPACE = " "


def _widths():
    import hangul

    return {ch: 6 for ch in (" ", "「", "」", "『", "』", *hangul.load_half())}  # 「」『』 = 대사에선 반각 글리프로 바뀐다(reinsert.KAGI)


WIDTHS = _widths()  # {글자: px} — 반각 6px, 나머지 12px


class TypesetError(Exception):
    pass


def px_width(text):
    """줄의 픽셀 폭 — 반각은 6, 나머지 12."""
    return sum(WIDTHS.get(c, CELL_PX) for c in text)


# 🔴 끊을 자리 고르기(마스터 10-25 「개행 손봐야할듯. 꽃 따기 같은건 한줄로」) — krwrap 은 줄이 찰 때까지 채우므로 짧은 명사구가 반으로 갈린다.
#    같은 줄 수 안에서(쪽 수 불변) 끊는 자리를 문장 끝 > 쉼표 > 연결어미 > 그 밖 순으로 고른다. 공용 krwrap 은 동결이라 여기서만 한다.
_END_RE = re.compile(r"[.?!…][\"'」』”’)]*$")
_CONN_RE = re.compile(r"(며|면서|면|고|서|니까|는데|은데|인데|지만|으나|거나|다가|려고|도록)$")
_CLOSERS = ".,?!…~)」』”’"
COST_END, COST_COMMA, COST_CONN, COST_PLAIN = 0, 1, 2, 5
COST_INTERJ = 9  # 감탄사+쉼표(「오,」) 뒤 — 감탄사는 뒷말과 붙어야 한다
COST_SHORT = 6  # 너무 짧은 줄(조각 하나만 남은 줄)


# 앞낱말에 붙어야 하는 말 — 줄머리에 오면 어색하다(의존명사) · 뒷말에 붙어야 하는 말(관형사·수)은 줄 끝에 오면 어색하다
_BOUND_NEXT = {"때", "것", "수", "줄", "데", "뿐", "번", "듯", "채", "적", "리", "바", "분", "만큼", "대로", "정도", "쪽", "곳", "중", "뒤", "앞"}
_DET_PREV = {"한", "두", "세", "네", "이", "그", "저", "어떤", "무슨", "어느", "새", "온", "모든", "이런", "그런", "저런", "다른", "큰", "작은", "아무"}
SHORT_GLYPHS = 4  # 공백 뺀 글자가 이만큼 이하인 줄은 짧은 줄


def _break_cost(prev, word, nxt):
    """낱말 `word` 뒤에서 줄을 끊는 값(낮을수록 좋다). `prev` = 그 앞 낱말(없으면 ""), `nxt` 가 닫는 부호로 시작하면 못 끊는다(None)."""
    if nxt[:1] and nxt[:1] in _CLOSERS:
        return None
    if word in _DET_PREV or nxt in _BOUND_NEXT:
        return COST_INTERJ
    if _END_RE.search(word):
        return COST_END
    if word.endswith(","):
        # 문장 첫머리의 짧은 감탄사+쉼표(「오,」「아,」) 뒤는 끊지 않는다
        if len(word.rstrip(",")) <= 2 and (not prev or _END_RE.search(prev)):
            return COST_INTERJ
        return COST_COMMA
    if _CONN_RE.search(word):
        return COST_CONN
    return COST_PLAIN


# 🔴 규칙 2-16(마스터 10-26 줄·쪽 나눔 전면 규칙) — 절째 내리기 · 쪽 끝 고아 · 보조용언 자리 쪽 끊기 · 띄어 쓴 고유명사 한 줄.
_HEAD_CONJ = {"그리고", "그러나", "하지만", "그래서", "그런데", "그러면", "그럼", "또한", "그러니까", "따라서", "그래도", "그러자", "그렇다면"}
_AUX_RE = re.compile(r"^(주[세시겠마자는며]|주$|주다|줘|봐|보[자세겠았]|두[자세겠었]|두$|둬|놓[아았자세]|버[렸리려]|있[어었는다자]|있$|않|못[한하]|싶)")
_AUX_PREV_RE = re.compile(r"[아어여해게지고서]$")
MIN_HEAD = 8  # 절째 내릴 때 앞 줄에 남아야 할 최소 글자(공백 뺀)
RULES_216 = os.environ.get("ED_NO216") != "1"  # 규칙 2-16 후처리 끄기(지표 「전」 계측용)


def _nouns():
    """띄어 쓴 정본 고유명사(공백 포함) → 낱말 열 — 줄 사이에서 안 갈린다(규칙 2-16 ④). 정본은 읽기만 한다."""
    global _NOUNS
    if _NOUNS is None:
        import json

        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared", "canon", "nouns", "ed4.json")
        try:
            with open(path, encoding="utf-8") as f:
                cats = json.load(f)["categories"]
            _NOUNS = sorted({tuple(v.split(" ")) for c in cats.values() for v in c.values() if v and " " in v})
        except OSError:
            _NOUNS = []
    return _NOUNS


_NOUNS = None


def _glued(words):
    """못 끊는 자리의 집합 — `j` = 낱말 `j-1` 과 `j` 사이. 띄어 쓴 고유명사 속(끝 낱말엔 조사가 붙을 수 있다)."""
    out = set()
    for nz in _nouns():
        k = len(nz)
        for i in range(len(words) - k + 1):
            if all(words[i + t] == nz[t] for t in range(k - 1)) and words[i + k - 1].startswith(nz[-1]):
                out.update(range(i + 1, i + k))
    return out


def _is_bound(word, prev=""):
    """절 경계(문장 끝 · 쉼표 · 연결어미) — 문장 머리 접속어·두 음절 이하 쉼표는 경계 아님."""
    if word in _HEAD_CONJ:
        return False
    if _END_RE.search(word):
        return True
    if word.endswith(","):
        return not (len(word.rstrip(",")) <= 2 and (not prev or _END_RE.search(prev)))
    return bool(_CONN_RE.search(word))


_NOT_NOUN_END = set("은는이가을를의에도로와과만서고며면니다요죠까나네데지자게어아해라러든께야군걸들")
_NOT_NOUN = {
    "가장", "특히", "모두", "한층", "우선", "역시", "대체", "여태", "지금", "이제", "계속", "완전히", "원래",
    "여기", "그리", "또다시", "냉큼", "모조리", "빨리", "우리", "너희들", "여러분", "정말", "아주", "매우",
    "너무", "다시", "아직", "벌써", "이미", "결코", "반드시", "제발", "어서", "함께", "같이", "그냥",
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
    """[명사+명사] 꼴인가(2-16 e) — 형태소 분석기 없이 앞 어절이 조사·어미·관형형·부사로 안 끝나면 명사로 본다."""
    if not wa or not wb or wa in _NOT_NOUN or wa.rstrip(_CLOSERS) != wa:
        return False
    if wa[-1] in _NOT_NOUN_END or _adnominal(wa):
        return False
    return not (wb[-1] in "다요죠까" or wb[0] in "그이저")


def _stem(w):
    return w.rstrip(_JOSA + ".,!?…」") or w


def phrases():
    """대사 전량(번역 정본)에서 같은 [앞 어절, 뒤 어절 줄기] 이음이 두 번 이상 나온 명사 구 — 반복이 굳은 구라는 증거."""
    global _PHRASES
    if _PHRASES is None:
        import collections
        import glob
        import itertools
        import json

        cnt = collections.Counter()
        for f in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "script", "*.json")):
            with open(f, encoding="utf-8") as fh:
                segs = json.load(fh)["segments"]
            for v in segs.values():
                ws = (v["kr"] or "").split()
                for x, y in itertools.pairwise(ws):
                    if noun_noun(x, y):
                        cnt[(x, _stem(y))] += 1
        _PHRASES = {k for k, n in cnt.items() if n >= 2}
    return _PHRASES


def is_nounphrase_split(line_a, line_b):
    """줄 끝 낱말과 다음 줄 첫 낱말이 굳은 명사 구인가 — (e) 지표·고치기 공용."""
    wa, wb = line_a.split(" ")[-1], line_b.split(" ")[0]
    return noun_noun(wa, wb) and (wa, _stem(wb)) in phrases()


def _short(line):
    return len(line.replace(" ", "")) <= SHORT_GLYPHS


def _fit(line, cols):
    return len(line) <= cols and px_width(line) <= cols * CELL_PX


def _cost_of(lines):
    """줄 목록의 끊는 값 합(마지막 줄 끝은 제외) + 짧은 줄 벌점 + 띄어 쓴 고유명사가 줄 사이에서 갈린 벌점."""
    total = 0
    allw = " ".join(lines).split(" ")
    cut, glue = 0, _glued(allw)
    for ln in lines[:-1]:
        cut += len(ln.split(" "))
        if cut in glue:
            total += COST_PLAIN * 4
    for i, ln in enumerate(lines):
        if i < len(lines) - 1:
            ws = ln.split(" ")
            c = _break_cost(ws[-2] if len(ws) > 1 else "", ws[-1], lines[i + 1].split(" ")[0] if lines[i + 1] else "")
            total += COST_PLAIN * 4 if c is None else c
        if _short(ln):
            total += COST_SHORT
    return total


def _refine(text, out, cols):
    """`out`(krwrap 결과)과 **같은 줄 수**로 끊는 자리만 다시 고른다. 더 낫지 않으면 `out` 을 그대로 둔다(결정적)."""
    n = len(out)
    words = text.split(" ")
    if n < 2 or n > 6 or any(not w for w in words):
        return out
    m = len(words)
    glue = _glued(words)
    best = {}  # (줄 수, 시작 낱말) → (값, 줄 목록)

    def solve(k, i):
        if (k, i) in best:
            return best[(k, i)]
        res = None
        for j in range(i + 1, m + 1):
            line = " ".join(words[i:j])
            if not _fit(line, cols):
                break
            if k == 1:
                if j != m:
                    continue
                cand = (COST_SHORT if _short(line) else 0, [line])
            else:
                if j == m:
                    break
                c = _break_cost(words[j - 2] if j > 1 else "", words[j - 1], words[j])
                if c is None or j in glue:
                    continue
                sub = solve(k - 1, j)
                if sub is None:
                    continue
                cand = (
                    c + (COST_SHORT if _short(line) else 0) + sub[0],
                    [line, *sub[1]],
                )
            if res is None or cand[0] < res[0]:
                res = cand
        best[(k, i)] = res
        return res

    got = solve(n, 0)
    if got is None or got[0] >= _cost_of(out):
        return out
    return got[1]


_LIST_RE = re.compile(r"^(?:[ㄱ-ㅎ가-힣]행)?【")


def is_listish(texts):
    """항목 줄(사전·목록 — `ㄱ행【…】`·`【…】` 글머리) 이 든 쪽인가 — 항목 줄은 손 개행을 지킨다(조판 규칙 밖, 2-16)."""
    return any(_LIST_RE.match((t or "").strip()) for t in texts)


def d_count(lines, cols=COLS):
    """(d) 절째 내리면 들어가는데 쪼갠 줄 수."""
    n = 0
    for k in range(len(lines) - 1):
        w = lines[k].split(" ")
        if len(w) < 2 or _is_bound(w[-1], w[-2]):
            continue
        bs = [j for j in range(len(w) - 1) if _is_bound(w[j], w[j - 1] if j else "")]
        if not bs:
            continue
        j = bs[-1]
        nx = lines[k + 1].split(" ")
        e = next((t for t, x in enumerate(nx) if _is_bound(x, nx[t - 1] if t else "")), None)
        if e is None or len(" ".join(w[: j + 1]).replace(" ", "")) < MIN_HEAD:
            continue
        if _fit(" ".join(w[j + 1 :] + nx[: e + 1]), cols):
            n += 1
    return n


def _modifier_cut(wa, wb):
    """[명사 + 관형형] 꾸밈구(「유서 깊은」「죄 없는」)를 가르는 끊김인가 — 앞이 조사·어미 없는 낱말, 뒤가 관형형."""
    if not wa or not wb or wa in _NOT_NOUN or wa[-1] in _JOSA or wa[-1] in ".,!?…」" or _adnominal(wa):
        return False  # 앞이 조사로 끝나면 꾸밈구가 아니다(「서」「고」 같은 어미 글자는 명사 끝일 수 있다 — 유서)
    return len(wb) >= 2 and wb[-1] not in ".,!?…」다요죠까" and _adnominal(wb) and wb[-1] in "은는던"


def _score(lines):
    """나쁜 자리 수 — (d) 절 쪼갬 + (e) 명사 구 갈림 + 쪼개면 안 되는 덩어리 끊김 + 꾸밈구 갈림. 줄이 느는 이동은 이게 줄어야 한다."""
    n = d_count(lines)
    for k in range(len(lines) - 1):
        wa, wb = lines[k].split(" ")[-1], lines[k + 1].split(" ")[0]
        if len(lines[k].split(" ")) >= 2 and is_nounphrase_split(lines[k], lines[k + 1]):
            n += 1
        if krwrap.split_reason(wa, wb) or _modifier_cut(wa, wb):
            n += 1
    return n


def _cuts(lines):
    """줄 경계가 선 낱말 위치(낱말 `j` 앞) 목록."""
    out, c = [], 0
    for ln in lines[:-1]:
        c += len(ln.split(" "))
        out.append(c)
    return out


def regressions(old, new):
    """`old` → `new`(같은 글) 에서 **새로 생긴** 나쁜 끊김 수(규칙 2-16 f) — ① 새 끊김이 `krwrap.split_reason`(보조용언·의존명사·관형사 고아 …)에 걸림
    ② 전에는 한 줄이던 문장이 새로 갈림. 규칙이 오히려 나쁘게 만든 꼴을 세고, 후처리는 이게 늘면 그 이동을 거부한다."""
    wo, wn = " ".join(old).split(" "), " ".join(new).split(" ")
    if wo != wn:
        return 0
    co = set(_cuts(old))
    n = 0
    for c in _cuts(new):
        if c not in co and (krwrap.split_reason(wn[c - 1], wn[c]) or _modifier_cut(wn[c - 1], wn[c])):
            n += 1
    # ③ 전엔 줄 끝이 절 경계(문장 끝·쉼표·연결어미)였는데 후엔 아니게 된 줄 — 절 경계에서 끊은 줄이 줄어들면 퇴행
    def nb(cuts):
        return sum(1 for c in cuts if _is_bound(wn[c - 1], wn[c - 2] if c > 1 else ""))

    n += max(0, nb(co) - nb(_cuts(new)))
    # ④ 쪽 경계(3줄째 끝) — 새 쪽 경계는 절 경계(문장 끝 > 쉼표·연결어미)여야 하고, 문장 끝이던 쪽 경계를 문장 중간으로 옮기면 퇴행
    po, pn = _cuts(old)[PAGE_LINES - 1 :: PAGE_LINES], _cuts(new)[PAGE_LINES - 1 :: PAGE_LINES]
    def pb(cuts):
        return sum(1 for c in cuts if _is_bound(wn[c - 1], wn[c - 2] if c > 1 else ""))

    n += max(0, pb(po) - pb(pn))  # 절 경계였던 쪽 경계가 절 경계 아닌 곳으로 옮겨 갔다
    n += max(0, sum(1 for c in po if _END_RE.search(wn[c - 1])) - sum(1 for c in pn if _END_RE.search(wn[c - 1])))
    # 문장(문장 끝 낱말까지) 단위로 — 이전엔 한 줄 안이던 문장이 갈렸나
    bounds, st = [], 0
    for j, w in enumerate(wn):
        if _END_RE.search(w) or j == len(wn) - 1:
            bounds.append((st, j))
            st = j + 1
    cn = set(_cuts(new))
    for a, b in bounds:
        split_new = any(a < c <= b for c in cn)
        split_old = any(a < c <= b for c in co)
        if split_new and not split_old:
            n += 1
    return n


def page_counts(lines, page_lines=PAGE_LINES):
    """쪽(엔진이 3줄마다 넘기는 창)마다 줄 수."""
    return [min(page_lines, len(lines) - k) for k in range(0, len(lines), page_lines)]


def lonely_last(lines):
    """(h) 창이 둘 이상인데 마지막 창에 한 어절만 남았나."""
    pc = page_counts(lines)
    return len(pc) >= 2 and pc[-1] == 1 and " " not in lines[-1]


def balance(text, lines, nseg, *, cols=COLS):
    """(h·h2) 창(쪽) 수는 그대로 두고 마지막 창이 비면 **줄 폭을 좁혀** 다시 나눠 마지막 창에 줄을 더한다. 못 하면 None.
    조각 수 안(`_pieces_fit`)·나쁜 자리 수(`_score`)가 안 느는 것만 받는다."""
    pc = page_counts(lines)
    if len(pc) < 2 or pc[-1] > pc[0] - 2:
        return None
    for w in range(cols - 1, 13, -1):
        try:
            new = rows(text, cols=w, paged=True, nseg=nseg)
        except TypesetError:
            continue
        pn = page_counts(new)
        if len(pn) != len(pc) or pn[-1] < 2 or not _pieces_fit(len(new), nseg):
            continue
        if _score(new) > _score(lines) or regressions(lines, new):
            continue
        return new
    return None


def _pieces_fit(nlines, nseg):
    """줄 `nlines` 개를 조각 `nseg` 개에 놓을 수 있나 — 줄마다 한 조각, 남는 줄은 마지막 조각에 패딩으로(`page_segments` 와 같은 셈). 쪽 한도 안에서 줄이 안 사라져야 한다."""
    if nseg < 1:
        return False
    per = [1] * (nseg - 1) + [max(1, nlines - (nseg - 1))] if nlines > nseg else [1] * nlines + [0] * (nseg - nlines)
    return _sim_rows(per) is None


def _sent_end(word):
    return bool(_END_RE.search(word)) or word.endswith("～")  # 「잘 가～」 — 물결 맺음도 문장 끝이다


def one_line_sentences(lines, cols=COLS, final=True):
    """(2-10) 한 줄에 들어가는 문장(≤ `cols` 글리프·px)이 같은 쪽 안에서 두 줄로 갈린 곳 — [(문장 낱말 `(줄, 낱말)` 목록)]. 쪽 경계는 안 센다.
    `final` = 글이 여기서 끝나나 — 끝 부호 없이 끝난 마지막 토막은 다음 쪽으로 이어질 수 있어 끝일 때만 센다."""
    words = [(k, w) for k, ln in enumerate(lines) for w in ln.split(" ") if w]
    out, cur = [], []
    for k, w in words:
        cur.append((k, w))
        if _sent_end(w):
            out.append(cur)
            cur = []
    if cur and final:
        out.append(cur)
    bad = []
    for sent in out:
        ks = sorted({k for k, _ in sent})
        if len(ks) < 2 or ks[-1] // PAGE_LINES != ks[0] // PAGE_LINES:
            continue
        txt = " ".join(w for _, w in sent)
        if _fit(txt, cols):
            bad.append(sent)
    return bad


def _pack_sentences(words, cols):
    """낱말 목록 → 문장 단위로 줄에 담는다(한 줄에 들어가는 문장은 쪼개지 않고, 한 줄보다 긴 문장만 `rows` 로 나눈다)."""
    sents, cur = [], []
    for w in words:
        cur.append(w)
        if _sent_end(w):
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)
    out, line = [], ""
    for sw in sents:
        t = " ".join(sw)
        if _fit(t, cols):
            if line and _fit(line + " " + t, cols):
                line += " " + t
            else:
                if line:
                    out.append(line)
                line = t
        else:
            if line:
                out.append(line)
                line = ""
            out.extend(rows(t, cols=cols))
    if line:
        out.append(line)
    return out


def _sentence_lines(lines, cols, nseg=0):
    """2-10 후처리 — 한 줄에 들어가는 문장이 같은 쪽 안에서 갈렸으면 **새 줄에서 시작**한다: 갈린 문장의 쪽에서 그 줄부터 쪽 끝까지를 문장 단위로 다시 담는다.
    쪽 구조는 그대로(2-17: 창 사이로 옮기지 않는다) — 마지막 쪽이 아니면 줄 수 불변, 마지막 쪽은 줄 수가 달라져도 쪽 한도·조각 수 계약 안이면 받는다.
    나쁜 끊김이 느는 이동은 거부한다(결정적)."""
    lines = list(lines)
    for _ in range(4):
        n = len(lines)
        bad = one_line_sentences(lines, cols)
        done = False
        for sent in bad:
            a = sent[0][0]
            pe = min(n, (a // PAGE_LINES + 1) * PAGE_LINES)  # 쪽 끝(제외)
            words = [w for ln in lines[a:pe] for w in ln.split(" ")]
            new_region = _pack_sentences(words, cols)
            new = lines[:a] + new_region + lines[pe:]
            if len(new) != n:
                if pe < n or page_counts(new)[:-1] != page_counts(lines)[:-1] or not _pieces_fit(len(new), nseg):
                    continue
            if new == lines or not all(_fit(x, cols) for x in new):
                continue
            if len(one_line_sentences(new, cols)) >= len(bad) or regressions(lines, new) or _score(new) > _score(lines):
                continue
            if lonely_last(new) and not lonely_last(lines):
                continue
            lines, done = new, True
            break
        if not done:
            break
    return lines


def _rules(lines, cols, nseg=0):
    """2-16 후처리 — 같은 줄 수로 ② 절째 내리기 ③ 쪽 끝 한 어절 고아 · 보조용언 자리 쪽 끊기. 값이 나빠지면 안 한다(결정적)."""
    lines = list(lines)
    n = len(lines)
    if n < 2:
        return lines
    for _ in range(3):  # 한 번 고치면 다음 줄이 새로 걸릴 수 있다
        changed = False
        fixed = _sentence_lines(lines, cols, nseg)  # 2-10 — 먼저 문장을 새 줄에서 시작시키고, 아래 규칙들이 그걸 되돌리지 않게(regressions ②)
        if fixed != lines:
            lines, changed = fixed, True
        for k in range(n - 1):
            w = lines[k].split(" ")
            if len(w) < 2 or _is_bound(w[-1], w[-2]):
                continue
            bs = [j for j in range(len(w) - 1) if _is_bound(w[j], w[j - 1] if j else "")]
            if not bs:
                continue
            j = bs[-1]
            head, tail = " ".join(w[: j + 1]), w[j + 1 :]
            nxt = lines[k + 1].split(" ")
            e = next((t for t, x in enumerate(nxt) if _is_bound(x, nxt[t - 1] if t else "")), None)
            if e is None or len(head.replace(" ", "")) < MIN_HEAD:
                continue
            if not _fit(" ".join(tail + nxt[: e + 1]), cols):
                continue
            new = lines[:k] + [head] + [" ".join(tail + nxt)] + lines[k + 2 :]
            if not _fit(new[k + 1], cols):
                # 다음 줄이 넘치면 뒤를 다시 나눈다 — 줄이 하나 느는 건 쪽 수가 안 늘고 조각 수 안일 때만
                rest = " ".join(tail + [x for ln in lines[k + 1 :] for x in ln.split(" ")])
                suf = rows(rest, cols=cols)
                new = lines[:k] + [head] + suf
                if len(new) > n and not _pieces_fit(len(new), nseg):  # 조각 수(창 수 계약)가 한도 — 쪽(▼)은 엔진이 알아서 넘기므로 느어도 된다
                    continue
                if len(new) < n:
                    continue
            if _cost_of(new) > _cost_of(lines) + (COST_SHORT if len(new) > n else 0):
                continue
            if regressions(lines, new) or (len(new) > n and _score(new) >= _score(lines)):
                continue
            lines, changed, n = new, True, len(new)
        # (e) 줄 끝 [명사+명사] 굳은 구 — 앞 어절을 다음 줄로 내려 구를 한 줄에 둔다(줄 수 안 늘 때만)
        for k in range(n - 1):
            w = lines[k].split(" ")
            if len(w) < 2 or not is_nounphrase_split(lines[k], lines[k + 1]):
                continue
            head = " ".join(w[:-1])
            if len(head.replace(" ", "")) < MIN_HEAD:
                continue
            moved = w[-1] + " " + lines[k + 1]
            if _fit(moved, cols):
                new = lines[:k] + [head, moved] + lines[k + 2 :]
            else:
                suf = rows(" ".join([w[-1]] + [x for ln in lines[k + 1 :] for x in ln.split(" ")]), cols=cols)
                new = lines[:k] + [head] + suf
                if len(new) < n or (len(new) > n and not _pieces_fit(len(new), nseg)):
                    continue
            if _cost_of(new) > _cost_of(lines) + COST_PLAIN + (COST_SHORT if len(new) > n else 0):
                continue
            if regressions(lines, new) or (len(new) > n and _score(new) >= _score(lines)):
                continue
            lines, changed, n = new, True, len(new)
        # 쪽 끝 한 어절 고아(쪽 안 줄이 둘 이상이고 마지막 줄이 한 어절) — 앞 줄 끝 낱말을 내려 둘로 만든다
        for i in range(1, n):
            page_end = i == n - 1 or i % PAGE_LINES == PAGE_LINES - 1
            if not page_end or i % PAGE_LINES == 0 or " " in lines[i]:
                continue
            pw = lines[i - 1].split(" ")
            for take in (1, 2):  # 앞 줄 끝 낱말 하나 — 그게 새 나쁜 끊김이면 둘
                if len(pw) <= take:
                    break
                new = list(lines)
                new[i - 1], new[i] = " ".join(pw[:-take]), " ".join(pw[-take:]) + " " + lines[i]
                if len(new[i - 1].replace(" ", "")) < MIN_HEAD or not _fit(new[i], cols) or _cost_of(new) > _cost_of(lines) + COST_PLAIN:
                    continue
                if regressions(lines, new):
                    continue
                lines, changed = new, True
                break
        # 본용언+보조용언 자리에서 쪽을 끊지 않는다 — 쪽 끝 낱말을 다음 쪽 머리로
        for i in range(PAGE_LINES - 1, n - 1, PAGE_LINES):
            w, nx = lines[i].split(" "), lines[i + 1].split(" ")
            if len(w) < 2 or not _AUX_PREV_RE.search(w[-1]) or not _AUX_RE.match(nx[0]):
                continue
            new = list(lines)
            new[i], new[i + 1] = " ".join(w[:-1]), w[-1] + " " + lines[i + 1]
            if len(new[i].replace(" ", "")) < MIN_HEAD or not _fit(new[i + 1], cols) or _cost_of(new) > _cost_of(lines) + COST_PLAIN:
                continue
            if regressions(lines, new):
                continue
            lines, changed = new, True
        if not changed:
            break
    return lines


def rows(text, *, cols=COLS, paged=False, nseg=0):
    """문안 → 줄 목록(어절 단위, 줄 폭 ≤ `cols` 칸). krwrap 의 어절 단위·금칙·고아 처리를 쓴다.

    🔴 krwrap 은 줄 끝에 매다는 부호(`…` `.` 등)를 폭에서 덜 쳐 **한두 칸 넘는 줄**을 낼 때가 있다(실측: 「…………어라.」 가 26글리프) —
    엔진은 칸 수로 24칸째에서 접으므로 그대로 두면 어절 한복판이 접힌다. 그래서 넘는 줄이 나오면 폭을 한 칸씩 줄여 다시 나눈다.
    그래도 넘으면(어절 하나가 24칸보다 길다) 운다.
    """
    last = None
    for w in range(int(cols), int(cols) - 5, -1):
        out = krwrap.wrap(text, width=float(w), cell_width=lambda _c: 1.0, strip_after=STRIP_AFTER)
        bad = [r for r in out if len(r) > cols or px_width(r) > cols * CELL_PX]
        if not bad:
            out = _refine(text, out, cols)
            return _rules(out, cols, nseg) if paged and RULES_216 else out
        last = bad[0]
    # krwrap 이 금칙(줄머리 `…` 등)에 막혀 한 줄로 두면 공백에서 그냥 자른다(금칙은 포기 — 어절은 지킨다)
    out, cur = [], ""
    for word in text.split(" "):
        cand = word if not cur else cur + " " + word
        if len(cand) <= cols:
            cur = cand
        else:
            out.append(cur)
            cur = word
    out.append(cur)
    if all(len(r) <= cols and px_width(r) <= cols * CELL_PX for r in out):
        return out
    raise TypesetError(
        f"줄이 {cols}글리프·{cols * CELL_PX}px 를 넘는다({len(last)}·{px_width(last)}): {last!r}"
    )


def pad_rows(rws, *, cols=COLS):
    """줄 목록 → **한 조각에 구울 꼴** — 줄마다 공백으로 `cols` 칸까지 채워 잇는다(마지막 줄은 안 채운다). 개행은 안 쓴다.

    엔진이 칸 수로 접으므로 우리 줄 경계와 일치한다. 조각 안 `0x01` 은 줄바꿈이 아니라 `、` 다.
    """
    out = []
    for i, r in enumerate(rws):
        if len(r) > cols:
            raise TypesetError(f"줄이 {cols}글리프를 넘는다: {r!r}")
        out.append(r if i == len(rws) - 1 else r + SPACE * (cols - len(r)))
    return "".join(out)


def rigid_segments(texts, *, cols=COLS):
    """`rigid` 토막 — 조각마다 제 줄을 지킨다(합쳐 다시 나누지 않는다). 앞뒤 공백은 그대로(이름·숫자가 바로 이어 붙는다). 한 조각이 한 줄을 넘으면 운다."""
    out = []
    for t in texts:
        body = t.strip()
        if body:
            rws = rows(body, cols=cols)
            if len(rws) > 1:
                raise TypesetError(
                    f"끼움 연산이 낀 토막인데 조각 하나가 한 줄({cols}칸)을 넘는다: {t!r}"
                )
        out.append(t)
    return out


def _sim_rows(rows_per_seg, page_lines=PAGE_LINES):
    """조각마다 줄 수 → 줄이 사라지는 조각 색인(없으면 None). 엔진은 `01` 로 이어진 줄이 `page_lines` 에 차면 알아서 쪽을 넘기지만(▼),
    한 조각 안에서 접힌 줄이 쪽 한도를 넘으면 그 줄은 조용히 사라진다(`over_limit_pages` 와 같은 셈)."""
    row = 0
    for k, r in enumerate(rows_per_seg):
        if r == 0:
            continue
        if row >= page_lines:
            row = 0
        if row + r > page_lines:
            return k
        row += r
    return None


def page_segments(texts, nseg, *, cols=COLS, page_lines=PAGE_LINES, rules=True):
    """한 **쪽**(스크립트에서 `01` 로 이어진 조각 `nseg` 개)의 번역 문장들 → 같은 개수의 조각 문자열.

    문장들을 이어 어절 단위로 다시 나눈 **줄을 조각에 하나씩** 놓는다(줄 `k` → 조각 `k`, 조각 사이는 원본의 `01` 줄바꿈이 그대로 맡는다 — 패딩이 필요 없다).
    줄이 조각보다 많으면 남는 줄을 **마지막 조각에 줄 패딩으로 이어 붙인다**(`pad_rows`) · 줄이 적으면 뒤 조각은 빈 조각(빈 꼬리는 화면에 아무것도 안 그린다 — 실측).
    🔴 **줄 수의 한도는 쪽(3줄)이 아니라 조각 수다** — 조각마다 한 줄이면 3줄이 차는 대로 엔진이 쪽을 알아서 넘긴다(원본에도 `01` 로 4~5조각이 이어진 쪽이 84개).
    한 조각 안에서 접힌 줄이 쪽 한도(3줄)를 넘으면 그 줄은 **조용히 사라진다** — `_sim_rows` 가 센다. 넘으면 운다.
    🔴 바이트도 중요하다 — 예전엔 전부 첫 조각에 24칸 패딩으로 몰아 원본보다 길어졌다.
    🔴 쪽 수는 스크립트가 정한다(`02`) — 조각을 늘려 쪽을 더할 수 없다. 문안은 원래 쪽 구조에 맞춘다.
    """
    text = " ".join(t.strip() for t in texts if t and t.strip())
    if not text:
        return [""] * nseg
    rws = rows(text, cols=cols, paged=rules, nseg=nseg)
    if rules and RULES_216 and (b := balance(text, rws, nseg, cols=cols)):
        rws = b
    if len(rws) <= nseg:
        out = rws + [""] * (nseg - len(rws))
    else:
        out = [*rws[: nseg - 1], pad_rows(rws[nseg - 1 :], cols=cols)]
    bad = _sim_rows([rows_of(len(x), cols) for x in out], page_lines)
    if bad is not None:
        raise TypesetError(
            f"{len(rws)}줄을 {nseg}조각에 놓으면 조각 {bad} 의 줄이 쪽 한도 {page_lines}줄을 넘어 사라진다: {text!r}"
        )
    return out


def sm_text_base(mem):
    return _sm.text_base(mem)


def sm_table_len(mem):
    return _sm.table_len(mem)


def message_streams(mem):
    """[{p0, kind, prints:[(자리, 색인)], end}] — 표 규격 멤버의 메시지 스트림(공용 `gmf_script.message_streams` — 해석기 `0x8003c98c` 가 읽는 그대로 걷는다)."""
    from shared.ps1 import gmf_script as sm

    return sm.message_streams(mem)


def message_sites(mem):
    """[{q, v, flow, kind, p0}] — 출력 자리 전부(스트림을 편 것). `flow` = 출력 바로 뒤 바이트(`00` 끝 · `01` 줄 · `02` 쪽 · 그 밖은 다른 연산)."""
    return [
        {"q": q, "v": v, "flow": mem[q + 2], "kind": st["kind"], "p0": st["p0"]}
        for st in message_streams(mem)
        for q, v in st["prints"]
    ]


def _gap_ops(mem, prev_q, q):
    """앞 출력(`prev_q`)과 다음 출력(`q`) 사이의 연산 바이트들."""
    op = q - 1 if mem[q - 1] == 0x0F else q - 2
    return mem[prev_q + 2 : op]


# 해석기 핸들러(`0x800103d0`)로 가른 연산 — 줄·쪽 흐름(`01` 줄 · `02` 쪽 · `03`·`04` 창 비우기/닫기 — 쪽 넘김 뒤에 붙는다) · 아무것도 안 그리는 것(`09`·`0A`·`0B`·`0C`~`0E`)
# 이 둘을 뺀 나머지(`05`·`06`·`08` 이름 삽입 · `07` 수 그리기 · `10` 이상 색)가 줄 한복판에 끼는 연산이다.
FLOW_OPS = {1, 2, 3, 4}
NEUTRAL_OPS = {9, 10, 11, 12, 13, 14}


class Run(list):
    """쪽(또는 쪽의 한 토막)의 조각 색인들. `rigid` = 줄 한복판에 끼는 연산(이름·숫자 삽입, 색 …)이 앞뒤에 있어 **조각을 합쳐 다시 나눌 수 없는** 토막."""

    rigid = False


def windows(mem):
    """[[Run(조각 색인…)(쪽·토막)…](메시지)…] — 표 규격 멤버의 대사 흐름. 메시지 = 스트림 하나.

    출력 사이 연산으로 가른다: `01` 만 있으면 **같은 쪽 다음 줄** · `01`·`02` 만 있고 `02` 가 있으면 **쪽 넘김** · 그 밖 연산(`05`·`06`·`08` 이름 삽입, 색, 대기 …)이
    끼면 **토막을 가른다** — 그 연산이 그리는 글자가 앞뒤 조각 사이에 들어가므로 앞뒤 조각을 한 문단으로 합쳐 옮기면 **삽입 자리가 어긋난다**(조각을 합치면 뒷 조각이 비고 연산은 그 자리에 남는다).
    그런 토막은 `rigid` — 조각마다 제 줄을 지킨다(`page_segments` 가 안 합친다).
    """
    out = []
    # 🔴 선택지 창(`3B` 연산)의 문자열은 **하나씩 제 줄**이다 — 합쳐 다시 나누면 첫 선택지에 셋이 몰리고 나머지는 빈다(마스터 10-25 「흑마법」만 보임)
    choices = {i for _p, _c, _r, idxs in choice.scan(mem, sm_text_base(mem), sm_table_len(mem)) for i in idxs}
    for st in message_streams(mem):
        msg, page = [], Run()
        prev = None
        for q, v in st["prints"]:
            if v in choices:
                if page:
                    msg.append(page)
                one = Run([v])
                one.rigid = True
                msg.append(one)
                page = Run()
                prev = q
                continue
            if prev is not None:
                ops = set(_gap_ops(mem, prev, q))
                if (
                    not ops or ops - FLOW_OPS - NEUTRAL_OPS
                ):  # 연산이 아예 없으면 두 출력이 같은 줄에 이어 붙는다  # 줄 한복판에 끼는 연산 — 앞뒤 토막 모두 rigid
                    page.rigid = True
                    msg.append(page)
                    page = Run()
                    page.rigid = True
                    if 2 in ops:  # 쪽 넘김이 같이 있어도 가름은 같다
                        pass
                elif 2 in ops or ops & {3, 4}:
                    msg.append(page)
                    page = Run()
            page.append(v)
            prev = q
        if page:
            msg.append(page)
        out.append(msg)
    # 🔴 같은 조각을 여러 곳(다른 쪽·메시지)에서 쓰면 합쳐 옮길 수 없다 — 한 곳에서 문안을 뒷 조각에 비우면 다른 곳이 빈다. 그런 조각이 든 토막은 rigid.
    use = {}
    for msg in out:
        for pg in msg:
            for i in set(pg):
                use[i] = use.get(i, 0) + 1
    for msg in out:
        for pg in msg:
            if any(use[i] > 1 for i in pg):
                pg.rigid = True
    return out


def rows_of(n_codes, cols=COLS):
    """조각 하나가 차지하는 줄 수 — 엔진이 24칸째에서 접는다. 빈 조각은 0줄(같은 쪽의 빈 꼬리는 아무것도 안 그린다 — 실측)."""
    return -(-n_codes // cols) if n_codes else 0


def engine_page_groups(seg_lens, *, cols=COLS, page_lines=PAGE_LINES):
    """[[조각 순번…]…] — `01` 로 이어진 조각을 엔진이 3줄마다 넘기는 **창(쪽)** 으로 가른다(`seg_lens` = 조각 순서대로 코드 수, 빈 조각은 줄 0).

    번역 규칙 2-17 — 원문 창의 내용을 창 사이로 옮기지 않는다. 원문이 4줄로 이어 쓴 대사는 엔진이 셋째 줄 뒤에서 창을 넘겨 **넷째 줄이 둘째 창**에 앉는데, 한국어가 짧아 석 줄에 끝나면 둘째 창이 사라진다.
    """
    groups, row, cur = [], 0, []
    last = max((k for k, n in enumerate(seg_lens) if n), default=-1)
    for k, n in enumerate(seg_lens):
        r = rows_of(n, cols)
        if k > last:  # 빈 꼬리는 아무것도 안 그린다(실측)
            cur.append(k)
            continue
        r = max(1, r)  # 꼬리 앞의 빈 조각은 **빈 줄**이다 — 줄바꿈(`01`)만 그린다
        if row >= page_lines or row + r > page_lines:
            if cur:
                groups.append(cur)
            cur, row = [], 0
        cur.append(k)
        row += r
    if cur:
        groups.append(cur)
    return groups


def over_limit_pages(mem, seg_lens, *, cols=COLS, page_lines=PAGE_LINES):
    """[(쪽의 조각 색인, 걸린 조각)] — **줄이 사라질 수 있는 쪽**. `seg_lens` = 조각 색인 → 코드 수(편집 반영본).

    🔴 실측(시험 빌드): **한 조각 안에서 24칸마다 접힌 줄이 쪽 한도(3줄)를 넘으면 그 줄은 화면에서 조용히 사라진다.** 반면 `01` 로 이어진 **조각 줄**은 3줄이 차면
    엔진이 알아서 `▼` 와 함께 쪽을 넘긴다(조각마다 1줄인 4줄 시험 — 4줄째가 다음 쪽에 나왔다). 그래서 쪽을 시뮬레이션한다:
      줄 위치 `row` 를 0 에서 시작해 조각마다 줄 수 `r` 를 더하되, `row == 3` 에서 새 조각이 시작하면 쪽이 넘어가 `row=0`;
      `row + r > 3` 이면 그 조각의 일부 줄이 사라진다 → 실패.
    ⚠ `row` 가 1~2 인데 `r` 이 커서 걸치는 경우는 어느 줄이 사라지는지 확정 안 됐다 — 보수적으로 실패로 친다.
    원본에도 `01` 로 4~5조각이 이어진 쪽이 84개 있다(자동 쪽 넘김 — 이 규칙으로는 통과).
    """
    bad = []
    for msg in windows(mem):
        for pg in msg:
            row = 0
            for i in pg:
                r = rows_of(seg_lens.get(i, 0), cols)
                if r == 0:
                    continue
                if row >= page_lines:
                    row = 0
                if row + r > page_lines:
                    bad.append((pg, i))
                    break
                row += r
    return bad
