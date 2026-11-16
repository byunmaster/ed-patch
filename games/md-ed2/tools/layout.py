"""줄·쪽 나눔 규칙 2-16 (전 기종 공통 규칙, 마스터 10-26) — 공용 krwrap 이 짠 쪽 위에 **게임 안에서** 얹는 다듬기와 지표.

krwrap(공용·동결)은 그리디 줄바꿈 + 문장 단위 쪽 묶기까지만 한다. 아래 셋은 그 결과를 보고 고친다 — 공용을 안 건드린다.

  ② 줄 나눔 — 줄이 넘쳐 **이 줄에서 시작한 절**이 다음 줄에 이어질 때, 그 절이 한 줄에 통째로 들어가면 절째 다음 줄로 내린다
     (경계 세기: 문장 끝 > 쉼표 > 연결어미. 「오,」 같은 두 음절 이하 쉼표·「그리고」 같은 문장 머리 접속어는 경계 아님.
     앞 줄에 남는 글이 `MIN_LEFT` 보다 짧으면 안 함. 본용언+보조용언 자리는 경계가 아니다 — `krwrap.split_reason`).
  ③ 쪽 나눔 — 쪽 끝 줄이 한 어절로 끝나면(쪽 끝 고아 · 문장 중간 한 낱말로 끝나는 쪽) 그 쪽의 마지막 절 경계에서 쪽을 끊고 뒤를 다시 짠다.
  ④ 정본 고유명사 속 공백(「사제 바바라」)과 굳은 명사구(「슬라임 괴롭히기」)는 줄 사이에서 안 갈린다 — 속 공백을 NBSP 자리표시로 바꿔 짜고 되돌린다.
  ① 문장 중간의 손 개행은 공백으로 읽는다(`soften`).

`metrics(...)` 가 지표 a/b/c/d 를 센다 — `check_layout.py` 가 대사 전량의 조판 결과로 재서 래칫으로 건다.
"""

import os
import re

import common  # noqa: F401  (공용 경로)
from text import krwrap

WIDTH = 17.5
LINES = 3
ENABLED = (
    os.environ.get("ED_LAYOUT", "1") != "0"
)  # 끄면 공용 krwrap 그대로 — 지표 「전」을 재는 데 쓴다
MIN_LEFT = 7.0  # 줄·쪽을 끊고 앞에 남는 글이 이 폭(= sfc-ed2 의 20/50 단위)보다 짧으면 그 자리에서는 안 끊는다
NBSP = " "
GLUE_LOCAL = (
    "슬라임 괴롭히기",
)  # 정본 고유명사는 아니지만 한 덩어리로 읽히는 명사구(마스터 10-25)

_END_RE = re.compile(r"[.!?…~」』]$")
_CONN_RE = re.compile(
    r"(?:아서|어서|여서|해서|려서|러서|라서|워서|니까|으니|면서|으며|하며|지만|는데|인데|으나|다가|도록|려고|므로|고|며|면)$"
)
_CONJ = frozenset(
    [
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
    ]
)
_SENT_END_CHARS = ".!?…~」』"


def cw(ch: str) -> float:
    # 「」『』 는 반각 글리프(진행 6px, hangul.KAGI_HALF — 마스터 도안 C판 10-26)라 0.5슬롯. 공용 krwrap 기본값(1.0)은 건드리지 않는다.
    return 0.5 if ch in (" ", NBSP, "「", "」", "『", "』") else 1.0


def tw(s: str) -> float:
    return krwrap.text_width(s, cw)


def bkind(word: str, nxt: str | None = None) -> int:
    """절 경계의 세기 — 3 문장 끝 > 2 쉼표(두 음절 이하 제외) > 1 연결어미 > 0 아님. 연결어미는 뒤 어절과 본용언+보조용언으로 묶이면 경계가 아니다."""
    w = word.replace(NBSP, " ")
    if _END_RE.search(w):
        return 3
    if w.endswith(","):
        return 2 if len(w.rstrip(",")) > 2 else 0
    if w in _CONJ or not _CONN_RE.search(w):
        return 0
    if nxt is not None and krwrap.split_reason(w, nxt.replace(NBSP, " ")):
        return 0
    return 1


