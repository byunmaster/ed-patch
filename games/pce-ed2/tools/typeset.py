"""대사 조판 — 공용 krwrap 을 PCE ED2 대사창 규격에 맞춰 부른다.

폭 14칸(글자 = 12px 한 칸 · 공백 = 반각 4px = 1/3 칸, 실측 10-12 → 168px) · 한 창 3줄(화자가 있으면 화자 줄이 따로 윗줄).
부호는 지금 12px 글리프라 한 칸으로 센다(반각 부호 렌더러는 P2 조판 몫).
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from text import krwrap

import font
import linemetrics

WIDTH = 14.0001
LINES = 3  # 화자 머리가 있는 쪽의 본문 줄 수(창은 머리 줄 포함 4행)
LINES_HEADLESS = 4  # 머리 없는 쪽 — 원판은 4줄을 담는다(원판 전 대사 실측 10-31: 머리 없는 쪽 4줄 325쪽 · 머리 있는 쪽 최대 3줄)
SPACE_PX = 4


def adv(ch: str) -> int:
    """대사창 글자 전진 폭 px — 공백 4 · 한 바이트 ASCII(`. , ! ?` 숫자 대문자) 8 · 나머지 12. 「」 는 `kagi.py` 가 8px. 한 바이트 ASCII 는 `narrow.py`(처리기 이음매)로 mode 2 반각 처리기를 타서 8px 다
    (그 이음매 없이는 전각으로 바뀌어 12px 씩 갔다 — 10-19 실측)."""
    return font.adv_dlg(ch)


def cell(ch: str) -> float:
    return adv(ch) / 12


def px(line: str) -> int:
    return sum(adv(c) for c in line)


def ink(s: str) -> str:
    return "".join(c for c in s if c not in " \u3000\n\f§")


def spaced(text: str) -> str:
    """공통 규칙 2-11 — `…` 뒤에 말이 이어지면 반각 공백(`그대도…잊었다` → `그대도… 잊었다`). 줄 끝·닫는 부호·여는 괄호(따옴표) 앞은 그대로.
    예외(마스터 10-12·10-13): ⓪ 문장 맨 앞의 `…` 는 붙인다(`…그랬던 것 같았다.` — 앞말 뒤에 오는 말줄임이 아니다) ① 한 낱말을 음절마다 끊어 말하는 꼴은 붙인다(`세…리…오…스…`) — 앞 음절이 `…` 바로 뒤거나 뒤 음절 다음이 또 `…`
    ② 의성어 되풀이는 붙인다(`흑…흑…흑…` · `으흑…으흑…`) — `…` 앞뒤 낱말이 같다."""

    def fix(m: re.Match) -> str:
        i = m.start()
        hangul = lambda c: "가" <= c <= "힣"  # noqa: E731
        before_split = i >= 2 and text[i - 2] == "…" and hangul(text[i - 1])
        after_split = text[i + 2 : i + 3] == "…" and hangul(text[i + 1]) and i >= 1 and hangul(text[i - 1])
        j = i
        while j > 0 and hangul(text[j - 1]):
            j -= 1
        prev = text[j:i]
        repeat = bool(prev) and text.startswith(prev, i + 1) and not hangul(text[i + 1 + len(prev) : i + 2 + len(prev)] or " ")
        k = i  # `…` 덩이(`……`)의 첫 자리 앞 글자 — 문장 맨 앞이면(앞이 없거나 공백·줄바꿈·쪽·여는 부호) 붙인다(마스터 10-13: 맨 앞 `…` 는 붙인다)
        while k > 0 and text[k - 1] == "…":
            k -= 1
        initial = k == 0 or text[k - 1] in " \u3000\n\f§¶「『(“‘"
        return "…" if initial or before_split or after_split or repeat else "… "

    return re.sub(r"…(?=[가-힣A-Za-z0-9])", fix, text)


LIMIT_PX = 14 * 12


def engine_wraps(line: str) -> bool:
    """엔진은 글자마다 「이 글자 시작 x + 12px(반각도 한 칸으로 셈) > 168px」이면 줄을 꺾는다 — 실측(10-19 `가`×14 + `.` · `가`×12 + 공백 + `가` + `.` 가 `.` 만 다음 줄로 떨어졌다).
    그려지는 폭은 반각 8px 이라 조판기(합계 px)는 통과시키는 줄이 있다 — 줄 끝 부호가 168px 에 딱 닿는 경우."""
    x = 0
    for c in line:
        if c != " " and x + font.CELL_PX > LIMIT_PX:
            return True
        x += adv(c)
    return False


_PHRASES_READY = False


def _ensure_phrases() -> None:
    """굳은 [명사+명사] 구(규칙 2-16 e)는 대사 전량에서 두 번 이상 나온 이음이다 — 처음 쓸 때 한 번 모은다."""
    global _PHRASES_READY
    if not _PHRASES_READY:
        _PHRASES_READY = True
        import check_punct

        linemetrics.set_phrases(t for _w, k, t, _d in check_punct.corpus() if k == "dlg")


def _lay(chunk: str, w: float, lines: int = LINES) -> list[list[str]]:
    old = linemetrics.PAGE_LINES
    linemetrics.PAGE_LINES = lines
    try:
        return _lay_n(chunk, w, lines)
    finally:
        linemetrics.PAGE_LINES = old


def _lay_n(chunk: str, w: float, lines: int) -> list[list[str]]:
    """krwrap 조판을 기본으로 하고, 규칙 2-16 지표(`linemetrics`)에 걸리는 구간만 규칙을 아는 자체 흐름(`linemetrics.flow`)으로 다시 짠다 —
    지표가 줄고 쪽 수가 안 늘 때만 채택한다. 공용 krwrap 은 손대지 않는다(동결)."""
    base = krwrap.wrap_pages(chunk, w, lines, cell_width=cell)
    _ensure_phrases()
    if os.environ.get("ED_LINERULE") == "0" or "\n" in chunk:  # ED_LINERULE=0 — 규칙 끄기(「전」 지표 계측용)
        return base
    words = chunk.split()
    fit = lambda ln: px(ln) <= w * 12 and not engine_wraps(ln)  # noqa: E731
    cand = base
    mine = linemetrics.repage(words, fit, base)
    if (
        ink("".join(x for p in mine for x in p)) == ink(chunk)
        and all(len(p) <= lines for p in mine)
        and len(mine) <= len(base)
        and (linemetrics.window_stats(base)[0] or not linemetrics.window_stats(mine)[0])  # 마지막 창에 한 어절만 남는 새 꼴은 만들지 않는다
        and not linemetrics.regress(base, mine)  # f 퇴행 금지 — 새로 생긴 끊김이 덩어리를 가르거나 한 줄 문장을 가르면 이 고침은 버린다
        and linemetrics.count(linemetrics.chunk_metrics(mine)) < linemetrics.count(linemetrics.chunk_metrics(base))
    ):
        cand = mine
    return _spread(chunk, words, fit, base, cand)


def _spread(chunk, words, fit, base, cand):
    """창(쪽) 분배(마스터 10-26) — 창이 둘 이상인 구간에서 마지막 창에 한 어절만 남거나 창 줄 수 차가 2 이상이면, 창 수를 안 늘리고 쪽 경계만 옮겨 고른다."""
    bal = linemetrics.rebalance(words, fit, cand)
    if (
        bal
        and ink("".join(x for p in bal for x in p)) == ink(chunk)
        and not linemetrics.regress(base, bal)
    ):
        return bal
    return cand


def _lay_kinds(chunk: str, w: float, headed: bool) -> list[list[str]]:
    """쪽 종류에 맞춘 조판 — 화자 머리가 있는 첫 쪽만 본문 3줄, 나머지(머리 없는 쪽)는 4줄. 첫 쪽을 3줄로 짠 뒤 남은 글을 4줄로 다시 짠다(문장 단위 쪽 가름을 그대로 쓴다).
    하드 개행(`\\n`)이 든 덩이는 다시 짜면 개행이 풀리므로 첫 쪽 종류의 줄 수로 통째로 짠다."""
    if LINES_HEADLESS == LINES:  # 4줄을 끈 조판(`pages(target=…)` 되돌림) — 종전 3줄 조판 그대로
        return _lay(chunk, w, LINES)
    if not headed:
        return _pick4(chunk, w, [], _lay(chunk, w, LINES_HEADLESS), _lay(chunk, w, LINES))
    pgs = _lay(chunk, w, LINES)
    if len(pgs) < 2 or "\n" in chunk:
        return pgs
    rest = " ".join(ln for p in pgs[1:] for ln in p)
    return pgs[:1] + _pick4(chunk, w, pgs[:1], _lay(rest, w, LINES_HEADLESS), _lay(rest, w, LINES))


def _flags(chunk: str, pgs: list[list[str]], w: float) -> tuple[bool, bool]:
    """(쪽 끝 한 어절 고아가 있나 · 창 수를 안 늘리고 고르게 나눌 수 있는데 안 나눴나) — 2-16 지표 a · h2."""
    fit = lambda ln: px(ln) <= w * 12 and not engine_wraps(ln)  # noqa: E731
    spread = linemetrics.window_stats(pgs)[1] and bool(linemetrics.rebalance(chunk.split(), fit, pgs))
    return bool(linemetrics.chunk_metrics(pgs).get("a")), spread


def _pick4(chunk: str, w: float, pre: list[list[str]], c4: list[list[str]], c3: list[list[str]]) -> list[list[str]]:
    """4줄 쪽 조판(`pre` = 앞에 이미 놓인 화자 머리 쪽)을 쓰되, 3줄 조판보다 쪽이 늘거나 지표가 나빠지거나 3줄 조판에 없던 쪽 끝 고아(a)·고를 수 있는 창 분배(h2)가 새로 생기면 3줄 조판을 둔다 —
    지표 래칫(2-16 ③)을 나쁘게 만들지 않는다. 지표는 앞 쪽까지 이은 덩이 전체로 잰다."""
    if len(c4) > len(c3):
        return c3
    n4, n3 = (linemetrics.count(linemetrics.chunk_metrics(pre + c)) for c in (c4, c3))
    if n4 > n3 or linemetrics.regress(pre + c3, pre + c4):
        return c3  # 3줄 조판에 없던 끊김 퇴행(문장 끝 경계가 문장 중간으로 옮겨감 등)이 생기면 안 쓴다
    a4, h4 = _flags(chunk, pre + c4, w)
    a3, h3 = _flags(chunk, pre + c3, w)
    return c3 if (a4 and not a3) or (h4 and not h3) else c4


def pages(text: str, headed: bool = False, target: int | None = None) -> list[list[str]]:
    """문안 → 쪽. `target` = 원판 창(쪽) 수 — 4줄 조판이 원판보다 창을 **줄이면**(원문 창 내용을 합침) 3줄 조판으로 되돌린다
    (번역 규칙 2-17: 여러 창 대사는 창마다 원문 창 내용을 그대로 둔다 — 4줄은 넘침으로 쪽이 늘어나는 걸 막을 때만 쓴다)."""
    global LINES_HEADLESS
    out = _pages(text, headed)
    if target and len(out) < target and LINES_HEADLESS != LINES:
        keep, LINES_HEADLESS = LINES_HEADLESS, LINES
        try:
            out3 = _pages(text, headed)
        finally:
            LINES_HEADLESS = keep
        if len(out3) > len(out) and not (linemetrics.window_stats(out3)[0] and not linemetrics.window_stats(out)[0]):
            return out3  # 단 3줄 조판이 마지막 창에 한 어절만 남기면(2-17 이 계속 막는다) 4줄 조판을 둔다
    return out


def _pages(text: str, headed: bool) -> list[list[str]]:
    """문안 → [[줄…], …]. `\\f` 는 강제 쪽 넘김, `\\n` 은 하드 개행. 엔진이 줄을 꺾을 줄이 생기면(줄 끝 부호가 168px 에 닿음) 폭을 4px 씩 줄여 다시 짠다."""
    text = spaced(text.replace("~", "～"))  # 규칙 1-2 — 물결표는 전각 `～`(ASCII `~` 는 글리프가 다른 작은 물결이다; PS1 문안·우리 문안의 `~` 를 여기서 바로잡는다)
    out: list[list[str]] = []
    for ci, chunk in enumerate(text.split("\f")):
        hd = headed and ci == 0  # 쪽 가름(`\f`) 뒤 쪽은 화자 머리가 없다
        first = _lay_kinds(chunk, WIDTH, hd)
        pgs = first
        for w in (WIDTH - 1 / 3, WIDTH - 2 / 3, WIDTH - 1):
            if not any(engine_wraps(line) for p in pgs for line in p):
                break
            pgs = _lay_kinds(chunk, w, hd)
        else:
            if any(engine_wraps(line) for p in pgs for line in p):
                pgs = first  # 어떻게 짜도 닿는 줄(끊을 데 없는 긴 낱말) — 처음 조판을 둔다
        out.extend(pgs)
    for p in out:
        for line in p:
            assert px(line) <= 14 * 12, (line, px(line))
    assert ink(text) == ink("".join(x for p in out for x in p)), ("조판이 글을 잃었다", text)
    return out
