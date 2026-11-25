"""조판 축 전수 게이트 — 실제로 굽는 글(`Typesetter` 결과 = 빌드와 같은 길)을 **전 대사·전 전투·시스템 문안**에서 축별로 센다(마스터 10-31 「조판검사할 때
첫칸공백, 고아부호, 빈줄개행, 여러창일 때 균등한 문장 분배(마지막 창에 한 어절만 남으면 안 됨) 등등」).

    .venv/bin/python games/sfc-ed1/tools/check_typeset_axes.py

축(번역 규칙):
  2-5 첫 칸 공백 · 2-3 고아 부호 · 2-4 빈 줄 개행 · 2-1 부호 뒤 공백 · 2-6 낱말 속 접힘 · 넘침(8px 글자가 줄 끝에 걸침) · 2-16③ 마지막 창 한 어절(h) · 원문 창 내용 보존·창 수(창이동·창수, 규칙 2-17 — 창 줄 수 고르기 h2 는 안 쓴다)
  + 쪽 끝 한 어절 고아(a)·문장 중간 한 낱말로 끝나는 쪽(b, 2-16 ③) → 전부 0 이어야 한다. 원판도 그 쪽 마지막 줄이 한 낱말이면(원판 동일 — 문장 끝 짧은 어절) 뺀다.
이미 있는 지표(`typeset.check_all` 의 ②④⑤ · `typeset.window_issues` · `linemetrics.orphan_pages`)를 그대로 쓰고, 전 영역으로 넓혔다(`linemetrics` 는 씬만 본다).
**양성 대조**: 축마다 일부러 틀린 글을 먹여 센다 — 0 을 「안 쟀다」와 가른다(못 세면 실패).
예외(조건): 고아 부호는 원판도 부호만 있는 줄(「!?」 한 마디)이면 허용. 첫 칸 공백은 네이티브 호출(`<EE:…>`) 바로 뒤(호출이 찍는 값 뒤 띄움)와 원판 줄이 전각 들임으로 시작하는 서명 줄만 허용한다.
"""

import argparse
import re
import sys

import common
import linemetrics
import places
import typeset

ZERO = ("첫칸공백", "고아부호", "빈줄", "부호뒤공백", "부호앞공백", "낱말속접힘", "넘침", "h", "창이동", "창수", "보상줄", "색불일치", "색낱말속", "a", "b", "가운데", "한줄문장", "쉼표", "창높이")
_TOK = re.compile(r"\{[^}]*\}")
_BREAKS_KR = re.compile(r"<FF>|<EF>|<FE>|<E0>")
_BREAKS_JP = re.compile(r"<PAGE>|<CLEAR>|<RETURN>|<END>")
# 색 틀을 **의도해서** 원판에 없던 곳에 넣은 조각(마스터 10-29 대사 색 코드 점검, status.md) — 이 셋만 색 수가 원판보다 하나 많다
COLOR_ADDED = {"2ba4af7baf5e", "c16cd84215d3", "e3c9fd21a292"}
_REWARD = ("포인트 획득", "Gold를 얻었", "해치웠다.")


def _fragments(res: str) -> list[list[str]]:
    """쪽·호출 조각마다 줄 목록 — 제어 코드를 걷되 네이티브 호출(`<EE:…>`)은 표지 글자(\\x02)로 남긴다."""
    out = []
    for part in typeset._PAGE_SPLIT.split(res):
        if part in ("<FF>", "<EF>", "<FE>", "<E0>"):
            continue
        part = typeset._HEADER.sub("", part)
        part = re.sub(r"<EE:[0-9A-Fa-f]+>", "\x02", part)
        out.append(typeset._CTRL_TOK.sub("", part).split("\n"))
    return out


def axes_of(res: str, jp: str = "") -> dict[str, list[str]]:
    """글 한 조각의 축별 위반 — {축: [예…]}. 조판이 낸 줄(`res`)만 본다(런타임 칸 배열 시뮬레이션은 `layout` 쪽에서 센다)."""
    found: dict[str, list[str]] = {k: [] for k in ("첫칸공백", "고아부호", "빈줄", "부호뒤공백", "부호앞공백")}
    indent_ok = bool(re.search(r"(^|\n)\u3000\u3000", jp))
    punct_ok = bool(re.search(r"(^|\n)[！？!?、。…]", jp))  # 원판도 부호만 있는 줄(놀람 한 마디)
    for lines in _fragments(res):
        for i, ln in enumerate(lines):
            if ln.startswith(" ") and not (indent_ok and ln.startswith("  ")):
                found["첫칸공백"].append(ln[:16])
            if ln and ln[0] in ".,!?" and not (punct_ok and not re.search(r"[가-힣A-Za-z0-9X]", ln)):
                found["고아부호"].append(ln[:16])
            if i and not ln.strip() and i < len(lines) - 1 and lines[i - 1].strip():
                found["빈줄"].append(" / ".join(x[:8] for x in lines[i - 1 : i + 2]))
    flat = _TOK.sub("X", typeset._CTRL_TOK.sub("\n", res))
    found["부호뒤공백"] += [flat[max(0, m.start() - 6) : m.end() + 4] for m in re.finditer(r"[,.!?][가-힣A-Za-z]", flat)]
    found["부호앞공백"] += [flat[max(0, m.start() - 6) : m.end() + 3] for m in re.finditer(r"[가-힣A-Za-z0-9] +[,.!?]", flat)]
    return found