def _words(line: str) -> list[str]:
    return [w for w in line.split(" ") if w]


def _split_ok(prev: str, nxt: str) -> bool:
    """prev | nxt 사이에서 줄·쪽을 끊어도 되는가(본용언+보조용언 같은 한 덩어리가 아닌가)."""
    return not krwrap.split_reason(prev.replace(NBSP, " "), nxt.replace(NBSP, " "))


def _starts(lines: list[str]) -> tuple[list[str], set[int]]:
    words: list[str] = []
    starts: set[int] = set()
    for ln in lines:
        ws = _words(ln)
        if ws:
            starts.add(len(words))
        words += ws
    return words, starts


def regress(before: list[list[str]], after: list[list[str]]) -> int:
    """(f) 규칙이 오히려 나쁘게 만든 끊김 수 — 후에 **새로 생긴** 줄 머리 중 `krwrap.split_reason`(보조용언·의존명사·관형사 고아)에 걸리는 것
    + 전에는 한 줄이던 문장이 후에 갈린 것 + 절 경계로 안 끝나는 줄 끝이 늘어난 만큼. 어절 열이 달라졌으면(다듬기가 글을 건드렸다) 큰 값을 돌려 거부시킨다."""
    wb, sb = _starts([ln for pg in before for ln in pg])
    wa, sa = _starts([ln for pg in after for ln in pg])
    if wb != wa:
        return 10**6
    n = 0

    def pstarts(pgs: list[list[str]]) -> set[int]:
        out, c = set(), 0
        for pg in pgs[:-1]:
            c += _nwords(pg)
            out.add(c)
        return out

    pb_, pa_ = pstarts(before), pstarts(after)
    n += sum(1 for i in pa_ - pb_ if not bkind(wa[i - 1], wa[i]))  # 새 쪽 경계가 절 경계가 아니다
    n += sum(1 for i in pb_ - pa_ if bkind(wb[i - 1]) == 3)  # 문장 끝이던 쪽 경계가 사라졌다
    for i in sa - sb:
        if i and not _split_ok(wa[i - 1], wa[i]):
            n += 1
    # 전 줄 끝이 절 경계였는데 후 줄 끝이 절 경계가 아니게 된 만큼(「있으면 좋으련만⏎」→「있으면⏎좋으련만 …」) — 경계로 안 끝나는 줄 끝이 늘면 센다
    def soft(w: list[str], st: set[int]) -> int:
        return sum(1 for i in st if i and not bkind(w[i - 1], w[i]))

    n += max(0, soft(wa, sa) - soft(wb, sb))
    begin = 0
    for i, w in enumerate(wb):
        if bkind(w) == 3 or i == len(wb) - 1:
            if not any(begin < j <= i for j in sb) and any(begin < j <= i for j in sa):
                n += 1
            begin = i + 1
    return n


# ── ⑥ 창 분배 (마스터 10-26: 「마지막 창에 한 어절 남는 현상 방지, 골고루 분배」) ───────────────────────────────
def _nwords(pg: list[str]) -> int:
    return sum(len(_words(ln)) for ln in pg)


def balance_pages(pages: list[list[str]]) -> list[list[str]]:
    """뒤 쪽부터 이웃 두 쪽의 줄 수 차가 2 이상이면 앞 쪽 마지막 줄을 뒤 쪽 머리로 옮긴다(창 수는 안 는다). 마지막 쪽이 한 어절뿐이면 끊김이 이음 가능(`_split_ok`)할 때,
    아니면 새 끊김이 옛 끊김보다 세거나 같을 때만 — 앞 쪽이 한 어절 줄로 끝나게 되면 안 옮긴다."""
    pages = [list(p) for p in pages]
    for k in range(len(pages) - 2, -1, -1):
        for _ in range(LINES):
            a, b = pages[k], pages[k + 1]
            if len(a) - len(b) < 2 or len(b) >= LINES:
                break
            wa, moved = _words(a[-2]), _words(a[-1])
            old = bkind(moved[-1], _words(b[0])[0])
            new = bkind(wa[-1], moved[0])
            if old == 3 or not new:  # 쪽 경계는 문장 끝 > 절 경계로만 옮긴다 — 문장 끝이던 경계를 문장 중간으로 옮기지 않고(3+1 이어도 둔다), 관형어·목적어·주어 뒤에서 안 끊는다
                break
            if not _split_ok(wa[-1], moved[0]) or (len(wa) == 1 and not _END_RE.search(wa[0])) or new < old:
                break
            pages[k], pages[k + 1] = a[:-1], [a[-1]] + b
    return pages


