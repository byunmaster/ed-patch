"""ED4 조판 — 우리 문안을 **대사창 24칸 격자**에 맞춰 줄·쪽으로 나눈다(ED3 `typeset` 의 ED4 몫, 규격은 `docs/wrap.md`).

엔진은 **조각 안 글자를 24칸째에서 저절로 접는다**(낱말·금칙 안 봄 — 시험 빌드 실측). 그래서 우리가 어절 단위로 나눈 줄을 엔진 접힘과 맞추려면 **각 줄을 공백 코드로
24칸까지 채워** 한 조각에 이어 붙인다(`pad_rows` — ED3 와 같은 발상). 🔴 **한 쪽은 3줄(72칸)이 한도이고 넘치는 글은 조용히 사라진다**(▼ 로 이어지지 않는다 — 시험 빌드 실측).
쪽 경계는 스크립트(`02`)가 정하므로 쪽 수는 못 늘린다 — 문안을 원래 쪽 구조(`windows`)에 맞춘다.

⚠ 지금 엔진엔 반각이 없다 — 코드 하나 = 12px 한 칸(공백도). 그래서 폭은 전부 1칸이고, 「부호 뒤 공백 제거」(`STRIP_AFTER`)로 줄을 줄인다(ED3 가 반각 패치 전에 쓰던 옛 규약).
반각 엔진 패치가 서면 `WIDTHS` 만 채우면 된다(공백 · `. , ! ?` 6px).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared.text import krwrap

COLS = 24  # 격자 열 수 = 한 줄 칸 수(조각 안에서 24칸째에 엔진이 접는다)
PAGE_LINES = 3  # 한 쪽 줄 수(차면 ▼)
CELL_PX = 12
STRIP_AFTER = ".,"  # 반각이 없는 동안 — 부호 뒤 공백을 지워 줄을 줄인다
WIDTHS = {}  # {글자: px} — 반각 엔진 패치 뒤에 채운다(공백·`. , ! ?` = 6)
SPACE = " "


class TypesetError(Exception):
    pass


def cell_width(ch):
    """글자의 칸 폭(소수). 코드 하나 = 12px = 1칸."""
    return WIDTHS.get(ch, CELL_PX) / CELL_PX


def width_cells(text):
    return sum(cell_width(c) for c in text)


def rows(text, *, cols=COLS):
    """문안 → 줄 목록(어절 단위, 줄 폭 ≤ `cols` 칸). krwrap 의 어절 단위·금칙·고아 처리를 쓴다.

    🔴 폭이 넘는 줄이 나오면 운다 — 엔진이 어절 한복판에서 접어 버린다.
    """
    out = krwrap.wrap(text, width=float(cols), cell_width=cell_width, strip_after=STRIP_AFTER)
    for row in out:
        if width_cells(row) > cols or len(row) > cols:
            raise TypesetError(f"줄이 {cols}칸을 넘는다({width_cells(row):g}): {row!r}")
    return out


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


def page_segments(texts, nseg, *, cols=COLS, page_lines=PAGE_LINES):
    """한 **쪽**(스크립트에서 `01` 로 이어진 조각 `nseg` 개)의 번역 문장들 → 같은 개수의 조각 문자열.

    문장들을 이어 어절 단위로 다시 나눠 첫 조각에 줄 패딩으로 몰고 나머지는 빈 조각으로 둔다(빈 꼬리는 화면에 아무것도 안 그린다 — 실측).
    🔴 **한 쪽은 `page_lines`(3)줄이 한도다** — 넘치는 줄은 **조용히 사라진다**(시험 빌드 실측: 4·5줄째가 화면에 안 나온다). 넘으면 운다.
    🔴 쪽 수는 스크립트가 정한다(`02`) — 조각을 늘려 쪽을 더할 수 없다. 문안은 원래 쪽 구조에 맞춘다.
    """
    text = " ".join(t.strip() for t in texts if t and t.strip())
    if not text:
        return [""] * nseg
    rws = rows(text, cols=cols)
    if len(rws) > page_lines:
        raise TypesetError(
            f"{len(rws)}줄 > 쪽 한도 {page_lines}줄(넘치는 줄은 화면에서 사라진다): {text!r}"
        )
    return [pad_rows(rws, cols=cols)] + [""] * (nseg - 1)


def windows(mem):
    """[[[조각 색인…](쪽)…](메시지)…] — 표 규격 멤버의 대사 흐름. `0F <색인>` 뒤 바이트가 `01`(같은 쪽 다음 줄) · `02`(쪽 넘김) · 그 밖(끝).

    ⚠ 자리를 구조로만 가른다(`0F` 연산자 + 4바이트 간격) — 대사가 아닌 자리의 `0F` 도 섞일 수 있다(25~28코드 조각 287개가 그런 자리).
    """
    from shared.ps1 import gmf_script as sm

    info = sm.parse(mem)
    sites = info["pointers"]
    out, msg, page = [], [], []
    prev_q = None
    for q, v in sites:
        linked = (
            prev_q is not None
            and q - prev_q == 4
            and mem[prev_q + 2] in (1, 2)
            and mem[q - 1] == 0x0F
        )
        if not linked and page:
            msg.append(page)
            out.append(msg)
            msg, page = [], []
        elif linked and mem[prev_q + 2] == 2:
            msg.append(page)
            page = []
        page.append(v)
        prev_q = q
    if page:
        msg.append(page)
        out.append(msg)
    return out


def rows_of(n_codes, cols=COLS):
    """조각 하나가 차지하는 줄 수 — 엔진이 24칸째에서 접는다. 빈 조각은 0줄(같은 쪽의 빈 꼬리는 아무것도 안 그린다 — 실측)."""
    return -(-n_codes // cols) if n_codes else 0


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
