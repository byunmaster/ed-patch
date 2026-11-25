#!/usr/bin/env python3
"""**굽는 바이트의 조판 전수 게이트** — 번역 규칙 2-1~2-6·2-16 ③ · 4-6(색·연출 제어 코드)을 핫픽스를 얹은 후보 바이트와
실행파일 문자열에 대고 센다(마스터 10-31 「모든 대사·전투 조판 — 첫칸공백 · 고아부호 · 빈줄개행 · 균등 분배 · 색 누락」).

이미 있는 게이트(`check_typeset_rules` ①~④ · `check_page_split` a~e · `check_prewrap_rules` · `check_battle_wrap`)는 **제품 문안**을
재거나 런타임 조립 문장만 본다. 이 도구는 **빠진 축**과 **핫픽스 덮개를 얹은 값**을 더한다 — 둘 다 같은 후보를 읽으므로
`check_typeset_rules.check_window` 를 그대로 불러 첫칸 공백(2-5) · 고아 부호(2-3) · 빈 줄(2-4) · 넘침(29열)도 같이 센다.

  씬 대사(후보 바이트)
    부호 뒤 공백(2-1) · 부호 앞 공백(2-2) · 마지막 창 한 어절(2-16 ③) · 창 줄 수 치우침(2-16 ③) ·
    핫픽스가 제품 문안의 색·연출 제어 바이트 열·`%c` 수를 바꿨나(4-6 — 원판↔제품 대조는 `check_scn_structure`) ·
    + check_window ①~④
  실행파일 문자열(전투·시스템·상점)
    줄(`/` 구분)마다 부호 뒤·앞 공백 · 줄 첫 칸 공백 · 고아 부호 · 빈 줄 · 줄 폭 29열 초과

  + 마스터 11-03 「화면 몫으로 남긴 규칙 셋」 — 정적으로 센다
    가운데 맞춤 2-8(오프닝·엔딩 가운데 줄 — 줄 끝 `.` `,` `…` 를 뺀 잉크 폭의 좌우 여백 차) ·
    한 줄 문장 2-10(29열에 드는 문장이 줄을 넘어 갈라진 곳 — 앞 문장 뒤에서 시작해 갈라지면 `mid`, 줄머리에서 시작했는데 갈라지면 `hard`) ·
    쉼표 2-13(「뺀다」 부류 중 규칙 예시와 꼴이 같은 것 — 접속부사 뒤 · 문장 첫머리 주제(`은·는`) 뒤 · 부사어(`에는` …) 뒤 ·
    `~는데·~지만·~만` 앞 절이 11음절 이하 · ⑩ 문장 앞 `그럼,` · ⑪ `~고·~며·~서` 앞 절 11음절 이하 — 마스터 11-03). 애매한 부류(`~고·~며` 연결 · 쪽 끝 · 줄 끝)는 센 수만 낸다.
    28열을 못 넘는 줄바꿈 한계(29열 문장)는 2-17 로 허용 — 센 뒤 따로 둔다.

  `원판 같은 꼴` — 같은 자리 원판(일본어) 쪽이 같은 모양이면(창 줄 수 치우침) 우리가 만든 게 아니라 원문 구조를 따른 것이라 센 뒤
  따로 둔다(실패로 안 친다).

  python3 tools/check_baked_typeset.py        # 요약 + 실패
  python3 tools/check_baked_typeset.py -v     # 목록
"""

import contextlib
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

os.environ["ED_HOTFIX"] = "0" if os.environ.get("ED_BAKED_CHILD") else "1"  # 핫픽스 덮개를 얹은 값(v1.2.1 준비분)을 잰다
with contextlib.redirect_stdout(io.StringIO()):
    import reinsert_kr_pilot as R
import check_typeset_rules as T

SENT_END = ".?!…」』”~)"
AX_AFTER = re.compile(r"[,.!?](?=[가-힣A-Za-z])")  # 부호 바로 뒤에 글자(2-1)
AX_BEFORE = re.compile(r"(?<=[가-힣A-Za-z0-9]) +[,.!?]")  # 부호 앞 공백(2-2)
AXES = (
    "첫칸공백 2-5", "고아부호 2-3", "빈줄 2-4", "넘침·낱말절단 2-6", "부호뒤공백 2-1", "부호앞공백 2-2",
    "마지막창한어절 2-16", "줄수치우침 2-16", "색코드열 4-6", "조각이음공백 2-1",
    "가운데맞춤 2-8", "한줄문장 2-10", "쉼표 2-13", "입장배너 가운데 2-8",
)  # fmt: skip
RULE_AXIS = {"①": "고아부호 2-3", "②": "빈줄 2-4", "③": "첫칸공백 2-5", "④": "넘침·낱말절단 2-6"}