def color_axes(kr: str, jp: str, sid: str = "") -> dict[str, list[str]]:
    """4-6 색 — 조각을 쪽 단위로 맞춰(`<FF>`↔`<PAGE>` …) 색 열기·닫기 수가 원판과 같은가, 색이 낱말 한가운데서 열리지 않는가(원판도 그러면 허용)."""
    out: dict[str, list[str]] = {"색불일치": [], "색낱말속": []}
    K, J = _BREAKS_KR.split(kr), _BREAKS_JP.split(jp)
    if len(K) != len(J):
        out["색불일치"].append(f"쪽 수 {len(K)}↔{len(J)}")
        return out
    for i, (a, b) in enumerate(zip(K, J)):
        k = (len(re.findall(r"<E[23]>", a)), len(re.findall(r"<E1>", a)))
        j = (len(re.findall(r"<COLOR_[C4]>", b)), len(re.findall(r"<COLOR_POP>", b)))
        if k != j and sid not in COLOR_ADDED:
            out["색불일치"].append(f"쪽{i} 우리 열기·닫기 {k} ↔ 원판 {j}")
    mid = lambda t, tag: [  # noqa: E731 — 색 여는 코드 바로 앞이 글자(공백·줄머리·다른 코드 아님)인 자리 수
        1 for m in re.finditer(tag, t) if re.match(r"[가-힣A-Za-z0-9]", re.sub(r"<[^>]*>|\{[^}]*\}", "", t[: m.start()])[-1:]) and not re.search(r"(\n|>|\}| )$", t[: m.start()])
    ]
    if len(mid(kr, r"<E[23]>")) > len(mid(jp, r"<COLOR_[C4]>")):
        out["색낱말속"].append("낱말 한가운데서 색이 열린다")
    return out


def _fixable(res: str, ts: "typeset.Typesetter") -> bool:
    """구운 글의 쪽 가운데 객관 결함(고아·나쁜 끊김·명사구 갈림)이 있고 줄 나눔 전수 탐색(`typeset._dp_page`)으로 더 줄일 수 있는 쪽이 있나 — 있으면 조판기가 못 고친 것(센다)."""
    for part in typeset._PAGE_SPLIT.split(res):
        if part in ("<FF>", "<EF>", "<FE>", "<E0>") or not part.strip():
            continue
        o = typeset._obj(part)
        dp = typeset._dp_page(part, ts.dm, ts.ml, o) if o else None
        bad = lambda t: sum(1 for a, b in typeset.break_pairs(t) if typeset._bad_break(a, b))  # noqa: E731
        if dp is not None and bad(dp) <= bad(part):  # 고아를 없애려고 나쁜 끊김을 새로 만드는 배치는 고친 게 아니다(조판기 정책 — 고아 ↔ 나쁜 끊김 교환은 안 받는다)
            return True
    return False


def reward_axes(res: str, reg: str) -> list[str]:
    """2-9 전투 보상 문구는 새 줄에서 시작 — 전투 보상 조각(해치웠다·EP 획득·Gold 획득)은 개행으로 시작한다."""
    if reg != "전투·시스템" or not any(w in res for w in _REWARD):
        return []
    return [] if res.startswith("\n") or res.startswith("<E3>") else [res[:20]]


def _jp_last_words(jp: str) -> list[int | None]:
    """원판 조각의 쪽(`<PAGE>`·`<CLEAR>`·`<RETURN>`·`<END>` 로 나눔)마다 마지막 글줄의 낱말 수(전각 공백 `\\u3000` 기준, 색 머리 줄 제외). 글이 없는 쪽은 None."""
    out: list[int | None] = []
    for part in _BREAKS_JP.split(jp):
        part = re.sub(r"<COLOR_[C4]>.*?<COLOR_POP>\n?", "", part, flags=re.S)
        ls = [x for x in (re.sub(r"<[^>]*>", "", ln) for ln in part.split("\n")) if x.strip()]
        out.append(len([w for w in re.split("\u3000| ", ls[-1]) if w]) if ls else None)
    return out


