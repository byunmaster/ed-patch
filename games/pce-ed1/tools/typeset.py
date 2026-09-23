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
        if "\n" in chunk and not speaker:
            # 🔴 **하드 개행이 든 창은 줄을 그대로 둔다**(빈 줄·앞 공백 포함) — krwrap 은
            #    protect_hard 여도 빈 줄과 줄머리 공백을 지워 장 끝 「완」 카드가 「…여행 완」 한 줄로
            #    붙었다(2026-09-24, 여섯 장 모두). 원문도 전각 공백으로 가운데를 맞춘 카드다.
            #    정본에서 `\n` 을 쓰는 건 그 카드뿐이라 대사 조판은 안 바뀐다.
            lines = chunk.split("\n")
            # ⚠ 창은 세 줄이다 — 네 줄째는 화면에서 빈 줄이 먹힌다(종장 카드 실측 2026-09-24)
            assert len(lines) <= LINES and all(len(x) <= WIDTH for x in lines), chunk
            out.append(lines)
            speaker = False
            continue
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