def line_axes(ln):
    """줄 하나의 부호 공백 위반 [축] — 말줄임(`...`)·소수점(`3.5`)·`%s` 는 뺀다."""
    s = ln.replace("...", "…")
    s = re.sub(r"\d[.,]\d", "0", s)
    out = []
    if AX_AFTER.search(s):
        out.append("부호뒤공백 2-1")
    if AX_BEFORE.search(s):
        out.append("부호앞공백 2-2")
    return out


def ctrl_bytes(b):
    """인라인 제어 바이트 열 — `%c`/`%s`/`%d` 토큰과 2바이트 글자는 건너뛰고 0x01~0x1F(개행 제외)만 모은다."""
    out, i = [], 0
    while i < len(b):
        c = b[i]
        if c == 0x25 and i + 1 < len(b) and b[i + 1] in b"csd":
            i += 2
        elif c >= 0x81:
            i += 2
        else:
            if 0 < c < 0x20 and c != 0x0A:
                out.append(c)
            i += 1
    return out


PRODUCT = {}


def product_ctrl():
    """제품 문안(핫픽스 없이)의 블록별 (제어 바이트 열, `%c` 수) — 핫픽스가 색·연출 코드를 건드렸나 대조하는 기준."""
    import json
    import subprocess

    code = (
        "import os,sys,io,json,contextlib;sys.path.insert(0,%r);os.environ['ED_HOTFIX']='0'\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n import reinsert_kr_pilot as R, check_baked_typeset as B\n"
        " d={f'{s}:{e}':[B.ctrl_bytes(c.rstrip(bytes(1))),R.render_bytes(c,ctrl=True).count('%%c')] for s,e,_j,c,_t in R.iter_candidates(None)}\n"
        "sys.__stdout__.write(json.dumps(d))" % os.path.dirname(os.path.abspath(__file__))
    )
    env = dict(os.environ, ED_HOTFIX="0", ED_BAKED_CHILD="1")
    r = subprocess.run(["nice", "-n", "10", sys.executable, "-c", code], capture_output=True, text=True, env=env)
    return json.loads(r.stdout[r.stdout.index("{") :]) if r.returncode == 0 and "{" in r.stdout else None



# ── 2-10 한 줄 문장 · 2-13 쉼표 · 2-8 가운데 맞춤 (마스터 11-03) ─────────────────────────────
FRAME = T.FRAME
S_END = re.compile(r"[.!?…~]+[」』”)]*$")
PLATE = re.compile(r"^[^.,!?…~]{1,12}$")  # 이름판처럼 본문 첫 줄에 붙은 짧은 머리 줄
CONJ = frozenset("다만 그러나 하지만 그런데 그리고 그래서 그렇지만 그러니까 또한 게다가 한편 따라서 그러므로 그러면 그렇다면".split())
KEEP_ONELINE = {  # 29열 안에 드는데 못 고친 자리 — 구조가 막는다(고친 뒤 기준선). 새로 생기면 실패.
    # 상점 가격 프롬프트(871·901·929·ED1SCN4 208·265)는 마스터 11-05 「상점 가격문구 같은건 굳이 한줄로 안해도 돼」 — 그대로 둔다.
    "ED1SCN3:143": "앞 창이 아이템 주입 스팬 — `은`/`을` 사이 `{p}` 가 줄을 가른다",
    "ED1SCN3:871": "상점 가격 프롬프트 빌더 — 이름 뒤 첫 줄 고정", "ED1SCN3:901": "〃", "ED1SCN3:929": "〃",
    "ED1SCN4:208": "상점 가격 프롬프트 빌더", "ED1SCN4:265": "〃",
    "ED1SCN6:257": "주입 스팬 셋(`{p}`) — 스팬 경계에선 개행이 죽는다",
    "ED1SCN6:277": "다음 블록이 같은 줄에 이어 그려지는 자리 — `{n}` 이 폭 보정", 
    "ED2SCN5:92": "창 경계 붙임 공백(NOBREAK_SP) — 개행이 죽는다", "ED2SCN9:5": "〃",
}  # fmt: skip