def orphan_axes(res: str, jp: str) -> tuple[list[str], list[str]]:
    """(a 쪽 끝 한 어절 고아, b 그중 문장 중간) — **원판도 그 쪽의 마지막 줄이 한 낱말이면 뺀다**(원판 동일 — 우리가 만든 고아가 아니다).
    쪽 대응은 `<FF>` 류 ↔ `<PAGE>` 류 개수가 같을 때만 쓴다(안 맞으면 뺄 근거가 없으니 센다)."""
    a, b = [], []
    jw = _jp_last_words(jp)
    parts = _BREAKS_KR.split(res)
    mapped = len(jw) == len(parts)
    for pi, part in enumerate(parts):
        rows = typeset.page_rows(part) if part.strip() else []
        if not rows:
            continue
        lines = rows[-1]
        last = lines[-1]
        if len(last) != 1 or not linemetrics._HANGUL.search(last[0]) or len(lines) < 2:
            continue
        if mapped and jw[pi] == 1:
            continue
        if "{D5:" in last[0]:  # 사전 문장 토큰은 런타임에 여러 어절로 펴진다 — 한 어절이 아니다
            continue
        sample = " / ".join(" ".join(w) for w in lines[-2:])
        a.append(sample)
        if not linemetrics._sentence_end(last[0]):
            b.append(sample)
    return a, b


def window_axes(kr: str, res: str, jp: str) -> list[str]:
    """여러 창(쪽) 대사는 창마다 원문 창의 내용을 그대로 둔다(규칙 2-17, 마스터 10-31) — 번역 원고의 창 경계(`<FF>` 류)와 구운 글의 창 경계를 대조.
    예외는 마지막 창에 고아 어절 하나만 남은 경우의 한 줄 이동(`_window_move`)뿐. 원판 창 수(`<PAGE>` 류)와도 같아야 한다."""
    out = []
    norm = lambda t: re.sub(r"<[^>]*>|\s", "", t)  # noqa: E731
    ks, rs = _BREAKS_KR.split(kr), _BREAKS_KR.split(res)
    if len(_BREAKS_JP.split(jp)) != len(rs):
        out.append(f"창 수 원판 {len(_BREAKS_JP.split(jp))} ↔ 구운 {len(rs)}")
    if len(ks) != len(rs):
        out.append(f"창 수 원고 {len(ks)} ↔ 구운 {len(rs)}")
    elif [norm(x) for x in ks] != [norm(x) for x in rs]:
        diff = [i for i, (x, y) in enumerate(zip(ks, rs, strict=True)) if norm(x) != norm(y)]
        last = max((i for i, x in enumerate(ks) if x.strip()), default=0)  # `<E0>` 뒤 빈 꼬리는 창이 아니다
        tail_orphan = last >= 1 and len(re.sub(r"<[^>]*>", "", ks[last]).split()) == 1 and bool(diff) and set(diff) <= {last - 1, last}
        if not tail_orphan:
            out.append(f"원문 창 내용 이동 창 {diff}")
    return out


_JP_BREAK = re.compile(r"<(?:PAGE|CLEAR|RETURN|END)>")
_END_PUNCT_W = ".,…!?"


def _ink_px(line: str) -> int:
    """줄의 글 폭(px) — **줄 끝 문장부호(`.` `,` `…`)는 뺀다**(규칙 2-8, 마스터 10-13)."""
    return typeset.px(line.rstrip(_END_PUNCT_W + " "))


def _centered_jp(jp: str) -> list[tuple[str, int]]:
    """원판의 가운데 맞춘 줄 [(어디에 맞췄나 'f'=창 한 줄 폭 · 'p'=윗줄 폭, 윗줄이 있으면 그 폭)] — 전각 공백 둘 이상으로 들여쓴 글(토큰 없음)이 한 칸(8px) 안에서 가운데인 줄.
    들여쓴 줄 가운데 서명 줄(`{…}` 이름 토큰)은 폭을 모르니 안 센다."""
    out = []
    for part in _JP_BREAK.split(jp.replace("<@>", "")):
        lines = part.split("\n")
        for i, ln in enumerate(lines):
            if "{" in ln or "<" in ln or not ln.startswith("\u3000\u3000") or not ln.strip("\u3000"):
                continue
            lead = len(ln) - len(ln.lstrip("\u3000"))
            w = 8 * len(ln.strip("\u3000"))
            prev = lines[i - 1] if i else ""
            fields = [("f", typeset.LINE_PX)]
            if prev.strip() and "{" not in prev and "<" not in prev:
                fields.append(("p", 8 * len(prev)))
            for kind, field in fields:
                if abs(8 * lead - (field - 8 * lead - w)) <= 8:
                    out.append((kind, i))
                    break
    return out


