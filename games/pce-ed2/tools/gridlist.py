"""디버그 마을 목록 격자 — 좁은 글꼴(`06` 모드, 한 칸 8px) 목록 줄을 **한 항목 = 한 칸 = 한 커서**로 다시 짠다(마스터 11-22).

배경(실측 11-22, 원판 디버그 사본 대조):
 · 좁은 글꼴 목록에서 글자 8px · ASCII 공백 4px(실측 11-22 v4 화면: 「표」+공백 7 → 다음 항목이 36px 뒤). 칸은 8px, 칸 폭 `P`칸 = `8P`px.
 · 커서 틀 폭은 목록마다 스크립트의 `18 <단계>`(`cursorw.py`)가 정한다 — 원판은 일본어 이름이 틀보다 길어도 틀이 앞 글자만 덮는다. 한국어는 이름이 틀 안에 들도록 단계를 올린다.
 · 줄 한계는 행 전체 168px(실측 v5: 「비스나의 열매」가 128+32=160 에서 한 글자 더 가면 꺾임 — 대사창과 같은 한계) — 마지막 글자 끝이 넘으면 엔진이 글자 단위로 꺾는다(「비스의 버/섯」).
방법: 목록의 한국어 항목(순서 = 커서 번호)을 모아 가장 긴 이름 폭 `Lpx` → 틀 단계 `cursorw.step_for(Lpx)` → 칸 폭 `P = max(ceil((Lpx+4)/8), ceil((틀 폭−2)/8))`칸 → 열 수(원문 열 수, 행 폭 27칸 안에서) 로 균일한 격자에 놓고 짧은 이름 뒤를 ASCII 공백으로 채운다.
"""

import math
import re

import cursorw

_REF = re.compile(r"\{@\d+\}|\{\$[0-9A-Fa-f]+\}")
LIMIT_PX = 168


def parse_items(tmpl: str):
    """⟦ 틀 → (items[(표지들, 이름)], 줄별 `$06` 접두 여부, 줄 끝 표지). 이름 속 전각 공백은 8px 공백 하나로 본다."""
    body = tmpl[1:] if tmpl.startswith("⟦") else tmpl
    items: list[tuple[str, str]] = []
    per_row = False
    tails = ""
    for r in body.split("\\n"):
        pos = 0
        marks = ""
        parts = []
        for m in _REF.finditer(r):
            txt = r[pos : m.start()]
            if txt:
                parts.append((marks, txt))
                marks = ""
            marks += m.group(0)
            pos = m.end()
        txt = r[pos:]
        parts.append((marks, txt))
        for m, t in parts:
            t2 = t.replace("\u3000", " ").strip(" ")
            if t2:
                if "{$06}" in m:
                    per_row = True
                items.append((m.replace("{$06}", ""), t2))
            else:
                tails += m
    return items, per_row, tails


def layout(tmpl: str, cols: int, name_fix=None, row_counts: list[int] | None = None, pitch_override: list[int] | None = None) -> tuple[str, int, list[str]]:
    """틀 → (새 틀, 커서 단계, 보고). `name_fix` = 이름 바꿈 함수(정렬용). 열 수는 행 폭이 넘으면 줄인다."""
    items, per_row, tails = parse_items(tmpl)
    notes: list[str] = []
    names = [name_fix(n) if name_fix else n for _m, n in items]
    pxs = [cursorw.name_px(n) for n in names]
    Lpx = max(pxs)
    rc = row_counts or [min(cols, len(items) - r0) for r0 in range(0, len(items), cols)]
    # 균일 칸 폭: 마지막 열 최장 이름이 168px 안에 들 최대 칸 폭 Pmax(4px 단위) → 틀 단계는 칸 폭(+2px)을 넘지 않는 가장 큰 쪽(이웃 글자를 덮지 않게)
    ncol = max(rc)
    lastmax = 0
    k = 0
    for n in rc:
        lastmax = max(lastmax, pxs[k + n - 1])
        k += n
    Pmax = ((LIMIT_PX - lastmax) // (ncol - 1)) // 4 * 4 if ncol > 1 else 0
    need = Lpx + 2
    step = next((i2 for i2, w in enumerate(cursorw.WIDTH_PX) if w >= need), len(cursorw.WIDTH_PX) - 1)
    while ncol > 1 and step > 0 and cursorw.WIDTH_PX[step] > Pmax + 2:
        step -= 1
    W = cursorw.WIDTH_PX[step]
    P = min(Pmax, -(-max(W - 2, Lpx + 4) // 4) * 4) if ncol > 1 else 0
    pitch = list(pitch_override) if pitch_override else [P] * max(ncol - 1, 0)
    if pitch_override:
        assert sum(pitch) + lastmax <= LIMIT_PX, (pitch, lastmax)
    over = [(n, p) for n, p in zip(names, pxs) if p + 2 > W]
    notes.append(f"열 칸 폭 {pitch} 마지막 열 최장 {lastmax}px")
    notes.append(f"최장 {Lpx}px 단계={step}({W}px) 칸폭 {P}px 열={ncol} 행폭 최대 {(ncol - 1) * P + lastmax}px · 틀 밖으로 나오는 이름 {len(over)}개 {[n for n, _ in over][:8]}")
    assert sum(rc) == len(items), (rc, len(items))
    rows = []
    r0 = 0
    for cnt in rc:
        s = ""
        chunk = range(r0, r0 + cnt)
        r0 += cnt
        for c, k in enumerate(chunk):
            m, _ = items[k]
            n = names[k]
            last = k == chunk[-1]
            if c == 0 and per_row:
                m = "{$06}" + m
            s += m + n + ("" if last else " " * max(0, (pitch[c] - cursorw.name_px(n)) // 4))
        rows.append(s)
    return "⟦" + "\\n".join(rows) + tails, step, notes