def vis_w(s):
    """`%s`·`%d` 를 최장 값으로 바꾼 화면 열 폭(반각 1 · 그 밖 2)."""
    return T.width(s.replace("%s", "세리오스").replace("%d", "9999"))


def sentences(lines):
    """줄 목록 → [(시작 줄, 끝 줄, 문장, 줄머리에서 시작했나)]. 문장은 줄을 공백으로 이어 붙인다. `…` 는 줄 끝일 때만 문장 끝으로 본다."""
    out, cur, sl, fol = [], [], None, False
    for i, ln in enumerate(lines):
        toks = re.findall(r"\S+\s*", ln)
        for k, tok in enumerate(toks):
            if sl is None:
                sl, fol = i, k == 0
            w = tok.strip()
            cur.append(w)
            if S_END.search(w) and (k == len(toks) - 1 or not w.endswith("…")):
                out.append((sl, i, " ".join(cur), fol))
                cur, sl = [], None
    return out


def oneline_split(lines, plate=False):
    """[(종류, 문장, 열 폭)] — 29열에 드는 문장이 줄을 넘어 갈라진 곳. `mid` 앞 문장 뒤에서 시작 · `hard` 줄머리에서 시작."""
    if plate and len(lines) > 1 and PLATE.match(lines[0]):
        lines = lines[1:]
    return [
        ("hard" if fol else "mid", t, vis_w(t))
        for s, e, t, fol in sentences(lines)
        if e > s and vis_w(t) <= FRAME
    ]


def comma_axes(sent):
    """문장 하나의 쉼표 위반 [(부류, 토막)] — 「뺀다」 부류 중 규칙 예시와 꼴이 같은 것만. + 참고 계수는 `comma_info`."""
    toks = sent.split()
    out, start = [], 0
    for i, tok in enumerate(toks):
        if not tok.endswith(","):
            continue
        w = tok[:-1]
        if i == 0 and w in CONJ:
            out.append(("접속부사 뒤", sent))
        elif w == "그럼" and (i == 0 or toks[i - 1] in ("%s", "%d")):  # ⑩ 문장 앞 접속 — 이름판 변수 뒤도 문장 머리다
            if sent not in KEEP_GEUREOM:
                out.append(("문장 앞 그럼 ⑩", sent))
        elif i <= 1 and re.search(r"(에는|에서는|으로는|로는|에게는|한테는|에서|에도)$", w):
            out.append(("부사어 뒤", sent))
        elif i <= 2 and len(w) >= 2 and w[-1] in "은는" and i + 1 < len(toks):
            out.append(("주제 뒤", sent))
        elif re.search(r"(는데|은데|인데|던데|지만|만)$", w) and i > start:  # 앞 절이 한 낱말뿐이면 감탄(`가만,`)이다
            clause = " ".join(toks[start : i + 1])[:-1]
            if not re.search(r"[0-9A-Za-z%{]", clause) and sum("가" <= c <= "힣" for c in clause) <= 11:
                out.append(("짧은 앞절 ~는데·~지만·~만", sent))
        elif (
            re.search(r"(고|며|면서|서)$", w)
            and not re.search(r"(라고|자고|시고|말고|에서|에게서|그래서)$", w)  # 인용·권유·관용(`~라고,` `~자고,` `그러지 마시고,` `~지 말고,`)은 남기는 부류
            and i > start
            and not re.search(r"[0-9A-Za-z%{]", " ".join(toks[start : i + 1]))
            and sum("가" <= c <= "힣" for c in " ".join(toks[start : i + 1])) <= 11
        ):
            if not sent.startswith("어때 지고,") and not sent.startswith(KEEP_DAEGU):  # `지고` 는 사람 이름(부르는 말 — 남기는 부류) · 대구는 쉼표를 남긴다
                out.append(("짧은 연결 ~고·~며·~서(11음절 이하) ⑪", sent))
        start = i + 1
    return out


# ⑪ 대구 — 같은 꼴 두 절이 맞서거나 나란한 문장은 짧아도 쉼표를 남긴다(마스터 11-06 「대구는 쉼표넣자」). 문장 머리로 가린다
KEEP_DAEGU = (
    "있지 게일, 병사들도 다쳐 버렸고, ",
    "광산도 그럭저럭 복구됐고, ",
    "문이 부서져 있고, ",
    "어디 보자, 어제가 목걸이고, ",
    "가이드도 예쁘고, ",
    "이제는 치안도 좋고, ",
    "무기는 우리에게 맡기고, ",
    "바람의 탑은 가라앉고, ",
    "술도 마음껏 마실 수 있었고, ",
    "어째서 우리는 고생만 하고, ",
)

