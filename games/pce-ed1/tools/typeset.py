"""대사 조판 — 공용 krwrap 을 이 창 규격(status.md 3·4절)에 맞춰 부른다.

폭 13칸(한 글자 = 1칸, 전각만) · 한 창 3줄(화자가 행 0) · 페이지는 `05`
🔴 화자가 있으면 **첫 줄 ≤ 10칸** — 넘은 만큼 화자 이름이 밀린다(실측). 기전을 풀면 넓힌다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from text import krwrap

WIDTH = 13
FIRST_WITH_SPEAKER = 10
LINES = 3


def cell(_ch: str) -> float:
    return 1.0  # 이 창엔 반각이 없다 — 공백도 전각 한 칸


def pages(text: str, *, speaker: bool) -> list[list[str]]:
    """문안 → [[줄…], …]. `\\n` 은 하드 개행, `\\f` 는 강제 페이지."""
    out: list[list[str]] = []
    for chunk in text.split("\f"):
        pg = krwrap.wrap_pages(chunk, WIDTH, LINES, cell_width=cell)
        if speaker and pg and pg[0] and len(pg[0][0]) > FIRST_WITH_SPEAKER:
            # 첫 줄만 좁히면 되지만 krwrap 엔 줄별 폭이 없다 — 첫 창을 10칸으로 다시 짠다
            first = krwrap.wrap_pages(chunk, FIRST_WITH_SPEAKER, LINES, cell_width=cell)
            pg = (
                first[:1]
                + krwrap.wrap_pages(
                    "\n".join(l for p in first[1:] for l in p),
                    WIDTH,
                    LINES,
                    cell_width=cell,
                    protect_hard=False,
                )
                if len(first) > 1
                else first
            )
        out.extend(pg)
        speaker = False  # 둘째 창부터는 화자 줄이 없다
    for p in out:
        for line in p:
            assert len(line) <= WIDTH, (line, len(line))
    return out
