"""ED4 조판 — 우리 문안을 **대사창 24칸 격자**에 맞춰 줄·쪽으로 나눈다(ED3 `typeset` 의 ED4 몫, 규격은 `docs/wrap.md`).

엔진은 **조각 안 글자를 24칸째에서 저절로 접는다**(낱말·금칙 안 봄 — 시험 빌드 실측). 그래서 우리가 어절 단위로 나눈 줄을 엔진 접힘과 맞추려면 **각 줄을 공백 코드로
24칸까지 채워** 한 조각에 이어 붙인다(`pad_rows` — ED3 와 같은 발상). 🔴 **한 쪽은 3줄(72칸)이 한도이고 넘치는 글은 조용히 사라진다**(▼ 로 이어지지 않는다 — 시험 빌드 실측).
쪽 경계는 스크립트(`02`)가 정하므로 쪽 수는 못 늘린다 — 문안을 원래 쪽 구조(`windows`)에 맞춘다.

🔴 **줄 한도는 둘이고 둘 다 건다**(관리자 10-24): ① 글리프 24개 이하(엔진이 칸 수로 센다 — 반각 훅도 이건 못 바꾼다) ② 픽셀 폭 288 이하(`halfwidth.py` 훅이 반각을 6px 로 앉힌다).
글리프가 12px 이하니 ①을 지키면 ②는 늘 따라온다 — 그래서 줄바꿈은 글리프 수로 하고 ②는 단언으로 둔다. 반각 때문에 생기는 줄 끝 여백은 그대로 둔다
(용량은 쪽 늘리기가 받는다 — 줄바꿈 연산까지 건드리는 패치는 안 한다).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared.text import krwrap

COLS = 24  # 격자 열 수 = 한 줄 칸 수(조각 안에서 24칸째에 엔진이 접는다)
PAGE_LINES = 3  # 한 쪽 줄 수(차면 ▼)
CELL_PX = 12
STRIP_AFTER = ""  # 반각 훅이 섰으니 부호 뒤 공백을 지우지 않는다(번역 규칙 「공백 유지」)
LINE_PX = COLS * CELL_PX  # 288
SPACE = " "


def _widths():
    import hangul

    return {ch: 6 for ch in (" ", *hangul.load_half())}


WIDTHS = _widths()  # {글자: px} — 반각 6px, 나머지 12px


class TypesetError(Exception):
    pass


def px_width(text):
    """줄의 픽셀 폭 — 반각은 6, 나머지 12."""
    return sum(WIDTHS.get(c, CELL_PX) for c in text)


def rows(text, *, cols=COLS):
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
            return out
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


def page_segments(texts, nseg, *, cols=COLS, page_lines=PAGE_LINES):
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
    rws = rows(text, cols=cols)
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
    for st in message_streams(mem):
        msg, page = [], Run()
        prev = None
        for q, v in st["prints"]:
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