# ⑩ 「그럼,」 중 남기는 부류 — 부르는 말 앞 · 작별 인사(문장 전체로 적는다)
KEEP_GEUREOM = frozenset({"그럼, 왕자님.", "그럼, 편히 쉬십시오.", "그럼, 몸조리 잘하세요."})
COMMA_INFO = {"연결어미쉼표": 0, "쪽끝쉼표": 0, "줄끝쉼표": 0}


def comma_sentences(text):
    """한 덩이 글 → 문장들(`.` `!` `?` `…` 뒤 공백에서 가른다)."""
    return [x for x in re.split(r"(?<=[.!?…])\s+", text) if x.strip()]


def comma_info(text, info):
    """애매한 부류 계수(실패 아님) — `~고·~며` 연결(B) · 쪽 끝 쉼표 · 줄 끝 쉼표."""
    for win in text.split("%c"):
        lines = win.split("\n")
        for i, ln in enumerate(lines):
            if ln.rstrip().endswith(","):
                info["쪽끝쉼표" if i == len(lines) - 1 else "줄끝쉼표"] += 1
    for ln in text.replace("%c", " ").replace("\n", " ").split(" "):
        if re.search(r"(고|며|면서|해서|서),$", ln):
            info["연결어미쉼표"] += 1


def scene_block(scn, eid, raw, cand, hits, flags, speaker=""):
    k = R.render_bytes(cand, ctrl=True)
    ws = T.windows(R.render_bytes(cand))
    wl = [w.rstrip("\n").split("\n") for w in ws]
    for w in ws:
        for rule, ln in T.check_window(w):
            hits.append((RULE_AXIS[rule], scn, eid, ln))
    for lines in wl:
        for ln in lines:
            for ax in line_axes(ln):
                hits.append((ax, scn, eid, ln))
    for lines in wl:
        for kind, st, wd in oneline_split(lines, plate=not speaker):
            if wd > FRAME - 1:
                flags.append(("한줄문장 28열 한계 2-17", scn, eid, st))  # 줄바꿈 한계(29열) — 문안을 줄이지 않고 갈림을 허용
            elif "이(가)" in st and "있었습니다" in st:
                # 보물상자 존대 둘째 줄: 「상자에는 ⟨아이템⟩이(가) 있었습니다.」 — 아이템 이름이 런타임에 들어가 가장 긴 이름(8음절=16열)이면
                # 29열을 넘는다. 이름이 짧아도 「있었습니다.」(11열)까지 한 줄이면 대부분 넘어, **이름 뒤에서 어절 경계로 접는다**(2-19).
                flags.append(("한줄문장 28열 한계 2-17", scn, eid, st))
            elif f"{scn}:{eid}" in KEEP_ONELINE:
                flags.append(("한줄문장 구조 막힘", scn, eid, st))
            else:
                hits.append(("한줄문장 2-10", scn, eid, f"{kind} {st}"))
    for st in comma_sentences(" ".join(x.strip() for lines in wl for x in lines)):
        for cls, seg in comma_axes(st):
            hits.append(("쉼표 2-13", scn, eid, f"{cls}: {seg}"))
    comma_info(k, COMMA_INFO)
    jws = T.windows(raw.rstrip(b"\x00").decode("cp932", "replace"))
    jl = [w.rstrip("\n").split("\n") for w in jws] if len(jws) == len(ws) else None
    for i in range(1, len(ws)):
        prev = ws[i - 1].rstrip()
        if not prev or prev[-1] in SENT_END or prev.endswith(("%s", "%d")) or prev.replace("%c", "") in ("%s", "%d"):
            continue
        if i == len(ws) - 1 and len(ws[i].split()) == 1 and "%" not in ws[i]:
            # 원판 마지막 창도 짧거나 앞 창이 짧은 한 줄(≤8자 — 이름판·쪽 대기 코드로 끊은 말)이면 원문 구조를 따른 것 — 센 뒤 따로 둔다
            same = (jl is not None and len(jws[i].strip()) <= 6) or (len(prev) <= 8 and "\n" not in prev)
            (flags if same else hits).append(("마지막창한어절 2-16", scn, eid, prev[-14:] + " | " + ws[i].strip()))
        if abs(len(wl[i - 1]) - len(wl[i])) >= 3:
            same = (jl is not None and abs(len(jl[i - 1]) - len(jl[i])) >= 3) or (len(prev) <= 8 and "\n" not in prev)
            (flags if same else hits).append(("줄수치우침 2-16", scn, eid, f"{len(wl[i - 1])}/{len(wl[i])}"))
    base = PRODUCT.get(f"{scn}:{eid}")
    if base is not None and (base[0] != ctrl_bytes(cand.rstrip(b"\x00")) or base[1] != k.count("%c")):
        hits.append(("색코드열 4-6", scn, eid, f"제품 {base[0]}·%c {base[1]} ≠ 핫픽스 {ctrl_bytes(cand.rstrip(bytes(1)))}·%c {k.count('%c')}"))