def center_axes(res: str, jp: str) -> list[str]:
    """2-8 가운데 정렬 — 원판에서 가운데 맞춘 줄(장 클리어 카드 등)은 우리 글도 **실제 픽셀 폭**으로 가운데여야 한다(줄 끝 `.` `,` `…` 는 폭에서 뺌, 좌우 여백 차 1px 이하).
    원판 줄과 우리 들여쓴 줄을 차례로 짝지어 맞춘 자리(창 폭 · 윗줄 폭)대로 잰다. 우리 쪽에 들여쓴 줄이 모자라도 위반이다."""
    want = _centered_jp(jp)
    if not want:
        return []
    mine = []
    for part in _BREAKS_KR.split(res.replace("<@>", "")):
        lines = typeset._CTRL_TOK.sub("", part).split("\n")
        for i, ln in enumerate(lines):
            if ln.startswith("  ") and "{" not in ln and ln.strip():
                mine.append((ln, lines[i - 1] if i else ""))
    out = []
    if len(mine) < len(want):
        out.append(f"가운데 줄 소실 원판 {len(want)} ↔ 우리 {len(mine)}")
    for (kind, _i), (ln, prev) in zip(want, mine, strict=False):
        field = typeset.LINE_PX if kind == "f" or not prev.strip() or "{" in prev else typeset.px(prev.rstrip(_END_PUNCT_W + " "))
        left = typeset.px(ln[: len(ln) - len(ln.lstrip(" "))])
        w = _ink_px(ln.lstrip(" "))
        if abs(left - (field - left - w)) > 1:
            out.append(f"좌 {left}px · 우 {field - left - w}px — {ln.strip()[:12]}")
    return out


_JOSA_TOPIC = ("은", "는")
_ADV_JOSA = ("에는", "에서는", "으로는", "로는", "에게는", "께서는", "에도", "에서도")
_CONN_COMMA = ("하고", "고", "하며", "으며", "며", "서")  # `-서,` 는 11-03 규칙 2-13 ⑪
_QUOTE_CONN = ("라고", "다고", "자고", "냐고", "느냐고", "이라고")


def _syllables(w: str) -> int:
    """읽는 소리대로 센 음절 수(한글만 — 숫자·영문은 근사로 글자 수, 규칙 2-13 ⑨)."""
    return sum(1 for c in w if "가" <= c <= "힣")