# ── 지표 ────────────────────────────────────────────────────────────────────────────────────
def orphan_pages(pages: list[list[str]]) -> tuple[int, int]:
    """(a) 쪽 끝 한 어절 고아 쪽 수 · (b) 그 가운데 문장 중간에서 한 낱말로 끝나는 쪽 수.

    (a): 다음 쪽이 있는 쪽의 마지막 줄이 한 어절(줄이 둘 이상인 쪽) · 앞 쪽이 문장 중간에서 끊겼는데 이 쪽 전체가 한 줄 한 어절.
    (b): 앞 쪽 규칙의 쪽 가운데 그 한 어절이 문장 끝 부호로 안 끝나는 것(문장이 다음 쪽으로 이어진다) — 둘째 경우도 센다."""
    a = b = 0
    for pi, pg in enumerate(pages):
        if len(pg) >= 2 and pi + 1 < len(pages):
            last = _words(pg[-1])
            if len(last) == 1:
                a += 1
                if not _END_RE.search(last[0]):
                    b += 1
        if pi and len(pg) == 1 and len(_words(pg[0])) == 1:
            prev = _words(pages[pi - 1][-1])
            if prev and not _END_RE.search(prev[-1]):
                a += 1
                b += 1
    return a, b


def hand_newlines(text: str) -> int:
    """(c) 원고 문안에서 문장 중간(앞 글자가 문장 끝 부호가 아님)에 박힌 손 개행 수 — 쪽·화자 머리 뒤 개행은 `<..>` 태그라 여기 안 든다."""
    n = 0
    for m in re.finditer(r"\n", text):
        i = m.start()
        if (
            0 < i < len(text) - 1
            and text[i - 1] not in _SENT_END_CHARS + "\n"
            and text[i + 1] != "\n"
        ):
            n += 1
    return n


def clause_violations(pg: list[str], width: float = WIDTH) -> list[tuple[int, int, int]]:
    """(d) 쪽 한 장 안의 (줄 i, 앞에 남길 마지막 어절 색인 j, 다음 줄의 절 끝 색인 k) — 줄 i 에서 시작한 절(ws[j+1:] + 다음 줄 ws2[:k+1])이 한 줄 폭에 든다."""
    out = []
    for i in range(len(pg) - 1):
        ws, ws2 = _words(pg[i]), _words(pg[i + 1])
        if (
            not ws or not ws2 or bkind(ws[-1], ws2[0])
        ):  # 줄이 경계로 끝나면 절이 이 줄에서 시작하지 않는다
            continue
        best = None  # (세기, j) — 가장 센 경계, 같으면 뒤쪽
        for j in range(len(ws) - 1):
            kd = bkind(ws[j], ws[j + 1])
            if kd and tw(" ".join(ws[: j + 1])) >= MIN_LEFT and (best is None or kd >= best[0]):
                best = (kd, j)
        if best is None:
            continue
        j = best[1]
        k = next(
            (k for k in range(len(ws2)) if bkind(ws2[k], ws2[k + 1] if k + 1 < len(ws2) else None)),
            None,
        )
        if k is None:
            continue
        if tw(" ".join(ws[j + 1 :] + ws2[: k + 1])) <= width:
            out.append((i, j, k))
    return out


