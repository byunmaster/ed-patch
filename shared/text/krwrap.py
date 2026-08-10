"""한글 인식 줄바꿈(개행) 공통 유틸.

고정폭 게임 텍스트박스용 줄바꿈기. 어절(공백) 단위 그리디 + 금칙 처리 +
위도우(고아 줄) 방지. 플랫폼·게임 무관하게 파라미터로 조정한다.

핵심 설계 — 표시 공백과 개행은 분리한다:
  - 표시: 같은 줄에서 `.`·`,` 뒤 공백 제거는 `strip_after`로(게임별; PS1 영웅전설=".,").
  - 개행: 줄바꿈은 어절 경계(공백)에서 일어나며, 개행이 그 공백을 대신하므로
    `끝. 다음`은 한 줄이면 `끝.다음`, 넘치면 `.` 뒤에서 줄을 나눌 수 있다.
    → 공백 제거를 미리 적용해 토큰을 붙여버리면 긴 토큰이 생기므로, 공백 제거는
       **줄로 나눈 뒤** 각 줄에 적용한다.

폭 계산은 공백을 정상 폭으로 세고 표시 단계에서 공백을 지운다(=줄이 폭보다 짧아짐,
게임 자동개행을 넘지 않는 안전측). 게임별 실측 폭은 호출부에서 넘긴다.

페이지(대화창) 나누기 — 문장이 창 경계에 반반 걸리는 고아문장 방지:
  - 창 경계 후보는 "문장 끝으로 끝나는 줄" 뒤. 줄들을 문장 그룹으로 묶어
    그룹째 창에 packing한다(`wrap_pages`). 그룹이 창(3줄)을 넘으면 그 문장만
    원문 개행을 버리고 문장 단위로 재줄바꿈해 창에 들어가게 시도한다.
  - 그래도 창을 넘는 긴 문장(4줄+)은 걸침이 불가피 — 문안 수정 없이는 못 줄인다.

상태: v2 (v1 금칙+위도우 + 문장 단위 페이지네이션). 줄 균형(balance)은 후속.
"""

from __future__ import annotations

import re

# 행두 금지(줄 맨 앞에 오면 안 되는 닫는 부호류)
NO_HEAD = set(".,!?;:)]}」』〉》…·’”\"'")
# 행말 금지(줄 맨 끝에 오면 안 되는 여는 괄호류)
NO_TAIL = set("([{「『〈《‘“")

# 문장 끝: 종결부호(닫는 따옴표류 허용)로 끝남 — 창 경계 배치 가능 지점
_SENT_END = re.compile(r"[.!?…]['\"’”」』)]*\s*$")
_TERM = set(".!?…")  # 종결부호
_CLOSE = set("'\"’”」』)")  # 종결부호 뒤 허용 닫는 부호
_OPEN_NEXT = re.compile(r"[가-힣‘“「『(]")  # 공백 없이도 문장 경계로 보는 다음 글자


def is_sentence_end(line: str) -> bool:
    """줄이 문장 끝(종결부호)으로 끝나는가 — 창 경계를 둘 수 있는 줄."""
    return bool(_SENT_END.search(line))


def split_sentences(text: str) -> list[str]:
    """종결부호 기준 문장 분리. 부호 뒤 공백이 없어도 한글이 이어지면 경계로 본다
    (`.`·`,` 뒤 공백 제거된 텍스트 대응). 숫자·라틴이 이어지면(소수점·이니셜) 안 나눈다."""
    out: list[str] = []
    start = i = 0
    n = len(text)
    while i < n:
        if text[i] in _TERM:
            j = i + 1
            while j < n and text[j] in _TERM | _CLOSE:  # `!?`·`…。`·닫는 따옴표 연속
                j += 1
            k = j
            while k < n and text[k] == " ":
                k += 1
            frag = text[start:j]
            # 부호-only 조각(선두 "…." 등)은 독립 문장으로 빼지 않고 다음 문장에 붙인다 —
            # 정발도 "…. 저쪽에 계시는 분은?"을 한 줄로 둔다(유저 QA 07-28). 실내용(한글/영숫자)이
            # 있을 때만 문장 경계로 분리(그래야 "…." 뒤 공백만으로 자체 줄로 꺾이지 않는다).
            if (
                k < n
                and (k > j or _OPEN_NEXT.match(text[k]))
                and re.search(r"[가-힣A-Za-z0-9]", frag)
            ):
                out.append(frag)
                start = i = k
                continue
            i = j
            continue
        i += 1
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def default_cell_width(ch: str) -> float:
    """엔진 슬롯 폭: 공백만 0.5, 나머지는 전각 1 (PS1 영웅전설 기준).

    reinsert 인코더가 인쇄가능 ASCII(0x21~0x7E — 구두점·숫자·라틴)를 전부 **전각
    SJIS**로 내보내므로 엔진 자동개행 관점에선 모두 1슬롯이다. 온점(.)을 0.5로
    세면 폭 15줄을 14.5로 오판해 엔진이 온점만 다음 줄로 꺾는다(2026-07-19 실측:
    '안녕히 주무셨사옵니까 왕자님.' 스크린샷). 잉크 폭(표시)과 슬롯 폭(개행)은
    별개 — 여기는 개행용이므로 슬롯 기준."""
    return 0.5 if ch == " " else 1.0