FRAG_END = re.compile(r"(?:에게|에서|으로|한테|께서?)$")


def exe_row(rid, kr, hits, flags=None):
    # 조사로 끝나는 조각(`…에게`)은 뒤에 런타임으로 이어 붙는 말(아이템·주문 이름)과 한 어절로 붙는다 — 끝 공백이 있어야 한다.
    # (ED2 몬스터 아이템 사용 「자신에게회복 버섯을」 — 10-31 전투 촬영에서 잡았다)
    flags = [] if flags is None else flags
    if FRAG_END.search(kr) and "/" not in kr:
        hits.append(("조각이음공백 2-1", "EXE", rid, kr))
    for li, ln in ((i, x) for v in kr.split(" ‖") for i, x in enumerate(v.split("/"))):
        for ax in line_axes(ln):
            hits.append((ax, "EXE", rid, ln))
        if li and re.match(r"^ {1,2}\S", ln):  # 첫 줄은 변수 뒤에 이어 붙는 조각이라 앞 공백이 맞다
            hits.append(("첫칸공백 2-5", "EXE", rid, ln))
        if ln and T.PUNCT_ONLY.match(ln) and 0 < len(ln.strip()) <= 2:
            hits.append(("고아부호 2-3", "EXE", rid, ln))
    for v in kr.split(" ‖"):
        lines = v.split("/")
        if re.match(r"^%c.*?%c$", lines[0]):  # 이름판 줄
            lines = lines[1:]
        lines = [x.replace("%c", "") for x in lines]
        if len(lines) > 1:
            for kind, st, wd in oneline_split(lines):
                if wd > FRAME - 1:
                    flags.append(("한줄문장 28열 한계 2-17", "EXE", rid, st))
                else:
                    hits.append(("한줄문장 2-10", "EXE", rid, f"{kind} {st}"))
        for st in comma_sentences(" ".join(x.strip() for x in lines)):
            for cls, seg in comma_axes(st):
                hits.append(("쉼표 2-13", "EXE", rid, f"{cls}: {seg}"))
        comma_info(v.replace("/", "\n"), COMMA_INFO)
        # 줄 폭(넘침)은 안 센다 — 이름이 런타임이라 `check_prewrap_rules` · `check_battle_wrap` · `check_battle_grid_wrap` 몫이다


def selftest():
    """양성 대조 — 일부러 망가뜨린 줄을 각 축이 잡아야 하고 정상은 안 걸려야 한다."""
    assert line_axes("안녕,잘 가.") == ["부호뒤공백 2-1"]
    assert line_axes("안녕 , 잘 가") == ["부호앞공백 2-2"]
    assert line_axes("그래... 응?") == [] and line_axes("값은 3.5입니다") == []
    assert ctrl_bytes(b"\x01%c\x82\xa0\x02\n") == [1, 2] and ctrl_bytes(b"%c\x82\xa0\n") == []
    h = []
    exe_row("t", "%c자신%c에게", h)
    assert [a for a, *_ in h] == ["조각이음공백 2-1"], h
    h = []
    exe_row("t", "%c자신%c에게 ", h)
    assert not h, h
    h = []
    exe_row("t", "ok/ 앞 공백/.", h)
    exe_row("t", "정상 줄/그래, 알았어.", h)
    assert {a for a, *_ in h} - {"한줄문장 2-10"} == {"첫칸공백 2-5", "고아부호 2-3"}, h


def selftest_popup():
    assert popup_entry_axes(b"\x8c\xb4\x90\xb9") == []
    assert popup_entry_axes(b"\x8c\xb4\x90\xb9 ") == ["앞뒤 공백", "홀수 바이트"]
    assert popup_entry_axes(b" \x8c\xb4") == ["앞뒤 공백", "홀수 바이트"]
    assert popup_entry_axes(b"\x8c\xb4 \x90\xb9") == ["홀수 바이트"]


