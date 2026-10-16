"""토큰 자리 — 번역문의 제어·사전 토큰이 **원문과 같은 자리(글 앞/뒤)** 에 있는가, 그리고 어긋난 것을 옮기는 함수.

## 왜 있나 (2026-10-19)

번역 정본의 토큰 계약(`textmap.check_tokens`)은 「제어 토큰이 전부 같은 순서로 있는가」만 본다. `init_from_tm` 은 PS1 문안 뒤에 원문 토큰을
**전부 이어 붙여** 초안을 만들고 「자리는 사람이 옮긴다」고 했는데, 옮기지 않은 조각이 최종 롬에 그대로 나갔다(qa 검수 58조각 + 그 밖):
`물건이옵니다.감사합니다.`(문장 끝 사전 문장 `{D5:10}`) · `주지.세리오스`(화자표가 글 뒤) · 소니아 `사자로 왔습니다.`가 끝없이 되풀이(CALL_TBL·화자별 JUMP 가
글 뒤라 분기가 글을 지나 실행) · 분기(IF/JUMP/CALL)가 본문 뒤.

규칙: **원문에서 글(가나·한자·부호) 앞에 오는 토큰은 번역문에서도 글 앞에, 뒤에 오는 토큰은 글 뒤에** 있어야 한다. 이름표 `<COLOR_C>…<COLOR_POP>`(`<E3>…<E1>`)
안은 글로 세지 않는다. 사전 문장 `{D5:xx}` 는 글이다.
"""

import re

TOK = re.compile(r"\{[0-9A-F]{2}(?::[0-9A-F]{2})?\}|<[0-9A-F]{2}(?::[0-9A-F]+)?>|<@>")
JP_TOK = re.compile(r"<[^<>]*>|\{[^{}]*\}")
JOSA = re.compile(r"\{(?:은/는|이/가|을/를|와/과|으로/로|이라/라|이다/다|이/)\}")
BLANK = " \n　 "
PARTICLE_KR = re.compile(r"\s*(?:은|는|이|가|을|를|에게서?|한테서?|께서?|의|와|과|으로|로|에|도|만)\s*")


def _is_text_token(t: str) -> bool:
    return t.startswith("{D5")  # 사전 문장 — 글이다


PARTICLES = "はがをにのもへと"


def _gap_text(prev_raw: str | None, gap: str) -> bool:
    """토큰 사이 틈이 글인가 — 이름표·치환 토큰 바로 뒤의 조사 한 글자(「<D6>は」)는 번역문의 `{은/는}` 과 같은 것이라 글로 안 센다."""
    g = gap.strip(BLANK)
    if not g:
        return False
    if prev_raw is not None and (prev_raw == "<COLOR_POP>" or re.fullmatch(r"<D[0-9A-F]>", prev_raw)):
        if len(g) == 1 and g in PARTICLES:
            return False
    if prev_raw is not None and prev_raw.startswith("{") and len(g) == 1 and g in PARTICLES.replace("の", ""):
        return False  # 사전 낱말 뒤의 조사(「{ほのおのつえ}を」) — 「の」는 뒤 낱말을 꾸미는 말이라 글로 센다
    return True