def text_width(s: str, cell_width=default_cell_width) -> float:
    return sum(cell_width(c) for c in s)


def _strip_spacing(line: str, strip_after: str) -> str:
    """한 줄 안에서 strip_after 문자 뒤의 공백 제거(표시용)."""
    if not strip_after:
        return line
    out, last_ns = [], None
    for ch in line:
        if ch == " " and last_ns is not None and last_ns in strip_after:
            continue
        out.append(ch)
        if ch != " ":
            last_ns = ch
    return "".join(out)


def _strip_before(text: str, chars: str) -> str:
    """부호 앞 공백 제거(원문 전처리). 한국어는 . , ! ? 앞에 공백을 쓰지 않는다."""
    if not chars:
        return text
    out: list[str] = []
    for ch in text:
        if ch in chars:
            while out and out[-1] == " ":
                out.pop()
        out.append(ch)
    return "".join(out)


def wrap(
    text: str,
    width: float = 14,
    *,
    cell_width=default_cell_width,
    no_head: set[str] = NO_HEAD,
    no_tail: set[str] = NO_TAIL,
    avoid_widow: bool = True,
    widow_cell: float = 1.0,
    strip_before: str = "",
    strip_after: str = "",
) -> list[str]:
    """text를 width(전각 셀 기준) 이하 줄들로 나눈다. 어절(공백) 단위.

    - no_head: 이 문자로 줄이 시작하지 않게 함(앞 줄에 붙임).
    - no_tail: 이 문자로 줄이 끝나지 않게 함(다음 어절을 끌어옴).
    - avoid_widow: 마지막 줄이 폭 widow_cell 이하의 한 어절만 남으면 앞 줄에서 하나 내림.
    - strip_before: 원문 전처리로 이 문자들 앞 공백 제거(예 PS1=".,!?" — `왕자님 ?`→`왕자님?`).
    - strip_after: 줄 확정 후 이 문자들 뒤 공백 제거(표시용; 예 PS1=".," — `!`·`?`는 제외해 뒤 공백 유지).
    """
    text = _strip_before(text, strip_before)
    words = text.split()
    if not words:
        return []

    def w(words_):
        return text_width(" ".join(words_), cell_width)

    lines: list[list[str]] = []
    cur: list[str] = []
    for word in words:
        if not cur:
            cur = [word]
            continue
        if w(cur + [word]) <= width:
            cur.append(word)
            continue
        # 여기서 줄을 나누면 새 줄이 word로 시작 —
        if word[0] in no_head:  # 금칙: 닫는 부호로 줄 시작 금지 → 현재 줄에 붙임
            cur.append(word)
            continue
        if cur[-1][-1] in no_tail:  # 금칙: 여는 괄호로 줄 끝 금지 → 다음 어절 끌어옴
            cur.append(word)
            continue
        lines.append(cur)
        cur = [word]
    if cur:
        lines.append(cur)

    # 균형 배분: 줄 수를 그대로 두고 들쭉날쭉함을 최소화한다(그리디는 앞줄만 꽉 채운다).
    bal = _balance(words, len(lines), width, cell_width, no_head, no_tail)
    if bal is not None:
        lines = bal

    # 위도우 방지: 마지막 줄이 짧은 한 어절만이면 앞 줄에서 하나 내림
    if avoid_widow and len(lines) >= 2:
        last, prev = lines[-1], lines[-2]
        if len(last) == 1 and text_width(last[0], cell_width) <= widow_cell and len(prev) > 1:
            lines[-1] = [prev.pop()] + last

    return [_strip_spacing(" ".join(wds), strip_after) for wds in lines]