# ── ⑦ 쪽 끝 고아 메움 (마스터 10-31: 「마지막 창에 한 어절만 남으면 안 됨」 · sfc-ed1 의 조판기 고아 메움과 같은 갈래) ─────────────────
def fill_orphan(pg: list[str], width: float = WIDTH) -> list[str]:
    """쪽의 **마지막 문장**이 두 줄 이상인데 한 어절 줄로 끝나면, 그 문장이 든 줄들만 줄 수는 그대로 두고 줄 나눔을 다시 골라 끝 줄이 두 어절 이상이 되게 한다
    (가능한 나눔 전부 중 줄 폭이 고른 것 · 줄 머리 최소 폭 `MIN_LEFT` · 새 끊김이 `_split_ok` 를 지키고 `regress` 가 0 인 것). 없으면 그대로 둔다.
    앞 문장이 끝난 줄은 건드리지 않는다."""
    from itertools import combinations

    if len(pg) < 2 or len(_words(pg[-1])) != 1:
        return pg
    start = len(pg) - 1  # 마지막 문장이 시작한 줄 — 앞 줄이 문장 끝으로 닫혔거나 쪽 머리
    while start > 0 and not _END_RE.search(_words(pg[start - 1])[-1] if _words(pg[start - 1]) else ""):
        start -= 1
    tail = pg[max(0, start) :]
    if len(tail) < 2:
        return pg
    words = [w for ln in tail for w in _words(ln)]
    n, best = len(tail), None
    if len(words) < 2 * n:
        return pg
    for cuts in combinations(range(1, len(words)), n - 1):
        idx = (0, *cuts, len(words))
        cand = [" ".join(words[idx[i] : idx[i + 1]]) for i in range(n)]
        if len(words) - idx[-2] < 2 or any(tw(c) > width for c in cand) or any(tw(c) < MIN_LEFT for c in cand[:-1]):
            continue
        cost = sum((width - tw(c)) ** 2 for c in cand)
        if best is not None and cost >= best[0]:
            continue
        if any(not _split_ok(p, q) for p, q in _boundaries(cand) - _boundaries(tail)) or regress([tail], [cand]):
            continue
        best = (cost, cand)
    return pg[: len(pg) - n] + best[1] if best else pg


# ── ⑧ 한 줄 문장 (규칙 2-10 — 마스터 10-10: 「한 줄에 나올 수 있는 문장은 한 줄로」) ─────────────────────────────────
def short_sentences(pg: list[str], width: float = WIDTH) -> list[tuple[int, int, int, int]]:
    """쪽 안에서 **한 줄에 통째로 들어가는데 두 줄 이상에 걸친** 문장 → [(첫 줄, 첫 줄 안 시작 어절 색인, 끝 줄, 끝 줄 안 끝 어절 색인)].
    문장 끝은 `_END_RE`(. ! ? … ~ 」). 변수(`§` 자리)가 낀 문장은 실폭을 몰라 건드리지 않는다."""
    out = []
    rows = [_words(ln) for ln in pg]
    start = (0, 0)
    for i, ws in enumerate(rows):
        for j, w in enumerate(ws):
            if _END_RE.search(w):
                (i0, j0), (i1, j1) = start, (i, j)
                if i1 > i0:
                    sent = rows[i0][j0:] + [w for r in rows[i0 + 1 : i1] for w in r] + rows[i1][: j1 + 1]
                    if tw(" ".join(sent)) <= width and "§" not in "".join(sent):
                        out.append((i0, j0, i1, j1))
                start = (i, j + 1) if j + 1 < len(ws) else (i + 1, 0)
    return out