def comma_candidates(kr: str) -> tuple[list[str], list[str]]:
    """2-13 쉼표 — (명백한 「뺀다」, 애매한 「뺀다」 후보). 번역 원고(`kr`)의 쉼표 어절을 규칙 행의 **뺀다** 부류에 견준다.
    명백한: 규칙 예시와 꼴이 같은 것 — 주어·주제 뒤(`파렌 왕국은,` — 앞 절이 짧은 은/는+쉼표) · 부사어 뒤(`처음에는,` — 에는·로는 …) · 짧은 연결 어미 뒤(`~하고,` `~받으며,` — 앞 절 11음절 이하).
    애매한: 은/는 인데 군말·부사(`실은,`)로 읽히거나 앞 절이 길어 남길 만한 것, 관형형 뒤. 런타임 변수 토큰(`{D6}`~`{DD}`)이 든 절은 음절을 몰라 애매한 쪽이다(사전 토큰은 펼쳐서 센다). 한 어절 쉼표(부르는 말·감탄·응답)와 따옴표 안 연결(`~라고,`)은 남기는 부류라 안 센다."""
    sure, maybe = [], []
    flat = typeset._CTRL_TOK.sub(" ", typeset._HEADER.sub(" ", typeset.expand_static(kr)))  # 사전 토큰은 펼쳐서(음절·어절을 안다) · 화자 머리 줄은 절이 아니다
    ws = flat.split()
    for i, w in enumerate(ws):
        if not w.endswith(",") or len(w) < 3:
            continue
        stem = w[:-1]
        j = i
        while j > 0 and not re.search(r"[.!?…,」]$", ws[j - 1]):
            j -= 1
        clause = ws[j : i + 1]
        if i + 1 >= len(ws):
            continue  # 글 끝 쉼표는 이 규칙 대상이 아니다
        ctx = " ".join(clause) + " | " + " ".join(ws[i + 1 : i + 3])
        tok = any("{" in c for c in clause)  # 펼쳐도 남은 건 런타임 변수(`{D6}`…) — 음절을 모른다
        syl = _syllables(" ".join(clause))
        if stem.endswith(_ADV_JOSA) and not tok:  # 부사어 뒤는 한 어절이어도 뺀다(`처음에는,`)
            sure.append(ctx)
        elif stem == "그럼" and clause[0] == w or stem == "그럼" and clause[-2:-1] == ["자"]:  # ⑩ 문장 앞 접속 — 부르는 말 앞(`그럼, 왕자님.`)·작별(`그럼, 몸조리 …`)은 남긴다
            nxt = ws[i + 1]
            if not (re.search(r"님[.!?,]?$", nxt) or nxt.startswith(("몸조리", "안녕"))):
                sure.append(ctx)
        elif len(clause) == 1:
            continue  # 한 어절(부르는 말·감탄·응답·군말)은 남기는 부류
        elif stem.endswith(_JOSA_TOPIC):
            (sure if len(clause) <= 4 and not tok and syl >= 5 and not stem.endswith(("실은",)) else maybe).append(ctx)
        elif stem.endswith(_CONN_COMMA) and not stem.endswith(_QUOTE_CONN):
            idiom = stem == "그렇고" or "말고" in ctx.split("|")[0]  # 「그건 그렇고,」 화제 전환(말머리 군말 ⑦) · 「~지 말고, ~려면」 짝을 이룬 두 구(⑤)는 남긴다
            (sure if not tok and syl <= 11 and len(clause) >= 2 and not idiom else maybe).append(ctx)
    return sure, maybe


def rows_axes(res: str) -> tuple[list[str], list[str]]:
    """2-10 창 높이 — (4줄을 넘는데 어절을 안 쪼개고 4줄 안에 담을 수 있는 쪽 · 폭상 불가피한 쪽). 분기 코드 든 쪽은 갈래가 한 쪽에 겹쳐 세지 못하니 뺀다.
    문장 단위 줄바꿈 탓에 한 창에 들어갈 글이 다음 줄(쪽)로 넘치면 안 된다(마스터 11-05). 화자 줄(`{D0:80~84}`)은 창 한 줄로 센다."""
    fit, tight = [], []
    for part in typeset._PAGE_SPLIT.split(res):
        if part in ("<FF>", "<EF>", "<FE>", "<E0>") or not part.strip() or not typeset._rows_over(part):
            continue
        body = re.sub(r"^(?:<E3>[^\n<]*\n?<E1>)", "", part)
        lines = [ln for ln in (re.sub(r"<[^>]*>", "", x).strip() for x in body.split("\n")) if ln]
        tag = sum(1 for ln in lines if typeset._TAGLINE.fullmatch(ln))
        rows, cur = 1, 0
        for w in (w for ln in lines if not typeset._TAGLINE.fullmatch(ln) for w in ln.split(" ")):  # 어절은 안 쪼갠다(사전 토큰은 펼쳐도 한 덩이)
            wpx = typeset.px(typeset.expand_static(w))
            add = wpx if cur == 0 else typeset.px(" ") + wpx
            if cur + add > typeset.LINE_PX and cur:
                rows, cur = rows + 1, wpx
            else:
                cur += add
        (fit if rows + tag <= typeset._WINDOW_ROWS else tight).append(" / ".join(x[:12] for x in lines)[:60])
    return fit, tight


def oneline_axes(res: str) -> list[str]:
    """2-10 한 줄 문장 — 조판 결과에 같은 변환(`typeset.one_line_sentences`)을 다시 걸어 바뀌는 쪽(= 아직 한 줄로 못 묶은, 줄을 늘리지 않고 묶을 수 있는 문장)."""
    out = []
    for part in typeset._PAGE_SPLIT.split(res):
        if part in ("<FF>", "<EF>", "<FE>", "<E0>") or not part.strip():
            continue
        fixed = typeset.one_line_sentences(part)
        if fixed != part:
            out.append(" / ".join(x[:14] for x in part.split("\n") if x.strip())[:60])
    return out