def _balance(words, n_lines, width, cell_width, no_head, no_tail):
    """어절 목록을 **정확히 n_lines줄**로 다시 나눠 들쭉날쭉함(raggedness)을 최소화한다.

    그리디 줄바꿈은 앞줄을 꽉 채우고 뒤로 갈수록 짧아져 `…계시다는 것을`(27) /
    `…아크담을`(24) / `무찌를 날도`(11) / `멀지 않았사옵니다.`(18)처럼 튄다. 같은 줄 수로
    22/20/20/18처럼 고르게 나누면 훨씬 읽기 좋다(유저 QA 2026-07-30, 전 대사 공통 현상).

    **줄 수가 그대로라 글자·공백·개행 총량이 안 변한다 = 바이트 중립**(메모리 영향 0).
    비용은 줄마다 (여백)^2 합 — 마지막 줄도 포함해 전체를 고르게 만든다.
    금칙(no_head/no_tail)은 그리디와 동일하게 지킨다. 해가 없으면 None(그리디 유지)."""
    m = len(words)
    if n_lines < 2 or m < n_lines:
        return None
    w = [text_width(x, cell_width) for x in words]
    sp = text_width(" ", cell_width)

    def line_w(i, j):  # words[i:j] 한 줄 폭
        return sum(w[i:j]) + sp * (j - i - 1)

    def ok(i, j):  # 폭·금칙 검사
        if line_w(i, j) > width:
            return False
        if i > 0 and words[i][0] in no_head:  # 금칙 문자로 줄 시작 금지
            return False
        if j < m and words[j - 1][-1] in no_tail:  # 여는 괄호로 줄 끝 금지
            return False
        return True

    INF = float("inf")
    dp = [[INF] * (m + 1) for _ in range(n_lines + 1)]
    back = [[-1] * (m + 1) for _ in range(n_lines + 1)]
    dp[0][0] = 0.0
    for k in range(1, n_lines + 1):
        for j in range(1, m + 1):
            for i in range(k - 1, j):
                if dp[k - 1][i] == INF or not ok(i, j):
                    continue
                cost = dp[k - 1][i] + (width - line_w(i, j)) ** 2
                if cost < dp[k][j]:
                    dp[k][j] = cost
                    back[k][j] = i
    if dp[n_lines][m] == INF:
        return None
    out, j = [], m
    for k in range(n_lines, 0, -1):
        i = back[k][j]
        out.append(words[i:j])
        j = i
    return out[::-1]


def wrap_hard(
    text: str,
    width: float = 14,
    *,
    break_char: str = "\n",
    cell_width=default_cell_width,
    no_head: set[str] = NO_HEAD,
    no_tail: set[str] = NO_TAIL,
    strip_before: str = "",
    strip_after: str = "",
    widow_cell: float = 1.0,
    merge_frag: float = 3.0,
    return_hard: bool = False,
):
    """원문의 하드 개행(break_char)을 **존중**한다.

    번역자가 넣어둔 줄바꿈이 대체로 자연스러우므로, 각 원문 줄이 폭에 맞으면 그대로 쓰고
    폭을 넘는 줄만 재줄바꿈한다. 넘친 줄의 꼬리 조각이 문장 끝이 아니면 같은 문장이 다음
    원문 줄로 이어진 것이므로 **다음 줄에 붙여 이어서 재줄바꿈**한다(캐스케이드 — 원문 창이
    우리보다 넓어 생기는 '무엇보다' 고아 줄 방지, 2026-07-19). 마지막에 아주 짧은 조각
    줄(폭 merge_frag 이하)은 이웃 줄과 병합한다(원문이 어절 중간을 끊은 드문 경우 정리).
    """
    text = _strip_before(text, strip_before)
    lines: list[str] = []
    hard: list[bool] = []  # 이 줄이 **원문 줄바꿈으로 시작**하는가(병합 금지 경계)
    segs = [t for t in (u.strip() for u in text.split(break_char)) if t]
    carry = ""
    for i, seg in enumerate(segs):
        first_hard = True
        if carry:
            # ⚠ 원문 줄바꿈을 공백으로 이어붙이면 안 된다 — 원문은 어절 중간에서도 끊는다
            # ("말아주시옵{n}소서" 실측). 반대로 어절 경계 끊김("미루는{n}것이")도 있어
            # 데이터만으론 구분 불가 → **원문 경계는 넘지 않는다**(carry를 제 줄로 확정).
            lines.append(_strip_spacing(carry, strip_after))
            hard.append(True)
            carry = ""
        if text_width(seg, cell_width) <= width:
            lines.append(_strip_spacing(seg, strip_after))
            hard.append(first_hard)
            continue
        wrapped = wrap(
            seg,
            width,
            cell_width=cell_width,
            no_head=no_head,
            no_tail=no_tail,
            widow_cell=widow_cell,
            strip_after=strip_after,
        )
        if wrapped and i + 1 < len(segs) and not is_sentence_end(wrapped[-1]):
            carry = wrapped.pop()
        for k, ln in enumerate(wrapped):
            lines.append(ln)
            hard.append(first_hard and k == 0)
    if carry:
        lines.append(_strip_spacing(carry, strip_after))
        hard.append(True)
    # 짧은 조각 줄 병합 — **원문 줄바꿈 경계(hard)는 넘지 않는다**(공백 오삽입 방지).
    # 우리가 재줄바꿈해 만든 soft 경계만 병합한다(그쪽은 원래 공백이 있던 자리).
    i = 0
    while merge_frag and i < len(lines):
        if text_width(lines[i], cell_width) <= merge_frag and len(lines) > 1:
            if (
                i > 0
                and not hard[i]
                and text_width(f"{lines[i - 1]} {lines[i]}", cell_width) <= width
            ):
                lines[i - 1] = f"{lines[i - 1]} {lines[i]}".strip()
                del lines[i], hard[i]
                continue
            if (
                i + 1 < len(lines)
                and not hard[i + 1]
                and text_width(f"{lines[i]} {lines[i + 1]}", cell_width) <= width
            ):
                lines[i] = f"{lines[i]} {lines[i + 1]}".strip()
                del lines[i + 1], hard[i + 1]
                continue
        i += 1
    return (lines, hard) if return_hard else lines