def fix_sentences(pg: list[str], width: float = WIDTH) -> list[str]:
    """갈린 짧은 문장을 새 줄에서 시작해 한 줄에 둔다 — 문장 앞의 글(앞 문장 꼬리)은 앞 줄에 남기고, 문장 뒤 글은 다음 줄 앞으로 이어 다시 감는다.
    글은 안 바꾸고 쪽 수도 안 늘린다(줄은 `LINES` 안). 새 끊김은 `_split_ok` · 퇴행 0 · 쪽 끝 고아가 안 느는 것만."""
    for _ in range(4):
        vs = short_sentences(pg, width)
        if not vs:
            break
        i0, j0, i1, j1 = vs[0]
        rows = [_words(ln) for ln in pg]
        head = [" ".join(r) for r in rows[:i0]]
        if j0:
            head.append(" ".join(rows[i0][:j0]))
        sent = " ".join(rows[i0][j0:] + [w for r in rows[i0 + 1 : i1] for w in r] + rows[i1][: j1 + 1])
        rest = rows[i1][j1 + 1 :] + [w for r in rows[i1 + 1 :] for w in r]
        tail = krwrap.wrap(" ".join(rest), width, cell_width=cw) if rest else []
        cand = head + [sent] + tail
        if len(cand) > LINES or any(tw(x) > width for x in cand):
            break
        if len(short_sentences(cand, width)) >= len(vs):
            break
        if any(not _split_ok(p, q) for p, q in _boundaries(cand) - _boundaries(pg)):
            break
        if orphan_pages([cand])[0] > orphan_pages([pg])[0] or regress([pg], [cand]):
            break
        pg = cand
    return pg


# ── ② 줄 나눔 ───────────────────────────────────────────────────────────────────────────────
def _boundaries(pg: list[str]) -> set[tuple[str, str]]:
    return {
        (_words(pg[i])[-1], _words(pg[i + 1])[0])
        for i in range(len(pg) - 1)
        if _words(pg[i]) and _words(pg[i + 1])
    }


def _push_down(
    lines: list[list[str]], i: int, j: int, width: float = WIDTH
) -> list[list[str]] | None:
    """줄 i 의 ws[j+1:] 를 다음 줄 앞으로 내리고, 넘친 꼬리는 다음 줄들 앞으로 밀어 낸다. 쪽이 LINES 줄을 넘으면 None."""
    lines = [list(x) for x in lines]
    carry = lines[i][j + 1 :]
    lines[i] = lines[i][: j + 1]
    n = i + 1
    while carry:
        if n == len(lines):
            if len(lines) >= LINES:
                return None
            lines.append([])
        cur = carry + lines[n]
        carry = []
        while tw(" ".join(cur)) > width:
            carry.insert(0, cur.pop())
        if not cur:
            return None
        lines[n] = cur
        n += 1
    return lines


def fix_clauses(pg: list[str], width: float = WIDTH) -> list[str]:
    pg = list(pg)
    for _ in range(8):
        vs = clause_violations(pg, width)
        done = False
        for i, j, _k in vs:
            new = _push_down([_words(x) for x in pg], i, j, width)
            if new is None:
                continue
            cand = [" ".join(x) for x in new]
            if any(tw(x) > width for x in cand):
                continue
            if len(clause_violations(cand, width)) >= len(vs):
                continue
            if (
                len(cand) > len(pg) and len(_words(cand[-1])) == 1
            ):  # 줄을 하나 더 쓰며 한 어절짜리 꼬리줄을 만들면 안 한다
                continue
            if any(not _split_ok(p, n) for p, n in _boundaries(cand) - _boundaries(pg)):
                continue
            if orphan_pages([cand])[0] != orphan_pages([pg])[0]:
                continue
            if regress([pg], [cand]):
                continue
            pg, done = cand, True
            break
        if not done:
            break
    return pg


# ── ③ 쪽 나눔 ───────────────────────────────────────────────────────────────────────────────
def _bad_end(pages: list[list[str]], k: int) -> bool:
    pg = pages[k]
    return k + 1 < len(pages) and len(pg) >= 2 and len(_words(pg[-1])) == 1