def jp_info(jp: str, tokens: list[str]) -> list[dict] | None:
    """원문 토큰마다 {tok, before(글이 앞에 있나), after(글이 뒤에 있나), nl_after(바로 뒤 개행), nl_before(바로 앞 개행), next_dict}.
    토큰 수가 안 맞으면 None."""
    ms = list(JP_TOK.finditer(jp))
    if len(ms) != len(tokens):
        return None
    info: list[dict] = []
    seen = False
    header = False
    pos = 0
    prev_raw = None
    for m, t in zip(ms, tokens, strict=True):
        gap = jp[pos : m.start()]
        if not header and _gap_text(prev_raw, gap):
            seen = True
        raw = m.group()
        info.append({"tok": t, "before": seen, "start": m.start(), "end": m.end(), "raw": raw})
        if raw == "<COLOR_C>":
            header = True
        elif raw == "<COLOR_POP>":
            header = False
        elif _is_text_token(t) and not header:
            seen = True
        pos = m.end()
        prev_raw = raw
    # 글이 뒤에 있나
    tail_seen = False
    gaps_after = []
    for i in range(len(ms)):
        end = ms[i].end()
        nxt = ms[i + 1].start() if i + 1 < len(ms) else len(jp)
        gaps_after.append(jp[end:nxt])
    # 뒤에서부터: 이 토큰 뒤에 (이름표 밖) 글이 있나
    hdr_after = False
    after = [False] * len(ms)
    run = False
    for i in range(len(ms) - 1, -1, -1):
        after[i] = run
        raw = ms[i].group()
        # 뒤에서 보면 COLOR_POP 이 먼저 만난다 — 이름표 안쪽 글은 세지 않는다
        gap = gaps_after[i]
        if _gap_text(ms[i].group(), gap):
            run = run or not _in_header(jp, ms, i)
        if _is_text_token(tokens[i]) and not _in_header(jp, ms, i):
            run = True
    for i, d in enumerate(info):
        d["after"] = after[i]
        end = d["end"]
        d["nl_after"] = jp[end : end + 1] == "\n"
        d["nl_before"] = jp[max(0, d["start"] - 1) : d["start"]] == "\n"
        nxt = info[i + 1] if i + 1 < len(info) else None
        d["next_text_char"] = _in_text(jp, ms, i)
        _ = tail_seen, hdr_after
    return info


def _in_text(jp: str, ms: list, i: int) -> bool:
    """i 번째 사전 토큰이 글 속 낱말인가 — 바로 뒤(사전 토큰은 건너뛰고)에 개행·제어 토큰이 아니라 글이 이어지면 글 속이다."""
    k = i
    while True:
        end = ms[k].end()
        ch = jp[end : end + 1]
        if k + 1 < len(ms) and ms[k + 1].start() == end:
            raw = ms[k + 1].group()
            if raw.startswith("{") and not raw.startswith("{ご"):
                k += 1
                continue
            return False
        return ch not in ("", "\n", " ", "\u3000")


def _in_header(jp: str, ms: list, i: int) -> bool:
    """i 번째 토큰 **뒤쪽 틈**이 이름표 `<COLOR_C>…<COLOR_POP>` 안인가."""
    depth = False
    for k in range(i + 1):
        raw = ms[k].group()
        if raw == "<COLOR_C>":
            depth = True
        elif raw == "<COLOR_POP>":
            depth = False
    return depth


def split_kr(kr: str) -> list[tuple[str, str]]:
    """번역문 → [("t", 글), ("k", 토큰)…]. 조사 자리표시자는 글이다."""
    out: list[tuple[str, str]] = []
    pos = 0
    for m in TOK.finditer(kr):
        if m.start() > pos:
            out.append(("t", kr[pos : m.start()]))
        out.append(("k", m.group()))
        pos = m.end()
    if pos < len(kr):
        out.append(("t", kr[pos:]))
    return out


def kr_flags(els: list[tuple[str, str]]) -> list[bool]:
    """요소마다 「앞에 (이름표 밖) 글이 있나」."""
    flags = []
    seen = False
    header = False
    prev = ""
    for kind, s in els:
        flags.append(seen)
        if kind == "t":
            if not header and JOSA.sub("", s).strip(BLANK) and not (prev == "<E1>" and PARTICLE_KR.fullmatch(s)):
                seen = True
        elif s == "<E3>":
            header = True
        elif s == "<E1>":
            header = False
        elif _is_text_token(s) and not header:
            seen = True
        prev = s
    return flags