def paginate(lines: list[str], lines_per_page: int = 3) -> list[list[str]]:
    """줄 목록을 페이지(lines_per_page줄)로 묶는다."""
    return [lines[i : i + lines_per_page] for i in range(0, len(lines), lines_per_page)] or [[]]


def wrap_page(
    text: str,
    width: float = 14,
    lines_per_page: int = 3,
    **kw,
) -> list[list[str]]:
    """wrap + paginate 한 번에."""
    return paginate(wrap(text, width, **kw), lines_per_page)


def _sentence_groups(lines: list[str]) -> list[list[str]]:
    """줄들을 문장 그룹으로 묶는다 — 문장 끝으로 끝나는 줄까지가 한 그룹.
    그룹 사이가 곧 창 경계 후보(여기서 창을 나누면 문장이 안 걸린다)."""
    groups: list[list[str]] = []
    cur: list[str] = []
    for ln in lines:
        cur.append(ln)
        if is_sentence_end(ln):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def _pack_groups(groups: list[list[str]], lines_per_page: int) -> list[list[str]]:
    """문장 그룹을 창(lines_per_page줄)에 packing. 그룹이 현재 창 잔여에 안 들어가고
    창 하나에는 들어가면 새 창으로 넘긴다(문장 걸침 방지). 창을 넘는 그룹(긴 문장)은
    걸침이 불가피 — 현재 창을 채우며 흘려보낸다."""
    pages: list[list[str]] = []
    cur: list[str] = []
    for g in groups:
        if len(cur) + len(g) <= lines_per_page:
            cur += g
        elif len(g) <= lines_per_page:
            pages.append(cur)
            cur = list(g)
        else:
            rest = list(g)
            while rest:
                room = lines_per_page - len(cur)
                cur += rest[:room]
                rest = rest[room:]
                if len(cur) == lines_per_page:
                    pages.append(cur)
                    cur = []
    if cur:
        pages.append(cur)
    return pages or [[]]


def _split_oversized(groups: list[list[str]], max_lines: int) -> list[list[str]]:
    """창을 넘는 그룹(긴 문장)은 max_lines 조각으로 쪼갠다 — 창 뚫림 방지가 최우선."""
    out: list[list[str]] = []
    for g in groups:
        if len(g) <= max_lines:
            out.append(g)
            continue
        out += [g[i : i + max_lines] for i in range(0, len(g), max_lines)]
    return out