def fix_page_ends(pages: list[list[str]], rewrap) -> list[list[str]]:
    """쪽 끝 줄이 한 어절이면 그 쪽의 뒤쪽 절 경계에서 쪽을 끊고 나머지를 `rewrap(text)` 로 다시 짠다."""
    pages = [list(p) for p in pages]
    guard = 0
    k = 0
    while k + 1 < len(pages) and guard < 40:
        guard += 1
        if not _bad_end(pages, k):
            k += 1
            continue
        pg = pages[k]
        flat = [(li, wi, w) for li, ln in enumerate(pg) for wi, w in enumerate(_words(ln))]
        cut = None
        for n in range(len(flat) - 2, -1, -1):  # 마지막 어절 앞부터 거꾸로
            li, wi, w = flat[n]
            nxt = flat[n + 1][2]
            if not bkind(w, nxt):
                continue
            kept = pg[:li] + [" ".join(_words(pg[li])[: wi + 1])]
            if tw(kept[-1]) < MIN_LEFT and len(kept) == 1:
                continue
            if len(_words(kept[-1])) < 2 and not _END_RE.search(w):
                continue
            cut = (n, kept)
            break
        if cut is None:
            k += 1
            continue
        n, kept = cut
        rest = " ".join(w for _l, _i, w in flat[n + 1 :])
        tail = " ".join(" ".join(ln.split()) for p in pages[k + 1 :] for ln in p)
        newp = rewrap((rest + " " + tail).strip())
        if len(newp) > len(pages) - k - 1 + 1:  # 쪽이 둘 이상 늘면 포기
            k += 1
            continue
        cand = pages[:k] + [kept] + newp
        if len(cand) > len(pages) + 1:
            k += 1
            continue
        pages = cand
        k += 1
    return pages


# ── [명사+명사] 굳은 구 (규칙 2-16 지표 e, md-ed1 linebreak.py 와 같은 판정) ───────────────────────────
# 형태소 분석기 없이, 앞 어절이 조사·어미·관형형·부사가 아닌 꼴이면 명사로 본다 — 같은 이음(앞 어절 + 뒤 어절 줄기)이 대사 전량에 두 번 이상
# 나올 때만 구로 친다(반복이 구라는 증거). 오탐은 줄 수가 안 늘 때만 묶으니 해가 작다.
_NOT_NOUN_END = set("은는이가을를의에도로와과만서고며면니다요죠까나네데지자게어아해라러든께야군걸들")
_NOT_NOUN = {
    "가장", "특히", "모두", "한층", "우선", "역시", "대체", "여태", "지금", "이제", "계속", "완전히", "원래",
    "여기", "그리", "또다시", "냉큼", "모조리", "빨리", "우리", "너희들", "여러분", "정말", "아주", "매우",
    "너무", "다시", "아직", "벌써", "이미", "결코", "반드시", "제발", "어서", "함께", "같이", "그냥",
    "그만큼", "엄히", "어차피", "한참", "결국", "그럼", "인제", "미리", "요즘", "더", "꽤", "자주", "부디", "먼저", "갑자기",
    "아무리", "본래", "예전처럼", "지금처럼", "평소처럼", "또", "늘", "항상", "곧", "거의", "겨우", "아예", "제법", "훨씬",
    "점점", "방금", "아까", "오늘", "내일", "어제", "때", "그대", "그런데", "그래서", "하지만", "그러나", "그러면", "참", "좀",
}  # fmt: skip
_VERB_END = ("러", "서", "면", "고", "며", "도록", "으니", "는데", "지만", "다가", "려고")
_JOSA2 = ("부터", "처럼", "까지", "마다", "도록", "보다", "에서", "한테", "께서", "에게", "으로", "이라", "라서", "듯", "만큼", "대로", "밖에")
_JOSA = "은는이가을를의에도로와과만"
_PHRASES: set | None = None


def _adnominal(w: str) -> bool:
    c = w[-1]
    if c in "던는":
        return True
    o = ord(c) - 0xAC00
    return 0 <= o < 11172 and o % 28 in (4, 8)  # 받침 ㄴ·ㄹ(관형형 -ㄴ/-ㄹ)


def noun_noun(wa: str, wb: str) -> bool:
    if not wa or not wb or wa in _NOT_NOUN or wa.rstrip(".,!?…」~") != wa:
        return False
    if wa[-1] in _NOT_NOUN_END or wa[-1] in ".,!?…」" or _adnominal(wa) or wa.endswith(_JOSA2) or krwrap._is_infinitive(wa):
        return False
    w2 = wb.rstrip(".,!?…」~")
    return not (wb[-1] in "다요죠까" or wb[0] in "그이저" or w2.endswith(_VERB_END))  # 서술어(활용형)·지시어로 시작하는 뒤는 구가 아니다