def align(els: list[tuple[str, str]], info: list[dict], fl: list[bool] | None = None) -> dict[int, int]:
    """KR 토큰 요소 인덱스 → 원문 토큰 인덱스. 제어 토큰은 순서대로, 사전·치환 토큰은 같은 것 중 아직 안 짝지은 첫째."""
    used: set[int] = set()
    out: dict[int, int] = {}
    cur = 0
    for ei, (kind, s) in enumerate(els):
        if kind != "k" or s == "<@>":
            continue
        if s.startswith("<"):
            for j in range(cur, len(info)):
                if info[j]["tok"] == s and j not in used:
                    out[ei] = j
                    used.add(j)
                    cur = j + 1
                    break
        else:
            cand = [j for j, d in enumerate(info) if d["tok"] == s and j not in used]
            if fl is not None:  # 같은 토큰이 여럿이면 글 앞/뒤가 같은 쪽을 먼저 짝짓는다
                cand.sort(key=lambda j: info[j]["before"] != fl[ei])
            if cand:
                out[ei] = cand[0]
                used.add(cand[0])
    return out


def problems(jp: str, kr: str, tokens: list[str], ps1: bool = False) -> list[str]:
    """어긋난 토큰 목록(`토큰:글앞|글뒤`). 비어 있으면 정상. `ps1`=PS1 문안을 끌어온 조각이면 글 끝 뒤에 매달린 사전 토큰(번역문이 이미 풀어 쓴 낱말·문장 덤프)도 센다."""
    info = jp_info(jp, tokens)
    if info is None:
        return []
    els = split_kr(kr)
    fl = kr_flags(els)
    al = align(els, info, fl)
    bad = []
    for ei, j in al.items():
        s = els[ei][1]
        if s.startswith("{") and (info[j]["next_text_char"] or info[j]["before"]):
            if ps1 and s.startswith("{D") and _literal_before(els, ei) and not _text_after(els, ei):
                bad.append(f"{s}:끝덤프")
            continue
        if info[j]["before"] != fl[ei]:
            bad.append(f"{s}:{'글앞' if not info[j]['before'] else '글뒤'}")
    if _add_nl(jp, kr, tokens, info) != kr:
        bad.append("개행")
    return bad


def fix(jp: str, kr: str, tokens: list[str], ps1: bool = True) -> str:
    """어긋난 토큰을 원문 자리로 옮긴다. 옮기는 규칙:
    ① 원문에서 글 앞(머리)인데 번역문에서 글 뒤에 있는 토큰 → 번역문 머리로, 원문 순서대로. 뒤에 개행이 붙어 있던 사전 토큰(화자표)은 개행을 함께.
       단 원문에서 글 속 낱말(바로 뒤에 글이 이어짐)인 사전 토큰은 번역문이 이미 글로 풀어 썼으므로 버린다.
    ② 원문에서 글 속(뒤)인데 번역문에서 글 끝 뒤로 밀린 **사전 토큰** → 버린다(번역문 글이 이미 풀어 썼다).
    ③ 원문에서 글 줄바꿈 뒤에 오는 이름표·화자 호출 앞에 개행이 빠졌으면 더한다."""
    info = jp_info(jp, tokens)
    if info is None:
        return kr
    els = split_kr(kr)
    fl = kr_flags(els)
    al = align(els, info, fl)
    move: list[tuple[int, str]] = []  # (원문 인덱스, 문자열)
    drop: set[int] = set()
    for ei, j in sorted(al.items(), reverse=True):
        s = els[ei][1]
        d = info[j]
        if s.startswith("{") and (d["next_text_char"] or d["before"]):
            if ps1 and s.startswith("{D") and _literal_before(els, ei, drop) and not _text_after(els, ei, drop):
                drop.add(ei)  # 글 속 낱말이 글 끝 뒤로 밀렸다 — 번역문이 이미 풀어 썼다
            continue
        if not d["before"] and fl[ei]:  # 머리 토큰이 글 뒤로 밀렸다
            if False:
                pass
            else:
                move.append((j, s + ("\n" if s.startswith("{") and d["nl_after"] else "")))
                drop.add(ei)
    if not move and not drop:
        return _add_nl(jp, kr, tokens, info)
    # 머리 = 번역문 앞쪽의 (글 앞) 토큰들 + 옮겨 온 것
    lead: list[tuple[int, str]] = []
    first_text = next((i for i, f in enumerate(fl) if f), len(els))
    keep: list[tuple[str, str]] = []
    for ei, (kind, s) in enumerate(els):
        if ei in drop:
            continue
        if ei < first_text and ei not in drop:
            if kind == "k" and ei in al and s != "<@>":
                lead.append((al[ei], s))
                continue
            if kind == "t" and s.strip(BLANK) == "" and lead:
                # 앞 토큰에 붙은 개행
                j, ps = lead[-1]
                lead[-1] = (j, ps + s)
                continue
        keep.append((kind, s))
    lead.extend(move)
    lead.sort(key=lambda x: x[0])
    head = "".join(s for _, s in lead)
    # 남은 요소 앞의 공백 개행 정리
    body = "".join(s for _, s in keep)
    out = head + body
    # 글 뒤에 남은 공백 꼬리 정리: 「…다. <E0>」 같은 꼴은 건드리지 않는다
    return _add_nl(jp, out, tokens, jp_info(jp, tokens))