def pack_groups_target(
    groups: list[list[str]], max_lines: int, target: int
) -> list[list[str]] | None:
    """문장 그룹을 **정확히 target개** 창에 균형 분배(창당 max_lines 이하).

    엔진이 블록당 창 수를 원본 개수로 고정하는 계약 때문에 필요하다(부족=빈 창/소프트락,
    초과=꼬리 잘림). 총 줄 수가 target×max_lines를 넘어 담을 수 없으면 None을 반환해
    호출부가 그리디 packing으로 폴백하게 한다(창 수 초과는 나도 창 뚫림은 안 난다).
    줄이 창보다 적으면 뒤쪽 창은 빈 채로 두어 **개수 계약은 지킨다**."""
    if target < 1:
        target = 1
    units = _split_oversized(groups, max_lines)
    total = sum(len(u) for u in units)
    if total > max_lines * target:
        return None
    if total < target:
        # 줄이 창보다 적으면 빈 창이 생긴다(계약은 지키지만 인게임에서 빈 대사창).
        # 긴 줄을 어절 경계로 쪼개 창 수만큼 줄을 만들어 **모든 창에 내용을 채운다**.
        flat = [ln for u in units for ln in u]
        while len(flat) < target:
            i = max(range(len(flat)), key=lambda k: len(flat[k].split()))
            words = flat[i].split()
            if len(words) < 2:
                break  # 더 못 쪼갬 — 남는 창은 빈 채로(계약 우선)
            half = len(words) // 2
            flat[i : i + 1] = [" ".join(words[:half]), " ".join(words[half:])]
        units = [[ln] for ln in flat]
    pages: list[list[str]] = []
    i = 0
    for p in range(target):
        rem_pages = target - p - 1
        rem_lines = sum(len(u) for u in units[i:])
        lo = max(0, rem_lines - max_lines * rem_pages)  # 남은 창에 다 못 담기면 여기서 더 가져감
        # ⚠ hi는 **절대 max_lines를 넘지 않는다**. lo(잔여 배분상 최소치)가 상한보다 커도
        # 올려주면 마지막 창이 상한을 넘어 글자가 창을 뚫는다(eid 1327에서 9줄 실측).
        # 못 담는 잔여는 아래 leftover 루프가 새 창으로 넘긴다(창 수 초과 감수).
        hi = max(1, min(max_lines, rem_lines - rem_pages if rem_pages else rem_lines))
        balanced = rem_lines / (rem_pages + 1)
        cur: list[str] = []
        while i < len(units):
            if cur and len(cur) + len(units[i]) > hi:
                break
            if cur and len(cur) >= lo and len(cur) >= balanced:
                break
            cur += units[i]
            i += 1
        pages.append(cur)
    # 남은 유닛은 **새 창으로** 넘긴다 — 마지막 창에 몰아넣으면 줄 상한을 넘겨
    # 글자가 대사창을 뚫는다(창 뚫림 절대 금지 > 창 수 초과 감수).
    while i < len(units):
        cur = []
        while i < len(units) and len(cur) + len(units[i]) <= max_lines:
            cur += units[i]
            i += 1
        if not cur:  # 단일 유닛이 상한 초과(이론상 _split_oversized가 막음)
            cur = units[i][:max_lines]
            i += 1
        pages.append(cur)
    return pages