def _stem(w: str) -> str:
    return w.rstrip(_JOSA + ".,!?…」") or w


def phrases() -> set:
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


def split_phrases(pg: list[str]) -> list[int]:
    """(e) 줄 끝·첫머리로 갈린 굳은 명사구의 줄 색인(앞 줄)."""
    out = []
    for i in range(len(pg) - 1):
        a, b = _words(pg[i]), _words(pg[i + 1])
        if len(a) >= 1 and b and noun_noun(a[-1], b[0]) and (a[-1], _stem(b[0])) in phrases():
            out.append(i)
    return out


def fix_phrases(pg: list[str], width: float = WIDTH) -> list[str]:
    """줄 끝 구의 앞 어절을 다음 줄로 내려 구를 한 줄에 둔다(① 앞 어절 내려 묶기). 앞에 남는 글이 `MIN_LEFT` 보다 짧으면 이 줄부터 끝까지 다시 감는다(② 재감기).
    쪽 수는 안 늘린다 — 줄이 늘어도 `LINES` 안이면 묶는다."""
    for i in split_phrases(pg):
        ws = _words(pg[i])
        cands = []
        for k in (1, 2):  # 구의 앞 어절 하나, 안 되면 둘(「달라지신 것」 처럼 관형형+의존명사를 같이)을 내린다
            if len(ws) > k and tw(" ".join(ws[:-k])) >= MIN_LEFT:
                pushed = _push_down([_words(x) for x in pg], i, len(ws) - k - 1, width)  # 뒤 줄 짜임을 최대한 두고 넘친 꼬리만 밀어 낸다
                if pushed:
                    cands.append([" ".join(x) for x in pushed])
                cands.append(pg[:i] + [" ".join(ws[:-k])] + krwrap.wrap(" ".join(ws[-k:]) + " " + " ".join(pg[i + 1 :]), width, cell_width=cw))
        cands.append(pg[:i] + krwrap.wrap(" ".join(pg[i:]), width, cell_width=cw))
        for cand in cands:
            if cand == pg or len(cand) > LINES or any(tw(x) > width for x in cand):
                continue
            if len(split_phrases(cand)) >= len(split_phrases(pg)):
                continue
            if regress([pg], [cand]) or any(not _split_ok(p, q) for p, q in _boundaries(cand) - _boundaries(pg)):
                continue
            return fix_phrases(cand, width)
    return pg


# ── ④ 굳은 명사구 · ① 손 개행 ──────────────────────────────────────────────────────────────
_GLUE: list[str] = []


def glue_phrases() -> list[str]:
    if not _GLUE:
        import canon

        cats = canon.nouns("eiyuu")["categories"]
        names = {v for c in cats.values() for v in c.values() if isinstance(v, str) and " " in v}
        _GLUE.extend(sorted(names | set(GLUE_LOCAL), key=len, reverse=True))
    return _GLUE


def glue(text: str) -> str:
    for ph in glue_phrases():
        if ph in text:
            text = text.replace(ph, ph.replace(" ", NBSP))
    return text


def soften(text: str) -> str:
    """① 문장 중간 손 개행 → 공백(문장 끝 부호 뒤 개행·연속 개행은 둔다)."""
    return re.sub(r"(?<![.!?…~」』\n])\n(?!\n)", " ", text.strip("\n")) if "\n" in text else text


def _squash(pages: list[list[str]]) -> str:
    return "".join(ln for pg in pages for ln in pg).replace(" ", "").replace(NBSP, "")