def selftest_new():
    """2-8 · 2-10 · 2-13 양성 대조 — 일부러 만든 줄이 걸리고 정상·허용 부류는 안 걸려야 한다."""
    assert oneline_split(["경험치를 얻었다. MP가", "5포인트 올랐다."])[0][0] == "mid"
    assert oneline_split(["외출하십니까,", "왕자님? 다녀오십시오."])[0][0] == "hard"
    assert not oneline_split(["경험치를 얻었다.", "MP가 5포인트 올랐다."])
    assert not oneline_split(["이것은 한 줄에 도저히 들어가지 않을 만큼", "아주 길고 긴 문장입니다 정말로 그렇습니다."])
    assert oneline_split(["사령관", "어리석은 놈!!"], plate=True) == [] and len(oneline_split(["사령관", "어리석은 놈!!"])) == 1
    for txt, cls in (
        ("다만, 그것은 사실이다.", "접속부사 뒤"),
        ("파렌 왕국은, 평화로웠다.", "주제 뒤"),
        ("처음에는, 몰랐다.", "부사어 뒤"),
        ("비가 오는데, 가자.", "짧은 앞절 ~는데·~지만·~만"),
    ):
        assert [c for c, _ in comma_axes(txt)] == [cls], (txt, comma_axes(txt))
    assert [c for c, _ in comma_axes("창이 깨져 있고, 안에는 몬스터가 돌아다닌다.")] == ["짧은 연결 ~고·~며·~서(11음절 이하) ⑪"]
    assert not comma_axes("문이 부서져 있고, 안에는 몬스터가 돌아다닌다.")  # 대구 예외
    assert [c for c, _ in comma_axes("그럼, 가시지요.")] == ["문장 앞 그럼 ⑩"]
    assert [c for c, _ in comma_axes("진척이 없어서, 난처합니다.")] == ["짧은 연결 ~고·~며·~서(11음절 이하) ⑪"]
    for ok in ("아트라스, 가자.", "그래, 좋아.", "가만, 그게 뭐였더라.", "하룻밤에 10 Gold입니다만, 괜찮으십니까?",
               "이 근방 드래곤은 알을 낳지 않는데, 우리가 낳을 참이라네.", "그러지 마시고, 비싸게 사 드릴 테니…",
               "그럼, 왕자님.", "그럼, 편히 쉬십시오.", "마스쿤 마을을 몬스터에게서 해방시키고, 다시 평화를 되찾았습니다.", "란도, 플로라, 아트라스를 불러라."):  # fmt: skip
        assert not comma_axes(ok), (ok, comma_axes(ok))
    assert center_ink_diff("그리고 세월은 흘렀다…") == 0 and center_ink_diff("그것은 실로") == 0
    assert center_ink_diff("!＿앞으로 우리들의,") is None
    assert center_ink_diff("이윽고 기다리던 왕자가 태어난다.") != 0  # 64유닛 꽉 참 — 앞 빈칸을 못 얹는다


def selftest_scene():
    """창 단위 축(마지막 창 한 어절 · 줄 수 치우침 · 핫픽스의 제어 바이트 변경) 양성 대조 — 합성 후보 바이트."""
    import hangul_map

    def enc(t):
        return b"".join(
            ch.encode() if ch.isascii() else hangul_map.syllable_sjis(ch).to_bytes(2, "big")
            for ch in t
        )

    raw = b"%c\x82\xa0%c\n" + b"\x82\xa0" * 8 + b"%c" + b"\x82\xa0" * 8 + b"%c\x00"
    cases = {
        "마지막창한어절 2-16": "%c여자%c\n오늘은 날씨가 아주 맑고 좋아서 정말%c기쁩니다.%c",
        "줄수치우침 2-16": "%c여자%c\n오늘은 날씨가 아주 맑고\n좋아서 정말 기쁜 마음으로\n길을 나서려\n합니다 여러분%c그래서 가자.%c",
    }
    ok = "%c여자%c\n오늘은 날씨가 아주 맑아서%c정말 기쁩니다 여러분.%c"
    for ax, txt in cases.items():
        h, f = [], []
        scene_block("T", "1", raw, enc(txt) + b"\x00", h, f)
        assert any(a == ax for a, *_ in h), (ax, h, f)
    h, f = [], []
    scene_block("T", "1", raw, enc(ok) + b"\x00", h, f)
    assert not h, ("정상 후보가 걸렸다", h)
    PRODUCT["T:2"] = ([1], 4)
    h, f = [], []
    scene_block("T", "2", raw, enc(ok) + b"\x00", h, f)
    assert [a for a, *_ in h] == ["색코드열 4-6"], ("제어 바이트 변경을 못 잡았다", h)
    PRODUCT.clear()