def wrap_pages(
    text: str,
    width: float = 14,
    lines_per_page: int = 3,
    *,
    target_pages: int | None = None,
    break_char: str = "\n",
    cell_width=default_cell_width,
    no_head: set[str] = NO_HEAD,
    no_tail: set[str] = NO_TAIL,
    strip_before: str = "",
    strip_after: str = "",
    widow_cell: float = 1.0,
    merge_frag: float = 3.0,
    protect_hard: bool = False,
    det_orphan: bool = False,
) -> list[list[str]]:
    """wrap_hard + 문장 단위 페이지네이션 — 대화창 고아문장 방지의 메인 진입점.

    protect_hard=True면 아래 "문장 단위 조판" 리플로우를 건너뛴다 — 원문 하드개행을
    가독성 위해 공백으로 되돌리는 기능이, **의도적 개행 override**를 지워버리기 때문
    (호출부가 override 마커를 감지해 이 창에서만 켠다. 기본 False = 기존 동작 불변).

    1. wrap_hard로 줄바꿈(원문 break_char 존중, 폭 초과만 재줄바꿈).
    2. 줄들을 문장 그룹으로 묶고, 창(lines_per_page)을 넘는 그룹만 원문 개행을
       버리고 문장별로 재줄바꿈(짧아지거나 창에 들어가게 되는 경우만 채택).
    3. 그룹째 창에 packing → 문장이 창 경계에 반반 걸리지 않는다.
    표시용 공백 정리(strip_after)는 창 확정 후 마지막에 적용한다.
    """
    kw = dict(cell_width=cell_width, no_head=no_head, no_tail=no_tail, widow_cell=widow_cell)
    lines, hard = wrap_hard(
        text,
        width,
        break_char=break_char,
        strip_before=strip_before,
        merge_frag=merge_frag,
        return_hard=True,
        **kw,
    )
    groups = []
    idx = 0
    for g in _sentence_groups(lines):
        g_hard = hard[idx + 1 : idx + len(g)]  # 그룹 **내부** 경계만(첫 줄 시작 경계는 무관)
        idx += len(g)
        if len(g) <= lines_per_page:
            groups.append(g)
            continue
        # ⚠ 원문 줄바꿈이 내부에 있으면 재분할 금지 — " ".join이 원문 경계를 공백으로
        # 이어붙여 어절 중간 분리를 망친다("말아주시옵"+"소서."→"말아주시옵 소서." 실측).
        # 원문은 어절 중간에서도 끊고(말아주시옵/소서), 어절 경계에서도 끊어(미루는/것이)
        # 데이터만으론 구분이 불가능하다 → 원문 경계는 그대로 줄바꿈으로 둔다.
        if any(g_hard):
            groups.append(g)
            continue
        resplit = [wrap(s, width, **kw) for s in split_sentences(" ".join(g))]
        n_new = sum(len(sg) for sg in resplit)
        if all(len(sg) <= lines_per_page for sg in resplit) or n_new < len(g):
            groups += resplit
        else:
            groups.append(g)
    # ── 문장 단위 조판(가독성 우선) ──────────────────────────────────────────
    # 문장을 **각자 새 줄에서 시작**시키면 "…하옵나이다. 오늘은"처럼 줄 중간에서 새 문장이
    # 시작하는 걸 막고, 창 경계도 문장 경계에 맞아 한 문장이 두 창으로 갈리지 않는다.
    # 다만 문장마다 마지막 줄이 남아 총 줄 수가 늘어나므로 **용량 안에 들어갈 때만** 쓰고,
    # 넘치면 기존 압축 조판으로 폴백한다(유저 지적: "다른 대사엔 공간이 부족할 수도").
    sent_groups = [
        w for s in split_sentences(text.replace(break_char, " ")) if (w := wrap(s, width, **kw))
    ]
    if sent_groups and not protect_hard:
        budget = lines_per_page * (target_pages or len(_pack_groups(groups, lines_per_page)))
        if sum(len(g) for g in sent_groups) <= budget and all(
            len(g) <= lines_per_page for g in sent_groups
        ):
            groups = sent_groups

    pages = None
    if target_pages is not None:
        pages = pack_groups_target(groups, lines_per_page, target_pages)
    if pages is None:  # target 미지정 또는 용량 초과 → 기존 그리디(창 수 초과 감수)
        pages = _pack_groups(groups, lines_per_page)
    # ⚠ 고아 정리는 **그리디 줄바꿈이 만든 줄**을 다듬는 것이다. protect_hard면 줄 경계가
    # 작성자가 지정한 것이므로 손대지 않는다 — 안 그러면 어절을 하드 개행 너머로 끌어내려
    # 지정한 조판이 조용히 뒤집힌다(여관 `하룻밤 10 Gold 입니다.` / `묵으시겠습니까?` 가
    # `…10 Gold` / `입니다. 묵으시겠습니까?` 로 뒤집힌 실측 2026-07-31).
    # 511행이 문장 단위 조판을 건너뛰는 것과 같은 규약.
    if not protect_hard:
        if det_orphan:
            _pull_det_orphans(pages, width, cell_width)
        _pull_bound_nouns(pages, width, cell_width)
        _pull_auxiliary(pages, width, cell_width)
        _pull_tail_orphans(pages, width, cell_width)
    return [[_strip_spacing(ln, strip_after) for ln in pg] for pg in pages]


# 지시관형사(이/그/저)가 줄 끝에 홀로 남으면(고아) 수식 대상 명사와 갈린다 — 다음 줄로 내려
# 붙인다. 재배치일 뿐이라 글자·줄 수·바이트 불변(메모리 중립). 줄 끝 홀로 온 '이'는 지시관형사
# 확정(주격조사 '이'는 앞말에 붙어 홀로 안 온다) → 판정 안전. 다음 줄 폭 초과 시엔 이동 안 함.
# 제/내/네(=저의/나의/너의)도 같은 자리다 — `제` / `손으로 직접…` 이 실제로 나왔다
# (유저 QA 2026-08-04). 이들도 홀로 오면 관형사 확정이라 판정이 안전하다.
#
# **부사도 같은 자리다**(유저 QA 2026-08-09 — `그런데, 로우, 왜` / `이런 짓을 한 건가?`).
# 홀로 줄 끝에 오면 수식 대상과 갈려 읽는 호흡이 끊긴다. 아래는 **어절 하나로 홀로 설 때
# 부사가 확정되는 것**만 담는다 — `안`(명사 內)·`못`(명사 못)도 어절 단독으로는 부정부사다.
_DET_ORPHAN = ("이", "그", "저", "제", "내", "네")
_ADV_ORPHAN = ("왜", "좀", "더", "잘", "꼭", "곧", "안", "못", "다시", "아직", "벌써", "이미")
# 수관형사·의문관형사도 같다 — `저택에는 몇` / `명만이 남아…` (단위명사와 갈린다).
_ADV_ORPHAN += ("몇", "여러", "어떤", "무슨", "온갖")

