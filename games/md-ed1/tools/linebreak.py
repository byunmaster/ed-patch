"""md-ed1 줄·쪽 나눔 규칙 2-16(전 기종 공통 규칙, 마스터 10-26) — 조판 결과를 다듬는 후처리 + 지표.

공용 `shared/text/krwrap` 은 손대지 않는다. `build.typeset()` 이 krwrap 으로 쪽을 짠 **뒤에** 이 모듈이
쪽(줄 목록) 단위로 두 가지를 고친다.

 ② 절째 내림 — 줄이 넘쳐 한 절이 줄 끝에서 시작해 다음 줄로 걸쳤는데, 그 절이 통째로 다음 줄에 들어가면
    경계(문장 끝 > 쉼표 > 연결어미)까지 내려 그 쪽의 나머지를 다시 감는다. 줄이 늘어나면 안 한다.
 ③ 쪽 끝 고아 — 쪽 끝 줄이 한 어절이거나(고아), 쪽이 한 낱말짜리 문장 토막으로 끝나면(문장 중간)
    끝 어절을 다음 쪽 머리로 보낸다. 본용언+보조용언 같은 한 덩어리(`krwrap.splits_unit`)는 안 가른다.

지표(`metrics`)는 같은 술어로 대사 전량을 조판 결과에서 센다 — 고친 뒤에도 0 이 아니면 못 고친 자리다.
(c) 문장 중간 손 개행은 조판 전 원고 기준(`\\n` 이나 글 조각 사이 `<01>`)이라 조판기 규칙이 아니라 원고 규칙이다.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from text import krwrap

# 경계 어미(절을 닫는 연결어미) — 본용언+보조용언은 `splits_unit` 으로 따로 거른다
CONNECTIVE = (
    "고", "서", "며", "면", "니", "나", "지만", "는데", "은데", "인데", "으나", "으며", "다가",
    "도록", "려고", "더니", "자", "으니", "니까", "라서", "어서", "아서", "해서", "던데",
)  # fmt: skip
HEAD_CONJ = {
    "그리고",
    "그러나",
    "하지만",
    "그래서",
    "그런데",
    "그러면",
    "그러니",
    "그렇지만",
    "또한",
    "그리하여",
}
MIN_KEEP = 7.0  # 절을 내리고 앞 줄에 남는 글이 이보다 짧으면 안 한다(칸)


def _tail_strip(w: str) -> str:
    return w.rstrip("」』)\"'")


def sentence_end(w: str) -> bool:
    return krwrap.is_sentence_end(w)


def boundary_strength(w: str) -> int:
    """어절 `w` 뒤가 절 경계인가 — 3 문장 끝 · 2 쉼표 · 1 연결어미 · 0 아님."""
    if sentence_end(w):
        return 3
    s = _tail_strip(w)
    if s.endswith(","):
        return 2 if len(s.rstrip(",")) > 2 else 0  # 「오,」 같은 두 음절 이하 쉼표는 경계 아님
    base = s
    if base in HEAD_CONJ or len(base) < 3:
        return 0
    if base.endswith(("라고", "다고", "자고", "냐고", "는다고")):  # 인용 「~라고 해서」는 한 덩어리
        return 0
    return 1 if base.endswith(CONNECTIVE) else 0


KAGI = "「」『』"  # 반각 코드(리소스 1)로 나가는 낫표 — 진행 6px = 0.5칸 (hangul.KAGI_HALF)


def cell_width(ch: str) -> float:
    """이 게임의 칸 폭 — krwrap 기본값(공백만 0.5)에 반각 「」 를 더한다. 공용 기본값은 건드리지 않는다."""
    return 0.5 if ch in KAGI else krwrap.default_cell_width(ch)


def _width(s: str) -> float:
    return krwrap.text_width(s, cell_width)


def _words(line: str) -> list[str]:
    return line.split(" ")


def _clause_tail(line: str) -> tuple[str, str] | None:
    """줄 끝에서 시작해 다음 줄로 걸친 절의 (앞에 남을 글, 내릴 글). 경계가 없으면 None."""
    ws = _words(line)
    if len(ws) < 2:
        return None
    for i in range(len(ws) - 2, -1, -1):  # 마지막 어절은 경계여도 소용없다(이미 줄 끝)
        if boundary_strength(ws[i]) and not krwrap.splits_unit(ws[i], ws[i + 1]):
            keep, move = " ".join(ws[: i + 1]), " ".join(ws[i + 1 :])
            return keep, move
    return None


def _breaks(page: list[str]) -> tuple[list[str], set[int]]:
    flat: list[str] = []
    cuts: set[int] = set()
    for ln in page:
        flat += _words(ln)
        cuts.add(len(flat))
    cuts.discard(len(flat))
    return flat, cuts


def regress(old: list[str], new: list[str]) -> list[tuple[str, str]]:
    """f 퇴행 — `new` 에서 **새로 생긴** 줄 끊김 가운데 한 덩어리를 가르는 것(`krwrap.split_reason`)이나,
    `old` 에서 한 줄이던 문장을 가른 것. 같은 말(어절 열)이어야 비교한다."""
    fo, co = _breaks(old)
    fn, cn = _breaks(new)
    if fo != fn:
        return []
    bad = [
        (fo[i - 1], fo[i]) for i in sorted(co - cn) if boundary_strength(fo[i - 1])
    ]  # 절 경계 끊김이 사라졌다
    for i in sorted(cn - co):
        if krwrap.split_reason(fn[i - 1], fn[i]):
            bad.append((fn[i - 1], fn[i]))
            continue
        a = i
        while a > 0 and not sentence_end(fn[a - 1]):
            a -= 1
        b = i
        while b < len(fn) - 1 and not sentence_end(fn[b]):
            b += 1
        if not any(a < c <= b for c in co):  # 이 문장은 전에 한 줄이었다
            bad.append((fn[i - 1], fn[i]))
    return bad


def improve_clause(page: list[str]) -> list[str]:
    """② 쪽 안에서 줄 끝에 걸친 절을 다음 줄로 통째로 내려 본다. 줄 수가 늘면 원래대로."""
    n = len(page)
    for i in range(n - 1):
        a = page[i]
        if sentence_end(a) or not page[i + 1]:
            continue
        ct = _clause_tail(a)
        if ct is None:
            continue
        keep, move = ct
        if _width(keep) < MIN_KEEP:
            continue
        # 내릴 글이 다음 줄 쪽 같은 절과 통째로 한 줄에 들어갈 때만(경계 어절까지)
        nxt = _words(page[i + 1])
        clause_end = len(nxt)
        for j, w in enumerate(nxt):
            if boundary_strength(w):
                clause_end = j + 1
                break
        if _width(move + " " + " ".join(nxt[:clause_end])) > krwrap_width():
            continue
        rest = move + " " + " ".join(page[i + 1 :])
        new_tail = krwrap.wrap(rest, krwrap_width(), cell_width=cell_width)
        cand = page[:i] + [keep] + new_tail
        if len(cand) > n or any(_width(x) > krwrap_width() for x in cand):
            continue
        if len(cand) == n and cand[i + 1 :] == page[i + 1 :]:
            continue
        if regress(page, cand):
            continue
        return improve_clause(cand) if cand != page else cand
    return page


# [명사+명사] 굳은 구를 줄 끝·첫머리에서 가르지 않는다(2-16 ④) — 형태소 분석기 없이, 앞 어절이 조사·어미·관형형·부사가
# 아닌 꼴이면 명사로 본다(오탐은 줄 수가 안 늘 때만 묶으니 해가 작다).
_NOT_NOUN_END = set(
    "은는이가을를의에도로와과만서고며면니다요죠까나네데지자게어아해라러든께야군걸들"
)
_NOT_NOUN = {
    "가장", "특히", "모두", "한층", "우선", "역시", "대체", "여태", "지금", "이제", "계속", "완전히", "원래",
    "여기", "그리", "또다시", "냉큼", "모조리", "빨리", "우리", "너희들", "여러분", "정말", "아주", "매우",
    "너무", "다시", "아직", "벌써", "이미", "결코", "반드시", "제발", "어서", "함께", "같이", "그냥",
}  # fmt: skip


def _adnominal(w: str) -> bool:
    c = w[-1]
    if c in "던는":
        return True
    o = ord(c) - 0xAC00
    return 0 <= o < 11172 and o % 28 in (4, 8)  # 받침 ㄴ·ㄹ(관형형 -ㄴ/-ㄹ)


def noun_noun(wa: str, wb: str) -> bool:
    if not wa or not wb or wa in _NOT_NOUN or _tail_strip(wa) != wa:
        return False
    if wa[-1] in _NOT_NOUN_END or wa[-1] in ".,!?…」" or _adnominal(wa):
        return False
    return not (
        wb[-1] in "다요죠까" or wb[0] in "그이저"
    )  # 서술어·지시어로 시작하는 뒤는 구가 아니다


_JOSA = "은는이가을를의에도로와과만"
_PHRASES: set | None = None


def _stem(w: str) -> str:
    return w.rstrip(_JOSA + ".,!?…」") or w


def phrases() -> set:
    """대사 전량에서 같은 [앞 어절, 뒤 어절 줄기] 이음이 두 번 이상 나온 명사 구(반복이 구라는 증거)."""
    global _PHRASES
    if _PHRASES is None:
        import collections
        import itertools

        import textmap

        cnt: collections.Counter = collections.Counter()
        for doc in textmap.load_all().values():
            for ent in doc.get("streams", {}).values():
                o = ent.get("ours")
                if not o or ent.get("raw"):
                    continue
                for kind, v in textmap.parse_ours(o):
                    if kind != "text":
                        continue
                    ws = v.replace("\n", " ").split()
                    for x, y in itertools.pairwise(ws):
                        if noun_noun(x, y):
                            cnt[(x, _stem(y))] += 1
        _PHRASES = {k for k, n in cnt.items() if n >= 2}
    return _PHRASES


def improve_nounphrase(page: list[str]) -> list[str]:
    """④ 줄 끝 [명사+명사] 구의 앞 어절을 다음 줄로 내려 구를 한 줄에 둔다. 줄이 늘면 안 한다."""
    n = len(page)
    for i in range(n - 1):
        wa = _words(page[i])[-1]
        wb = _words(page[i + 1])[0]
        if len(_words(page[i])) < 2 or not noun_noun(wa, wb) or (wa, _stem(wb)) not in phrases():
            continue
        keep = " ".join(_words(page[i])[:-1])
        if _width(keep) < MIN_KEEP:
            continue
        cand = page[:i] + [keep] + krwrap.wrap(wa + " " + " ".join(page[i + 1 :]), krwrap_width(), cell_width=cell_width)
        if len(cand) > n or any(_width(x) > krwrap_width() for x in cand):
            continue
        if cand != page and not regress(page, cand):
            return improve_nounphrase(cand)
    return page


_W = [17.5]


def krwrap_width() -> float:
    return _W[0]


def set_width(w: float) -> None:
    _W[0] = w


def _last_fragment(page: list[str]) -> list[str]:
    """쪽 끝에서, 마지막 문장 끝 뒤에 남은 어절들(= 문장이 쪽을 넘어 이어질 토막)."""
    ws = [w for ln in page for w in _words(ln)]
    k = len(ws)
    while k > 0 and not sentence_end(ws[k - 1]):
        k -= 1
    # 이 쪽이 문장 끝으로 끝났으면 토막 없음
    if sentence_end(ws[-1]):
        return []
    return ws[k:]


def page_end_issues(page: list[str]) -> tuple[bool, bool]:
    """(a 쪽 끝 한 어절 고아, b 문장 중간 한 낱말 토막으로 끝남) — 한 쪽에 대해."""
    if len(page) < 2:
        return False, False
    last = _words(page[-1])
    a = len(last) == 1 and not sentence_end(
        last[0]
    )  # 문장 끝으로 끝난 한 어절은 문장이 쪽 안에 있으니 고아가 아니다
    frag = _last_fragment(page)
    b = (not a) and len(frag) == 1 and len(frag[0]) > 0
    return a, b


def fix_page_end(p: list[str], q: list[str]) -> bool:
    """③ 쪽 `p` 끝 고아를 다음 쪽 `q` 머리로 보낸다(한 어절, 안 되면 두 어절). 고쳤으면 True."""
    if not any(page_end_issues(p)):
        return False
    flat = [w for ln in p for w in _words(ln)]
    for k in (1, 2):
        if k >= len(flat) or krwrap.splits_unit(flat[-k - 1], flat[-k]):
            continue
        moved_head = " ".join(flat[-k:]) + " " + q[0]
        if _width(moved_head) > krwrap_width():
            continue
        # 마지막 줄(모자라면 앞 줄)에서 k 어절을 뺀다
        lines = [_words(ln) for ln in p]
        rem = k
        while rem and lines:
            if len(lines[-1]) <= rem:
                rem -= len(lines.pop())
            else:
                lines[-1] = lines[-1][:-rem]
                rem = 0
        new_p = [" ".join(w) for w in lines]
        if not new_p or any(page_end_issues(new_p)):
            continue
        p[:] = new_p
        q[0] = moved_head
        return True
    return False


def _subj_obj_adn(w: str) -> bool:
    """주어·목적어·관형어 꼴 어절(뒤에서 쪽을 끊으면 꾸밈받는 말이 다음 쪽으로 넘어간다)."""
    t = _tail_strip(w).rstrip(",")
    return bool(t) and (t[-1] in "을를은는이가의" or _adnominal(t))


def _cut_score(lines: list[str], at: int) -> int:
    """줄 `at` 앞에서 쪽을 자를 때의 점수 — 낮을수록 좋다. 0 문장 끝 · 1 쉼표 · 2 연결어미 · 3 부사어·서술어 뒤(주어·목적어·관형어 아님) ·
    4 주어·목적어·관형어 뒤 · 99 한 덩어리를 가름."""
    pw, nw = _words(lines[at - 1])[-1], _words(lines[at])[0]
    if krwrap.splits_unit(pw, nw):
        return 99
    st = boundary_strength(pw)
    if not st:  # 쪽 경계는 「않고」·「하여」 같은 두 음절 연결어미도 절 경계로 친다(줄 안 경계 판정보다 느슨)
        t = _tail_strip(pw)
        if len(t) == 2 and t.endswith(CONNECTIVE) and t not in HEAD_CONJ:
            st = 1
    if st:
        return {3: 0, 2: 1, 1: 2}[st]
    return 4 if _subj_obj_adn(pw) else 3


def balance_pages(pages: list[list[str]]) -> list[list[str]]:
    """h·h2 — 창이 둘 이상인 덩이에서 줄 수 차가 2 이상이면, 줄은 그대로 두고 쪽 경계만 옮겨 고르게 나눈다
    (창 수·줄 수·글 불변). 경계는 문장 끝 > 쉼표 > 연결어미 > 그 밖 순으로 고르고, 한 덩어리를 가르는 자리는 안 쓴다."""
    n = len(pages)
    sizes = [len(p) for p in pages]
    if n < 2 or max(sizes) - min(sizes) < 2:
        return pages
    lines = [ln for p in pages for ln in p]
    total = len(lines)
    base, extra = divmod(total, n)
    if base < 1 or base + (1 if extra else 0) > 3:
        return pages
    import itertools

    old_cuts = list(itertools.accumulate(sizes))[:-1]
    old_score = [_cut_score(lines, c) for c in old_cuts]
    best = None
    for big in itertools.combinations(range(n), extra):
        sz = [base + (1 if i in big else 0) for i in range(n)]
        cuts = list(itertools.accumulate(sz))[:-1]
        score = [_cut_score(lines, c) for c in cuts]
        if (
            max(score) >= 3
        ):  # 문장 끝·쉼표·연결어미 경계만(관형어·목적어·주어 뒤에서 쪽을 끊지 않는다)
            continue
        if any(o_sc == 0 and n_sc != 0 for o_sc, n_sc in zip(old_score, score, strict=True)):
            continue  # 전에 문장 끝이던 쪽 경계를 문장 중간으로 옮기는 이동은 거부
        trial, i = [], 0
        for z in sz:
            trial.append(lines[i : i + z])
            i += z
        if any(any(page_end_issues(p)) for p in trial[:-1]):  # 쪽 끝 고아를 새로 만들면 안 된다
            continue
        key = (sum(score), sum(abs(a - b) for a, b in zip(cuts, old_cuts, strict=True)))
        if best is None or key < best[0]:
            best = (key, sz)
    if best is None:
        return pages
    out, i = [], 0
    for z in best[1]:
        out.append(lines[i : i + z])
        i += z
    return out


LINES_PER_PAGE = 3


def bad_cuts(pages: list[list[str]]) -> int:
    """g — 쪽 경계 중 문장 끝·쉼표·연결어미 뒤가 아닌 것(관형어·목적어·주어 뒤 등) 수."""
    lines = [ln for p in pages for ln in p]
    n = 0
    i = 0
    for p in pages[:-1]:
        i += len(p)
        if _cut_score(lines, i) >= 4:
            n += 1
    return n


def fix_cuts(pages: list[list[str]]) -> list[list[str]]:
    """g 고치기 — 줄은 그대로 두고 쪽 경계만 다시 고른다(쪽당 3줄 이하, 쪽 수는 늘어도 된다).
    비용: 나쁜 경계·새 쪽 끝 고아·한 어절 마지막 쪽 100 · 경계 세기(문장 끝 0 < 쉼표 1 < 연결어미 2) · 쪽 하나 3 · 옛 경계에서 벗어남 1."""
    if len(pages) < 2 or bad_cuts(pages) == 0:
        return pages
    lines = [ln for p in pages for ln in p]
    n = len(lines)
    old = set()
    acc = 0
    for p in pages[:-1]:
        acc += len(p)
        old.add(acc)
    INF = float("inf")
    best = [(INF, -1)] * (n + 1)
    best[0] = (0, -1)
    for i in range(1, n + 1):
        for j in range(max(0, i - LINES_PER_PAGE), i):
            if best[j][0] == INF:
                continue
            page = lines[j:i]
            c = best[j][0] + 3
            if i < n:
                sc = _cut_score(lines, i)
                c += {0: 0, 1: 1, 2: 2, 3: 4}.get(sc, 100)
                if any(page_end_issues(page)):
                    c += 100
                if i not in old:
                    c += 1
                if len(page) == 1 and _width(page[0]) < 9:
                    c += 20  # 짧은 한 줄짜리 창은 피한다
            elif len(page) == 1 and len(_words(page[0])) == 1 and j > 0:
                c += 100
            if c < best[i][0]:
                best[i] = (c, j)
    out, i = [], n
    while i > 0:
        j = best[i][1]
        out.append(lines[j:i])
        i = j
    out.reverse()
    return out if bad_cuts(out) < bad_cuts(pages) else pages


def rewrap_cuts(pages: list[list[str]]) -> list[list[str]]:
    """g 의 마지막 수단 — 줄을 다시 감아 쪽 경계를 주어·목적어·관형어 뒤가 아닌 자리에 둔다(쪽 수가 늘어도 된다).
    단어 열은 그대로이고, 줄 끊김은 한 덩어리를 가르지 않는 자리(`splits_unit` · 반복 명사구)만 쓴다."""
    if len(pages) < 2 or bad_cuts(pages) == 0:
        return pages
    words = [w for p in pages for ln in p for w in _words(ln)]
    n = len(words)
    W = krwrap_width()
    ph = phrases()

    def can_break(j: int) -> bool:  # 단어 j-1 뒤에서 줄을 끊어도 되나
        if j >= n:
            return True
        if krwrap.splits_unit(words[j - 1], words[j]):
            return False
        return not (noun_noun(words[j - 1], words[j]) and (words[j - 1], _stem(words[j])) in ph)

    def line_w(i: int, j: int) -> float:
        return _width(" ".join(words[i:j]))

    INF = float("inf")
    # 상태 (지난 단어 수 i, 이 쪽에서 이미 쓴 줄 수 k) → (비용, 이전 상태, 줄 끝 j, 쪽을 닫았나)
    best: dict[tuple[int, int], tuple[float, tuple[int, int] | None, bool]] = {
        (0, 0): (0.0, None, False)
    }
    order = [(0, 0)]
    idx = 0
    while idx < len(order):
        i, k = order[idx]
        idx += 1
        base = best[(i, k)][0]
        for j in range(i + 1, n + 1):
            if line_w(i, j) > W:
                break
            if not can_break(j):
                continue
            last_line = j == n
            cost = base + 5 + (0 if last_line else (W - line_w(i, j)) ** 2 / 8)
            if j - i == 1 and not last_line:
                cost += 20  # 한 어절 줄
            opts = []
            if k + 1 < LINES_PER_PAGE and not last_line:
                opts.append(((j, k + 1), cost, False))
            if last_line:
                opts.append(
                    ((j, 0), cost + 3 + (100 if (k == 0 and j - i == 1 and i > 0) else 0), True)
                )
            else:
                sc = _score_words(words[j - 1], words[j])
                if sc < 99:
                    cc = {0: 0, 1: 1, 2: 2, 3: 4}.get(sc, 100)
                    opts.append(((j, 0), cost + 3 + cc + (100 if j - i == 1 else 0), True))
            for st, c, closed in opts:
                if c < best.get(st, (INF,))[0]:
                    if st not in best:
                        order.append(st)
                    best[st] = (c, (i, k), closed)
                    best[st] = (c, (i, k), closed)
    if (n, 0) not in best:
        return pages
    # 복원
    st = (n, 0)
    cuts_ = []
    while best[st][1] is not None:
        cuts_.append((best[st][1], st, best[st][2]))
        st = best[st][1]
    cuts_.reverse()
    out: list[list[str]] = [[]]
    for (i, _k), (j, _k2), closed in cuts_:
        out[-1].append(" ".join(words[i:j]))
        if closed and j < n:
            out.append([])
    if bad_cuts(out) >= bad_cuts(pages):
        return pages
    flat = [w for p in out for ln in p for w in _words(ln)]
    return out if flat == words and all(_width(x) <= W for p in out for x in p) else pages


def _score_words(pw: str, nw: str) -> int:
    return _cut_score([pw, nw], 1)


def improve_pages(pages: list[list[str]], width: float) -> list[list[str]]:
    """한 덩이(`\\f` 사이) 조판 결과에 ②·③ 을 건다 — 쪽 경계는 krwrap 이 정한 대로, 줄 수는 안 는다."""
    set_width(width)

    def each(ps):
        return [improve_nounphrase(improve_clause(list(pg))) for pg in ps]

    # 줄을 먼저 다듬고 → 나쁜 쪽 경계를 절 경계로 옮기고(g) → 고르게 나누고(h·h2) → 바뀐 쪽 안을 다시 다듬는다
    out = balance_pages(rewrap_cuts(fix_cuts(each(pages))))
    out = each(out)
    for i in range(len(out) - 1):
        fix_page_end(out[i], out[i + 1])
    return each(out)


# ───────── 지표(대사 전량, 조판 결과 기준) ─────────

HAND_BREAK = re.compile(r"\n")


def metrics(typeset_fn, streams, width: float, flattened: bool = False, before_fn=None) -> dict:
    """streams: (구역, 키, ours) 목록. typeset_fn(body) → 쪽 목록. 반환 {a,b,c,d: [(구역,키,글)…]}."""
    import textmap

    set_width(width)
    res = {"a": [], "b": [], "c": [], "d": [], "e": [], "f": [], "h": [], "h2": [], "g": []}
    for blk, key, ours in streams:
        parts = textmap.parse_ours(ours)
        pend: list[str] = []

        def flush(key=key, blk=blk, pend=pend):
            if not pend:
                return
            body = "".join(pend)
            pend.clear()
            if not body.strip():
                return
            pages = typeset_fn(body)
            if before_fn is not None:
                old = before_fn(body)
                if len(old) == len(pages):
                    for po, pn in zip(old, pages, strict=True):
                        if regress(po, pn):
                            res["f"].append((blk, key, " / ".join(po) + " ⇒ " + " / ".join(pn)))
            if len(pages) >= 2:
                if bad_cuts(pages):
                    res["g"].append((blk, key, " ¶ ".join(" / ".join(p) for p in pages)))
                if len(pages[-1]) == 1 and len(_words(pages[-1][0])) == 1:
                    res["h"].append((blk, key, " ¶ ".join(" / ".join(p) for p in pages)))
                if balance_pages(pages) != pages:
                    res["h2"].append((blk, key, " ¶ ".join(" / ".join(p) for p in pages)))
            for pi, pg in enumerate(pages):
                if pi < len(pages) - 1:
                    a, b = page_end_issues(pg)
                    if a:
                        res["a"].append((blk, key, " / ".join(pg)))
                    if b:
                        res["b"].append((blk, key, " / ".join(pg)))
                if improve_nounphrase(list(pg)) != pg:
                    res["e"].append((blk, key, " / ".join(pg)))
                if improve_clause(list(pg)) != pg:
                    res["d"].append((blk, key, " / ".join(pg)))

        prev = None
        for i, (kind, val) in enumerate(parts):
            if kind == "text":
                if HAND_BREAK.search(val) and not (flattened and not val.lstrip().startswith("「")):
                    res["c"].append((blk, key, val[:30]))
                pend.append(val)
            else:
                flush()
                if (
                    not flattened
                    and kind == "ctl"
                    and val[0] == 0x01
                    and prev is not None
                    and prev[0] == "text"
                    and not sentence_end(prev[1].rstrip().split(" ")[-1] if prev[1].strip() else "")
                    and i + 1 < len(parts)
                    and parts[i + 1][0] == "text"
                ):
                    res["c"].append((blk, key, prev[1][-20:]))
            prev = (kind, val)
        flush()
    return res