def wrap_pages(
    text: str, width: float = WIDTH, lines_per_page: int = LINES, **kw
) -> list[list[str]]:
    """`krwrap.wrap_pages` + 2-16 다듬기. 서명은 같다(`cell_width`·`strip_after` 등은 그대로 통과)."""
    kw.setdefault("strip_after", "")
    if not ENABLED:
        return krwrap.wrap_pages(text, width=width, lines_per_page=lines_per_page, **kw)
    text = glue(soften(text))

    def base(t: str) -> list[list[str]]:
        return krwrap.wrap_pages(t, width=width, lines_per_page=lines_per_page, cell_width=cw, **kw)

    global F_TOTAL, F_REVERT, PRESERVED
    pages0 = base(text)

    def refine(pgs: list[list[str]], page_ends: bool) -> list[list[str]]:
        if page_ends:
            pgs = fix_page_ends(pgs, base)
        pgs = balance_pages(pgs)
        return [
            fill_orphan(fix_sentences(fix_phrases(fix_clauses(pg, width), width), width), width)
            for pg in pgs
        ]

    pages = refine(pages0, True)
    if regress(pages0, pages):  # 쪽 나눔이 퇴행을 만들면 쪽 나눔만 빼고 다시 해 본다 — 그래도 퇴행이면 공용 조판 그대로
        F_REVERT += 1
        alt = refine(pages0, False)
        pages = alt if not regress(pages0, alt) else pages0
    F_TOTAL += regress(pages0, pages)
    # 🔴 글 보존 — 전·후를 이어 붙여 공백·개행을 빼면 같아야 한다(다듬기는 줄·쪽만 옮긴다)
    if _squash(pages) != _squash(pages0):
        raise SystemExit(f"[layout] 글이 바뀌었다: {text[:30]!r}")
    PRESERVED += 1
    return [[ln.replace(NBSP, " ") for ln in pg] for pg in pages]


# ── 지표 기록 (build.typeset 이 부른다) ────────────────────────────────────────────────────
CALLS: list[dict] = []
CTX = ""  # 지금 조판 중인 정본 열쇠(`BBB-K:스트림`) — build 가 정한다
F_TOTAL = 0  # (f) 퇴행 — 되돌린 뒤의 값(0 이어야 한다)
F_REVERT = 0  # 퇴행이 나와 되돌린 덩이 수(참고)
PRESERVED = 0  # 글 보존 검사를 통과한 덩이 수


def record(raw: str, lead: str, prefix_w: float, pages: list[list[str]]) -> None:
    CALLS.append({"raw": raw, "lead": lead, "pw": prefix_w, "pages": pages, "ctx": CTX})


def metrics(calls: list[dict] | None = None) -> dict:
    """a 쪽 끝 한 어절 고아 쪽 · b 문장 중간 한 낱말로 끝나는 쪽 · c 문장 중간 손 개행 · d 절째 내리면 들어가는데 쪼갠 줄 — 조판 호출(= 대사 덩이) 전량."""
    a = b = c = d = e = h = h2 = 0
    for cl in CALLS if calls is None else calls:
        pa, pb = orphan_pages(cl["pages"])
        a, b = a + pa, b + pb
        c += hand_newlines(cl["raw"])
        d += sum(len(clause_violations(pg)) for pg in cl["pages"])
        e += sum(len(split_phrases(pg)) for pg in cl["pages"])
        pgs = cl["pages"]
        if len(pgs) >= 2:
            h += _nwords(pgs[-1]) == 1  # ① 창 분배 — 창이 둘 이상인 단위의 마지막 창이 한 어절
            h2 += max(map(len, pgs)) - min(map(len, pgs)) >= 2  # 창 줄 수 차가 2 이상(줄 단위로 옮기면 고를 수 있다)
    return {"a": a, "b": b, "c": c, "d": d, "e": e, "f": F_TOTAL, "h": h, "h2": h2}


def dump(path) -> None:
    import json
    from pathlib import Path

    out = {
        "enabled": ENABLED,
        "calls": len(CALLS), "f_revert": F_REVERT, "preserved": PRESERVED,
        "metrics": metrics(),
        "pages": [[c["raw"], c["lead"], c["pw"], c["pages"], c["ctx"]] for c in CALLS],
    }
    Path(path).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