# 보조용언은 본용언과 한 덩어리다 — 사이에서 끊으면 `괴물들에게 당해` / `가면서 모험을…`
# 처럼 뜻이 늦게 도착한다(유저 QA 2026-08-09: `당해 가면서` · `사 가는`).
# 판정은 **둘 다** 맞아야 한다 — ①앞 줄 끝이 `-아/어/여` 활용형(종성 없는 ㅏ/ㅓ/ㅐ/ㅕ 계열)
# ②줄 첫머리가 아래 보조용언 **활용형 목록**에 있음. 어간 접두 매칭은 `바다`+`가운데` 같은
# 오탐을 만들어서 안 쓴다 — 닫힌 목록이라 결정적이고 눈으로 검산된다.
_AUX_HEAD = frozenset(
    """
    가 가서 가고 가는 가며 가면 가면서 간다 간 갈 갑니다 갔다 갔습니다 가지 가야 가자
    와 와서 오는 오며 온다 온 올 옵니다 왔다 왔습니다 오고
    버려 버려서 버렸다 버렸습니다 버리는 버린 버릴 버립니다 버리고 버리자
    줘 줘서 주는 준다 준 줄 줍니다 줬다 주고 주세요 주십시오 주시오 주게 주자
    봐 봐서 보는 본다 본 볼 봅니다 봤다 보자 보라 보고 보시오
    둬 두는 둔다 둔 둘 뒀다 두고 두자
    놔 놓는다 놓은 놓을 놓았다 놓고
    있다 있는 있어 있어서 있었다 있습니다 있는데 있고 있을 있은
    진다 지는 진 질 졌다 져 져서
    댄다 대는 댔다 낸다 내는 냈다 내어 난다 나는 났다
    마 말아 마라 말자 말았다 말아라 말고
    싶다 싶은 싶어 싶습니다 싶었다 싶지
    드려 드립니다 드리는 드렸다
    치웠다 치운다 가지고 가진 가질
    """.split()
)
# ⚠ `ㅔ` 는 뺀다 — 활용 어미가 아니라 **조사 `에`** 가 압도적이라(`안에`·`곁에`) 오탐만 는다.
_AUX_TAIL_VOWELS = frozenset("ㅏㅓㅐㅕㅘㅙㅝ")
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"