def main():
    selftest()
    selftest_scene()
    selftest_new()
    selftest_popup()
    for k in COMMA_INFO:
        COMMA_INFO[k] = 0
    verbose = "-v" in sys.argv
    hits, flags = [], []
    nblk = 0
    pc = product_ctrl()
    if pc is None:
        print("  ❌ 안 쟀다 — 제품 문안 기준 제어 바이트를 못 뽑았다")
        return 1
    PRODUCT.update(pc)
    for scn, eid, raw, cand, _t in R.iter_candidates(None):
        if (scn, str(eid)) in T.SCRIPT_PREFIX_SILENT:
            continue
        nblk += 1
        scene_block(scn, eid, raw, cand, hits, flags, speaker=_t[0])
    nexe = 0
    kr_bin = os.path.join(C.BUILD_DIR, "Eiyuu Densetsu (KR).bin")
    if not os.path.exists(kr_bin):
        print("  ❌ 안 쟀다 — 최종 이미지 없음(실행파일 문자열)")
        return 1
    import tempfile

    import pair_table_sys as PS

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "p.tsv")
        with contextlib.redirect_stdout(io.StringIO()):
            PS.battle_system(kr_bin, out)
        with open(out, encoding="utf-8") as fh:
            rows = [ln.split("\t") for ln in fh.read().split("\n")[1:] if ln.strip()]
    import json

    hot = hotfix_monster()
    tm = hotfix_textmap_pairs()
    for r in rows:
        if len(r) >= 3 and r[2] and not any("번역 대상 아님" in x or "죽은" in x for x in r[3:5]):
            nexe += 1
            jp = r[1][2:] if r[1].startswith("%c") else r[1]
            kr = ("%c" + hot[jp]) if jp in hot else r[2]
            for old, new in tm:  # 핫픽스 textmap(derive 값 덮개) — 제품 파생값을 핫픽스 값으로 바꿔 센다
                kr = kr.replace(old, new)
            exe_row(r[0], kr, hits, flags)
    nctr, nctr_bad = center_scan(hits, flags)
    npop = popup_scan(hits, kr_bin)
    cnt = {a: 0 for a in AXES}
    for a, *_ in hits:
        cnt[a] += 1
    fl = {}
    for a, *_ in flags:
        fl[a] = fl.get(a, 0) + 1
    print(
        f"  굽는 바이트 조판 [ps1-ed1+2] — 씬 {nblk}블록 · 실행파일 {nexe}문자열 · 가운데 줄 {nctr} · 입장 배너 {npop}칸 · "
        + " · ".join(f"{a.split()[0]} {n}" for a, n in cnt.items())
        + f" · 원판 같은 꼴(실패 아님) 마지막창 {fl.get('마지막창한어절 2-16', 0)}·줄수 {fl.get('줄수치우침 2-16', 0)}"
        + f" · 한 줄 문장 28열 한계(2-17 허용) {fl.get('한줄문장 28열 한계 2-17', 0)}·구조 막힘 {fl.get('한줄문장 구조 막힘', 0)}"
        + f" · 가운데 못 맞춤(폭 한도) {fl.get('가운데맞춤 폭 한도', 0)}"
        + f" · 쉼표 애매 부류 연결어미 {COMMA_INFO['연결어미쉼표']}·쪽끝 {COMMA_INFO['쪽끝쉼표']}·줄끝 {COMMA_INFO['줄끝쉼표']}"
        + " (양성 대조 통과)"
    )
    for a, scn, eid, st in flags[: 400 if verbose else 0]:
        print(f"    ➖ {a} {scn} {eid} {st!r}")
    for a, scn, eid, st in hits[: 400 if verbose else 8]:
        print(f"    ❌ {a} {scn} {eid} {st!r}")
    return 1 if hits else 0


def hotfix_monster():
    import json

    hp = os.path.join(C.ROOT, "hotfix", "textmap", "monster_lines_ed2.json")  # 제품 이미지 위에 핫픽스 값을 얹어 센다
    return {k: v for k, v in json.load(open(hp, encoding="utf-8")).items() if not k.startswith("_")} if os.path.exists(hp) else {}