def _literal_before(els: list[tuple[str, str]], ei: int, skip: set[int] | frozenset[int] = frozenset()) -> bool:
    """ei 앞에 (이름표 밖) 번역문 **글자**가 있나 — 사전 문장 토큰만으로 된 조각(글이 곧 `{D5:xx}`)은 해당 없다."""
    header = False
    for k, (kind, s) in enumerate(els[:ei]):
        if k in skip:
            continue
        if kind == "k":
            header = True if s == "<E3>" else (False if s == "<E1>" else header)
        elif not header and JOSA.sub("", s).strip(BLANK):
            return True
    return False


def _text_after(els: list[tuple[str, str]], ei: int, skip: frozenset[int] | set[int] = frozenset()) -> bool:
    for k, (kind, s) in enumerate(els[ei + 1 :], ei + 1):
        if k in skip:
            continue
        if kind == "t" and JOSA.sub("", s).strip(BLANK):
            return True
        if kind == "k" and _is_text_token(s):
            return True
    return False


def _add_nl(jp: str, kr: str, tokens: list[str], info: list[dict] | None) -> str:
    """원문에서 개행 바로 뒤에 화자 호출이 오는데 번역문에서 개행이 빠진 자리에 개행을 더한다."""
    if info is None:
        return kr
    els = split_kr(kr)
    al = align(els, info)
    out: list[tuple[str, str]] = []
    for ei, (kind, s) in enumerate(els):
        if kind == "k" and ei in al and out:
            j = al[ei]
            d = info[j]
            nxt = info[j + 1] if j + 1 < len(info) else None
            # 화자 호출(이름 사전 토큰이 뒤따르는 CALL/RETURN)·이름표뿐 아니라 **원문에서 개행 바로 뒤에 오는 모든 CALL/RETURN**: 호출 대상은 새 줄 머리에서 시작한다
            # (qa 2026-10-20 「뭣하다만싸움에」·「이, 이놈이!! 보아드」 — 개행이 빠져 호출 문장이 앞 줄 끝에 붙었다). `_` 로 못 쓰는 nxt 는 이전 조건 흔적이라 남긴다
            _ = nxt
            speaker_call = s == "<E3>" or s.startswith("<FC:") or s == "<FE>"
            if speaker_call and d["nl_before"]:
                prev_kind, prev = out[-1]
                if (
                    prev_kind == "t"
                    and prev.strip(BLANK)
                    and not prev.endswith("\n")
                    and (s != "<E3>" or re.search(r"[.!?…。」]$", prev))
                ):
                    out[-1] = ("t", prev + "\n")
        out.append((kind, s))
    return "".join(s for _, s in out)