def _is_infinitive(word: str) -> bool:
    """어절이 `-아/어/여` 활용형으로 끝나는가 — 뒤에 보조용언이 올 자리(당해·사·되어)."""
    ch = word.rstrip(".,!?…~ ")[-1:] or " "
    if not ("가" <= ch <= "힣"):
        return False
    code = ord(ch) - 0xAC00
    return code % 28 == 0 and _JUNG[(code // 28) % 21] in _AUX_TAIL_VOWELS

# 의존명사는 앞 용언 없이 못 선다 — 줄 첫머리에 오면 `너를 다시 만날` / `수 있을…` 처럼
# 한 덩어리가 갈린다(유저 QA 2026-08-04). 앞 줄로 **올려** 붙인다. `_pull_det_orphans` 의
# 거울상이고, 마찬가지로 재배치일 뿐이라 글자·줄 수·바이트 불변이다.
# ⚠ 판정은 **앞 줄 끝이 관형형 어미(ㄴ/ㄹ 받침)** 일 때만 — 그래야 의존명사가 확정된다.
# 그 조건이 없으면 `수(數)`·`때(垢)` 같은 자립명사를 잘못 끌어올린다.
_BOUND_NOUN = re.compile(
    r"(수|것|줄|때|뿐|적|바|터|듯|채|편|만큼|나름)(이|가|은|는|을|를|에|의|도|만|과|와|로|으로|이다|입니다)?[.,!?…]*$"
)


def _is_adnominal(word: str) -> bool:
    """어절이 관형형(…ㄴ/…ㄹ)으로 끝나는가 — 뒤에 의존명사가 올 자리."""
    ch = word[-1]
    if not ("가" <= ch <= "힣"):
        return False
    return (ord(ch) - 0xAC00) % 28 in (4, 8)  # 종성 ㄴ / ㄹ


def _pull_tail_orphans(pages, width, cell_width):
    """창의 **마지막 줄에 어절 하나만 남는 고아**를 없앤다 — 앞 줄의 끝 어절을 내려 붙인다.

    그리디 줄바꿈은 `…무찌를 날도 멀지` / `않았사옵니다.`처럼 서술어만 홀로 떨어뜨린다
    (유저 QA 2026-07-30). 앞 줄에서 한 어절을 내려 `…무찌를 날도` / `멀지 않았사옵니다.`로
    만든다. **재배치일 뿐이라 글자·줄 수·바이트 불변**(공백↔개행 자리만 바뀜, 메모리 중립).
    ⚠ 내린 뒤 폭을 넘거나 앞 줄이 한 어절만 남으면 이동하지 않는다."""
    for pg in pages:
        if len(pg) < 2:
            continue
        last, prev = pg[-1].split(), pg[-2].split()
        if len(last) != 1 or len(prev) < 2:
            continue
        if prev[-2] in _DET_ORPHAN:  # 내리면 지시관형사가 줄 끝 고아가 된다 — 그대로 둔다
            continue
        # 앞 줄이 한 어절만 남을 땐, 그 어절이 짧으면 오히려 더 어색하다
        # (`폐하를` 홀로 = 나쁨 / `무찌르기에는` 홀로 = 무방). 4음절 이상만 허용.
        if len(prev) == 2 and len(prev[0]) < 4:
            continue
        cand = prev[-1] + " " + pg[-1]
        if text_width(cand, cell_width) <= width:
            pg[-2] = " ".join(prev[:-1])
            pg[-1] = cand
    return pages


def _pull_bound_nouns(pages, width, cell_width):
    """줄 첫머리 의존명사를 앞 줄로 올려 붙인다(앞 줄이 관형형으로 끝날 때만)."""
    for pg in pages:
        for i in range(1, len(pg)):
            words, prev = pg[i].split(), pg[i - 1].split()
            if len(words) < 2 or not prev:  # 올리면 그 줄이 비는 경우는 제외
                continue
            if not (_BOUND_NOUN.fullmatch(words[0]) and _is_adnominal(prev[-1])):
                continue
            cand = pg[i - 1] + " " + words[0]
            if text_width(cand, cell_width) <= width:
                pg[i - 1] = cand
                pg[i] = " ".join(words[1:])
    return pages


def _pull_det_orphans(pages, width, cell_width):
    for pg in pages:
        for i in range(len(pg) - 1):
            words = pg[i].split()
            if len(words) >= 2 and words[-1] in _DET_ORPHAN + _ADV_ORPHAN:
                cand = words[-1] + " " + pg[i + 1]
                if text_width(cand, cell_width) <= width:
                    pg[i] = " ".join(words[:-1])
                    pg[i + 1] = cand
    return pages


def _pull_auxiliary(pages, width, cell_width):
    """본용언(`-아/어`)과 보조용언 사이의 줄바꿈을 없앤다 — 붙는 쪽으로 한 어절 옮긴다.

    ①보조용언을 앞 줄로 **올리고**, 폭이 모자라면 ②본용언을 다음 줄로 **내린다**.
    둘 다 재배치일 뿐이라 글자·줄 수·바이트 불변(다른 `_pull_*` 과 같은 규약).
    ⚠ 앞 줄이 문장부호(`.!?`)로 끝나면 문장 경계라 손대지 않는다 — 다음 문장의 첫 어절이
    우연히 보조용언 꼴일 수 있다(`…했다.` / `보자` 는 붙이면 안 된다).
    ⚠ **옮겨서 새 위반이 생기면 안 옮긴다.** 판정이 `주어+서술어`(`해가` + `져`)도 물기 때문에,
    그대로 밀면 진짜 짝을 갈라 놓는다 — `해가` / `져 버릴 거야` 가 `해가 져` / `버릴 거야` 로
    악화됐다(2026-08-09 검토표에서 잡았다). 이동 후 경계를 같은 규칙으로 다시 본다."""

    def splits(a, b):
        """어절 a 다음에 줄이 갈리면 보조용언 짝이 끊기는가."""
        if a[-1] in ".!?…":  # 문장 경계
            return False
        b = b.rstrip(".,!?…")
        if _is_infinitive(a) and b in _AUX_HEAD:
            return True
        # `-지 못하다/않다/말다` — `국경의 동굴로 가지` / `못했다고` 처럼 부정이 뒤늦게 온다.
        return len(a) >= 2 and a.endswith("지") and (b[:1] in ("못", "않") or b[:1] == "마")

    for pg in pages:
        for i in range(1, len(pg)):
            prev, words = pg[i - 1].split(), pg[i].split()
            if not prev or not words or not splits(prev[-1], words[0]):
                continue
            if len(words) > 1 and not splits(words[0], words[1]):  # ① 보조용언을 위로
                cand = pg[i - 1] + " " + words[0]
                if text_width(cand, cell_width) <= width:
                    pg[i - 1], pg[i] = cand, " ".join(words[1:])
                    continue
            if len(prev) > 1 and not splits(prev[-2], prev[-1]):  # ② 본용언을 아래로
                cand = prev[-1] + " " + pg[i]
                if text_width(cand, cell_width) <= width:
                    pg[i - 1], pg[i] = " ".join(prev[:-1]), cand
    return pages