def hotfix_textmap_pairs():
    """[(제품 파생값, 핫픽스 값)] — 줄 구분을 `/` 로. `monster_lines_ed2` 는 따로(원문 키)."""
    import glob
    import json

    out = []
    for f in sorted(glob.glob(os.path.join(C.ROOT, "hotfix", "textmap", "*.json"))):
        cls = os.path.basename(f)[:-5]
        if cls == "monster_lines_ed2":
            continue
        dp = os.path.join(C.OUT_DIR, "text", f"{cls}.json")
        if not os.path.exists(dp):
            continue
        der = json.load(open(dp, encoding="utf-8"))
        for k, v in json.load(open(f, encoding="utf-8")).items():
            if not k.startswith("_") and isinstance(der.get(k), str) and der[k] != v:
                out.append((der[k].replace("\n", "/"), v.replace("\n", "/")))
    return out


CENTER_KNOWN = {  # 폭 한도(64유닛)에 꽉 찬 줄 — 앞 빈칸을 얹을 자리가 없고, 문안을 줄이지 않는다(2-17)
    ("opening_ed2", 0x10F0): "이윽고 기다리던 왕자가 태어난다. — 64유닛 꽉 참",
    ("ending_ed1", 0x1A88): "제 것인 양 세계를 지배하고 있다. — 64유닛 꽉 참",
}


def center_ink_diff(kr, FIELD_OK=None):
    """오프닝·엔딩 가운데 줄 하나 — 최종 줄(빈칸 보정 뒤)의 `앞 빈칸 폭 − 줄 끝 부호 폭`(유닛). 0 이어야 잉크가 가운데다."""
    import patch_opening_font as P

    if kr.startswith("!"):
        return None  # 대화창 왼쪽 정렬 줄
    p = P.center_pad(kr)
    final = p if P.units(p) <= P.FIELD else kr
    head, body = (kr[0], kr[1:]) if kr.startswith("~") else ("", kr)
    tp = P.ADV_WIDE if body.endswith("…") else P.ADV_NARROW if body.endswith((".", ",")) else 0
    f = final[len(head) :]
    return (P.units(f) - P.units(f.lstrip(" "))) - tp


def center_scan(hits, flags):
    with contextlib.redirect_stdout(io.StringIO()):
        import patch_opening_font as P
    n = 0
    for cls in ("opening", "opening_ed2", "ending_ed1", "ending_ed2"):
        for o, kr in P.off_pairs(cls):
            d = center_ink_diff(kr)
            if d is None:
                continue
            n += 1
            if d:
                (flags if (cls, o) in CENTER_KNOWN else hits).append(
                    ("가운데맞춤 폭 한도" if (cls, o) in CENTER_KNOWN else "가운데맞춤 2-8", cls, hex(o), kr)
                )
    return n, 0


POPUP_LBA, POPUP_SIZE, POPUP_LO, POPUP_HI, POPUP_STRIDE = 756, 872448, 0x9A030, 0x9A280, 16


def popup_entry_axes(raw):
    """입장 배너(ED2.EXE 월드맵 마을 팝업, 16B 칸) 한 칸 — 엔진이 문자열 바이트 길이로 틀 안 가운데에 놓는다(11-04 실측:
    2~7자·공백 낀 홀수 길이 모두 가운데). 그래서 가운데가 깨지는 길은 둘뿐이다 — 앞뒤 공백(공백 폭만큼 쏠린다)·홀수 바이트."""
    out = []
    if raw[:1] == b" " or raw[-1:] == b" ":
        out.append("앞뒤 공백")
    if len(raw) % 2:
        out.append("홀수 바이트")
    return out


def popup_scan(hits, kr_bin):
    """ED2.EXE 입장 배너 표를 최종 이미지에서 읽어 센다. 반환 = 센 칸 수."""
    buf = C.extract(POPUP_LBA, POPUP_SIZE, path=kr_bin)
    n = 0
    for o in range(POPUP_LO, POPUP_HI, POPUP_STRIDE):
        raw = buf[o : o + POPUP_STRIDE].split(b"\x00")[0]
        if not raw:
            continue
        n += 1
        for why in popup_entry_axes(raw):
            hits.append(("입장배너 가운데 2-8", "ED2.EXE", hex(o), why))
    return n


if __name__ == "__main__":
    sys.exit(main())
