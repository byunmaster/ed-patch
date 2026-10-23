"""대사 조판 — 공용 krwrap 을 PCE ED2 대사창 규격에 맞춰 부른다.

폭 14칸(글자 = 12px 한 칸 · 공백 = 반각 4px = 1/3 칸, 실측 10-12 → 168px) · 한 창 3줄(화자가 있으면 화자 줄이 따로 윗줄).
부호는 지금 12px 글리프라 한 칸으로 센다(반각 부호 렌더러는 P2 조판 몫).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from text import krwrap

import font

WIDTH = 14.0001
LINES = 3
SPACE_PX = 4


def adv(ch: str) -> int:
    """대사창 글자 전진 폭 px — 공백 4 · 한 바이트 ASCII(`. , ! ?` 숫자 대문자) 8 · 나머지 12. 한 바이트 ASCII 는 `narrow.py`(처리기 이음매)로 mode 2 반각 처리기를 타서 8px 다
    (그 이음매 없이는 전각으로 바뀌어 12px 씩 갔다 — 10-19 실측)."""
    return font.adv(ch)


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


def pages(text: str) -> list[list[str]]:
    """문안 → [[줄…], …]. `\\f` 는 강제 쪽 넘김, `\\n` 은 하드 개행. 엔진이 줄을 꺾을 줄이 생기면(줄 끝 부호가 168px 에 닿음) 폭을 4px 씩 줄여 다시 짠다."""
    text = spaced(text.replace("~", "～"))  # 규칙 1-2 — 물결표는 전각 `～`(ASCII `~` 는 글리프가 다른 작은 물결이다; PS1 문안·우리 문안의 `~` 를 여기서 바로잡는다)
    out: list[list[str]] = []
    for chunk in text.split("\f"):
        first = krwrap.wrap_pages(chunk, WIDTH, LINES, cell_width=cell)
        pgs = first
        for w in (WIDTH - 1 / 3, WIDTH - 2 / 3, WIDTH - 1):
            if not any(engine_wraps(line) for p in pgs for line in p):
                break
            pgs = krwrap.wrap_pages(chunk, w, LINES, cell_width=cell)
        else:
            if any(engine_wraps(line) for p in pgs for line in p):
                pgs = first  # 어떻게 짜도 닿는 줄(끊을 데 없는 긴 낱말) — 처음 조판을 둔다
        out.extend(pgs)
    for p in out:
        for line in p:
            assert px(line) <= 14 * 12, (line, px(line))
    assert ink(text) == ink("".join(x for p in out for x in p)), ("조판이 글을 잃었다", text)
    return out
