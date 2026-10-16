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


def cell(ch: str) -> float:
    return font.adv(ch) / 12


def px(line: str) -> int:
    return sum(font.adv(c) for c in line)


def ink(s: str) -> str:
    return "".join(c for c in s if c not in " \u3000\n\f§")


def spaced(text: str) -> str:
    """공통 규칙 2-11 — `…` 뒤에 말이 이어지면 반각 공백(`그대도…잊었다` → `그대도… 잊었다`). 줄 끝·닫는 부호·여는 괄호(따옴표) 앞은 그대로.
    예외(마스터 10-12·10-13): ① 한 낱말을 음절마다 끊어 말하는 꼴은 붙인다(`세…리…오…스…`) — 앞 음절이 `…` 바로 뒤거나 뒤 음절 다음이 또 `…`
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
        return "…" if before_split or after_split or repeat else "… "

    return re.sub(r"…(?=[가-힣A-Za-z0-9])", fix, text)


def pages(text: str) -> list[list[str]]:
    """문안 → [[줄…], …]. `\\f` 는 강제 쪽 넘김, `\\n` 은 하드 개행."""
    text = spaced(text)
    out: list[list[str]] = []
    for chunk in text.split("\f"):
        out.extend(krwrap.wrap_pages(chunk, WIDTH, LINES, cell_width=cell))
    for p in out:
        for line in p:
            assert px(line) <= 14 * 12, (line, px(line))
    assert ink(text) == ink("".join(x for p in out for x in p)), ("조판이 글을 잃었다", text)
    return out