def oneline_left(res: str) -> list[str]:
    """2-10 남김 — 한 줄에 들어가는데 두 줄에 걸친 문장 가운데 조판기가 못 묶은 것(줄이 창 높이를 넘거나 · 뒤 글이 길어 쪽 끝 고아가 생기거나 · 줄 가운데 제어 코드가 낀 것). 조판기와 같은 문장 검출(`_sentence_spans`)을 쓴다."""
    out = []
    for part in typeset._PAGE_SPLIT.split(res):
        if part in ("<FF>", "<EF>", "<FE>", "<E0>") or not part.strip():
            continue
        lines = part.split("\n")
        for f, wf, k, wk in typeset._sentence_spans(lines):
            sent = lines[f].split(" ")[wf:] + [w for ln in lines[f + 1 : k] for w in ln.split(" ")] + lines[k].split(" ")[: wk + 1]
            if typeset.px(typeset._CTRL_TOK.sub("", typeset.expand_static(" ".join(sent)))) <= typeset.LINE_PX:
                out.append(" ".join(sent)[:30])
    return out


def _skewed_place() -> bool:
    """음성 대조 — 앞 빈칸 0·뒤 빈칸 큼(왼쪽으로 쏠린 지명)은 센다."""
    real = places.pad_cells
    places.pad_cells = lambda kr: (0, 10 - len(kr))
    try:
        return bool(place_center_axes(["가나"]))
    finally:
        places.pad_cells = real


def selftest() -> list[str]:
    """양성 대조 — 축마다 틀린 글을 먹여 센다. 못 세는 축 이름 목록(비어야 정상)."""
    bad = axes_of(" 가나다\n,라마\n가\n\n바사\n자,차", "")
    bad["부호앞공백"] = bad["부호앞공백"] or axes_of("가나 ,다")["부호앞공백"]
    miss = [k for k in ("첫칸공백", "고아부호", "빈줄", "부호뒤공백", "부호앞공백") if not bad[k]]
    ca = color_axes("<E3>가<E1>나<FF>다", "<COLOR_C>가<COLOR_POP>나<PAGE><COLOR_C>다<COLOR_POP>")
    miss += [f"{k}(색 양성)" for k in ("색불일치",) if not ca[k]]
    if not color_axes("가나<E3>다<E1>", "가나 <COLOR_C>다<COLOR_POP>")["색낱말속"]:
        miss.append("색낱말속")
    if color_axes("<E3>가<E1>", "<COLOR_C>가<COLOR_POP>")["색불일치"]:
        miss.append("색 거짓 양성")
    if not reward_axes("해치웠다.", "전투·시스템") or reward_axes("\n해치웠다.", "전투·시스템"):
        miss.append("보상줄")
    if not rows_axes("가나다 라마\n바사\n아자\n차카\n타파\n")[0] and not rows_axes("가나다 라마\n바사\n아자\n차카\n타파\n")[1]:
        miss.append("창높이")
    if place_center_axes(["가나"]) or place_center_axes(["가나다라"]) or not _skewed_place():
        miss.append("지명 가운데")
    cj = "가나다\n\u3000\u3000\u3000\u3000\u3000\u3000\u3000가나다라"  # 원판은 창 한 줄 폭 안에서 가운데(앞 7칸 · 뒤 6칸)
    if not center_axes("가나다\n가나다", cj) or center_axes("가나다\n" + " " * 14 + "가나다", cj):
        miss.append("가운데")
    if not comma_candidates("파렌 왕국은, 가난한 나라였다.")[0] or not comma_candidates("처음에는, 평화로웠다.")[0] or not comma_candidates("문을 열고, 밖으로 나갔다.")[0]:
        miss.append("쉼표")
    if not comma_candidates("그럼, 하루라도 빨리 오시오.")[0] or comma_candidates("그럼, 왕자님.")[0] or not comma_candidates("통에 칼을 꽂아서, 인형이 튄다.")[0]:
        miss.append("쉼표(⑩ 그럼 · ⑪ -서)")
    if comma_candidates("아트라스, 어서 와라.")[0] or comma_candidates("그래, 알았다.")[0] or comma_candidates("란도, 플로라, 모두 모였다.")[0]:
        miss.append("쉼표(거짓 양성)")
    if not oneline_axes("그러자. 저희는\n당연한 일을 했을 뿐입니다.\n") or oneline_axes("그러자.\n저희는 당연한 일을 했을 뿐입니다.\n"):
        miss.append("한줄문장")
    # 사전 토큰 펼침 — 토큰 줄도 센다(양성) · 런타임 변수 토큰 든 문장은 폭을 모르니 건드리지 않는다(음성)
    if typeset.expand_static("{D5:29}") != "나타났다." or typeset.expand_static("{D5:2D}{을/를}") != "주문을":
        miss.append("토큰 펼침")
    if not oneline_axes("어머!! 이것 참,\n과연 {D0:46}이시군요.\n") or oneline_axes("어머!! 이것 참,\n과연 {D6}이시군요.\n"):
        miss.append("한줄문장(토큰)")
    if not orphan_axes(typeset.expand_static("가나다 라마바 사아자\n{D5:29}"), "")[0]:
        miss.append("a(토큰)")
    ok = axes_of("<EE:A3FD05> 가나다\n가나다\n라마.", "")  # 호출 뒤 띄움은 통과해야 한다
    miss += [f"{k}(거짓 양성)" for k, v in ok.items() if v]
    if not window_axes("가나 다라\n<FF>마바 사아\n<E0>", "가나\n<FF>다라 마바 사아\n<E0>", "a<PAGE>b<END>") or window_axes("가나 다라\n<FF>마바 사아\n<E0>", "가나 다라\n<FF>마바 사아\n<E0>", "a<PAGE>b<END>"):
        miss.append("창이동")
    # 창 수 「적음」(원문 두 창을 한 창에 합침) — 구운 쪽이 원판보다 적어도, 원고보다 적어도 창수 축이 잡아야 한다(규칙 2-17, 관리자 11-05)
    if not any("원판" in x for x in window_axes("가나\n<FF>다라\n<E0>", "가나 다라\n<E0>", "a<PAGE>b<END>")) or not any("원고" in x for x in window_axes("가나\n<FF>다라\n<E0>", "가나 다라\n<E0>", "a<E0>")):
        miss.append("창수(적음)")
    if window_axes("가나 다라\n마바 사아\n자차 카타\n<FF>파하\n<E0>", "가나 다라\n마바 사아\n<FF>자차 카타\n파하\n<E0>", "a<PAGE>b<END>"):
        miss.append("창이동(고아 예외)")
    if not typeset.window_issues("가나 다라\n마바 사아\n<FF>파하.\n<E0>")[0]:
        miss.append("h")
    if not linemetrics.orphan_pages("가나 다라 마바\n사아\n")[0] or linemetrics.orphan_pages("가나 다라 마바\n사아 자차\n")[0]:
        miss.append("a")
    if not any("묶음 끊김" in b for b in typeset.layout(typeset.expand("가" * 20 + " 나", {}, {}))[1]):
        miss.append("낱말속접힘")
    lines, bad_l = typeset.layout(typeset.expand("가\n\n나", {}, {}))
    if not any("빈 줄" in b for b in bad_l):
        miss.append("layout 빈줄")
    _l, bad_l = typeset.layout(typeset.expand("\n가", {}, {}))
    if not any("쪽 첫머리 개행" in b for b in bad_l):
        miss.append("layout 쪽첫머리개행")
    return miss


EXPANDED = [0]  # 사전 토큰을 펼쳐 다시 센 조각 수
INFO: dict[str, list[str]] = {"쉼표 애매": [], "한줄문장 남김": [], "쪽끝고아 남김(사전 토큰)": [], "창높이 넘김(폭상 불가피)": []}  # 고치지 않고 부류·수로 남기는 것(2-13 애매 · 2-10 줄 늘림·고아 때문에 못 묶은 것)


CELL_PX = 8  # 지명 칸 폭(8px 고정)


def place_center_axes(names: list[str]) -> list[str]:
    """2-8 지명 입장 배너·HUD 지명(같은 표) — 10칸 안 가운데 정렬. 앞뒤 빈칸 차이는 한 칸(= 반 칸 4px 쏠림)까지만 허용(칸 단위 한계)."""
    out = []
    for kr in names:
        left, right = places.pad_cells(kr)
        if left < 0 or abs(right - left) * CELL_PX // 2 > CELL_PX // 2:
            out.append(f"{kr} — 앞 {left}칸 · 뒤 {right}칸 (쏠림 {abs(right - left) * CELL_PX // 2}px)")
    return out


def measure() -> tuple[dict[str, dict[str, int]], dict[str, list[str]]]:
    ts = typeset.Typesetter()
    rep = typeset.check_all()
    lay = {r["id"]: r for r in rep}
    cnt: dict[str, dict[str, int]] = {}
    ex: dict[str, list[str]] = {}

    def add(reg: str, axis: str, item: str) -> None:
        cnt.setdefault(axis, {}).setdefault(reg, 0)
        cnt[axis][reg] += 1
        ex.setdefault(axis, []).append(item)

    for it in typeset.targets():
        reg = typeset.region(it["addr"])
        res = ts(it["kr"], it["addr"])
        for axis, items in axes_of(res, it["jp"]).items():
            for x in items:
                add(reg, axis, f"{it['id']} {x}")
        for axis, items in color_axes(it["kr"], it["jp"], it["id"]).items():
            for x in items:
                add(reg, axis, f"{it['id']} {x}")
        for x in reward_axes(res, reg):
            add(reg, "보상줄", f"{it['id']} {x}")
        h, _h2 = typeset.window_issues(res)
        for x in window_axes(it["kr"], res, it["jp"]):
            add(reg, "창이동" if "내용" in x else "창수", f"{it['id']} {x}")
        for x in center_axes(res, it["jp"]):
            add(reg, "가운데", f"{it['id']} {x}")
        for x in oneline_axes(res):
            add(reg, "한줄문장", f"{it['id']} {x}")
        rf, rt = rows_axes(res)
        for x in rf:
            add(reg, "창높이", f"{it['id']} {x}")
        for x in rt:
            INFO["창높이 넘김(폭상 불가피)"].append(f"{it['id']} {x}")
        sure, maybe = comma_candidates(it["kr"])
        for x in sure:
            add(reg, "쉼표", f"{it['id']} {x}")
        for x in maybe:
            INFO["쉼표 애매"].append(f"{it['id']} {x}")
        for x in oneline_left(res):
            INFO["한줄문장 남김"].append(f"{it['id']} {x}")
        a, b = orphan_axes(res, it["jp"])
        if (a or b) and "{" in res and not _fixable(res, ts):  # 사전 토큰 든 쪽의 고아 — 줄 나눔 전수 탐색으로도 더 나쁜 끊김 없이는 못 고치면(폭 때문) 목록으로 남긴다
            INFO["쪽끝고아 남김(사전 토큰)"] += [f"{it['id']} {x}" for x in a]
            a, b = [], []
        for axis, items in (("h", h), ("a", a), ("b", b)):
            for x in items:
                add(reg, axis, f"{it['id']} {x}")
        # 사전 토큰(`{D0:xx}`~`{D5:xx}`)·조사 토큰을 **펼친 글**로 줄 구조 축을 다시 센다 — 토큰 줄은 어절·폭을 몰라 위 축들이 건너뛰던 것(관리자 11-03). 엔진은 사전 문자열을 일반 글자처럼 찍는다.
        e = typeset.expand_static(res)
        if e != res:
            EXPANDED[0] += 1
            for axis, items in axes_of(e, it["jp"]).items():
                for x in items:
                    add(reg, axis, f"{it['id']} [펼침] {x}")
            ea, eb = orphan_axes(e, it["jp"])
            if (ea or eb) and not _fixable(res, ts):
                ea, eb = [], []  # 위에서 목록으로 센 같은 고아
            eh, _eh2 = typeset.window_issues(e)
            for axis, items in (("h", eh), ("a", ea), ("b", eb), ("가운데", center_axes(e, it["jp"]))):
                for x in items:
                    add(reg, axis, f"{it['id']} [펼침] {x}")
        w = lay.get(it["id"])
        for m in set(w["worst"][1] if w and w["worst"] else []):
            if m.startswith("②"):
                add(reg, "빈줄", f"{it['id']} {m}")
            elif m.startswith("④"):
                add(reg, "낱말속접힘", f"{it['id']} {m}")
            elif m.startswith("⑤"):
                add(reg, "넘침", f"{it['id']} {m}")
    for x in place_center_axes(places.texts()):
        add("지명", "가운데", x)
    INFO["지명 반 칸 쏠림(4px, 홀수 차)"] = [kr for kr in places.texts() if (lambda lr: lr[0] != lr[1])(places.pad_cells(kr))]
    return cnt, ex


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=5)
    args = ap.parse_args()
    miss = selftest()
    if miss:
        print(f"  ✗ 양성 대조 실패 — 못 세는 축: {miss}")
        return 1
    cnt, ex = measure()
    tot = {k: sum(cnt.get(k, {}).values()) for k in ZERO}
    print("  조판 축 전수(씬·전투·시스템) — " + " · ".join(f"{k} {tot[k]}" for k in ZERO) + " · 양성 대조 통과")
    print(f"  사전 토큰 펼침 — {EXPANDED[0]}조각을 펼친 글로 줄 구조 축을 다시 셌다")
    print("  남김(목록만) — " + " · ".join(f"{k} {len(v)}" for k, v in INFO.items()))
    fail = []
    for k in ZERO:
        if tot[k]:
            fail.append(f"{k} {tot[k]}")
            for x in ex[k][: args.show]:
                print(f"    ✗ [{k}] {x}")
    if fail:
        print(f"  ✗ 위반: {' · '.join(fail)}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
