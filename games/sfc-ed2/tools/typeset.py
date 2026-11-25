"""sfc-ed2 대사 조판 — 한국어 문안을 대사창 규격(줄 폭 50단위 · 쪽당 3줄)에 맞춰 줄바꿈·쪽 넘김을 넣는다.

규격(대사 출력기 `$C0:A9F5` 와 에뮬 실측 2026-10-12):
  · 글자 폭 단위: 전각(2바이트) 3 · 반각(1바이트·공백) 2 — 한 줄은 **50단위**(= 200px)까지(전각 16자 + 반각 1칸)
  · 한 쪽 = 본문 3줄(화자 이름 줄은 따로 한 줄 더 붙는다). 넘치면 `<05>`(키 대기 + 쪽 지우기)
번역 문안 표기: `⏎`(실제 개행)은 강제 줄바꿈, `<05>` 는 강제 쪽 넘김, 그 밖의 `<..>` 는 폭 0 제어. 어절(공백) 단위로 끊고(규칙 2-6),
줄 첫머리에 부호만 넘기지 않으며(2-3), 줄 첫 공백을 두지 않는다(2-5). 화자 머리(`<1e>이름<04>` + 개행)는 쪽 줄 수에 안 센다.
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from text import krwrap  # 줄바꿈 금지 판정(본용언+보조용언 등)의 정본 — 규칙을 다시 짓지 않는다(DRY)

LINE_UNITS = 50
NBSP = "\u00a0"  # 고유명사 속 공백 자리표시 — 어절로 안 갈라지고 폭은 반각 공백(2)
PAGE_ROWS = 3
_TOK = re.compile(r"<[^>]*>|\{\*[^{}/]+/[^{}/]+\}|\n|.", re.S)
_PUNCT = set(".,!?…」』)~:;")


_GLUE: list[str] = []
_GLUE_LOCAL = ["슬라임 괴롭히기"]  # 정본 고유명사는 아니지만 한 덩어리로 읽히는 이 게임의 명사구(「슬라임⏎괴롭히기」로 갈리면 안 된다 — 마스터 10-25)


def _glue(text: str) -> str:
    """정본 고유명사 가운데 공백이 든 이름(「사제 바바라」·「가죽 갑옷」)은 줄 사이에서 갈리지 않게 속 공백을 자리표시로 바꾼다(끝에서 되돌린다)."""
    if not _GLUE:
        import canon

        cats = canon.nouns("eiyuu")["categories"]
        _GLUE.extend(sorted({v for c in cats.values() for v in c.values() if isinstance(v, str) and " " in v} | set(_GLUE_LOCAL), key=len, reverse=True))
    for ph in _GLUE:
        if ph in text:
            text = text.replace(ph, ph.replace(" ", NBSP))
    return text


def width(tok: str, names: dict | None = None) -> int:
    if tok == NBSP:
        return 2
    if tok.startswith("<E") and names is not None:
        m = re.match(r"<E([01]):(\d+)>", tok)
        t = names.get(f"E{m.group(1)}:{m.group(2)}", "") if m else ""
        return sum(2 if 0x20 <= ord(c) <= 0x7E or c in "「」『』" else 3 for c in t)
    if tok.startswith("<10 ") and names is not None:  # 호출(`$10 lo hi`) — 같은 뱅크 조각 문자열을 끼워 넣는다. 폭은 대상 조각의 문안 폭(빌드가 `call:lohi` 로 넣어 준다)
        m = re.match(r"<10 ([0-9a-f]{2}) ([0-9a-f]{2})>", tok)
        t = names.get(f"call:{m.group(1)}{m.group(2)}", "") if m else ""
        return sum(2 if 0x20 <= ord(c) <= 0x7E or c in "「」『』" else 3 for c in re.sub(r"<[^>]*>", "", t))
    if tok.startswith("{*"):
        return 3  # 런타임 조사는 전각 한 글자
    if tok.startswith("<"):
        return 0
    return 2 if 0x20 <= ord(tok) <= 0x7E or tok in "「」『』" else 3


def _plain(w: list, names: dict | None) -> str | None:
    """어절의 이음 판정용 글자 — 사전 이름 토큰(`<E0:n>`·`<E1:n>`)은 조판기가 아는 이름 글자로 풀고, 그 밖의 제어·런타임 토큰이 끼면 None."""
    out = []
    for t in w:
        m = re.match(r"<E([01]):(\d+)>$", t)
        if m and names is not None and names.get(f"E{m.group(1)}:{m.group(2)}"):
            out.append(names[f"E{m.group(1)}:{m.group(2)}"])
        elif t[0] in "<{":
            return None
        else:
            out.append(t)
    return "".join(out)


def end_state(text: str, names: dict | None = None) -> tuple[int, int]:
    """조판된 문안이 끝난 자리의 (마지막 줄 폭, 이 쪽에 쓴 완결 줄 수) — 바로 이어지는 다음 구간이 이 줄에서 이어 쓰도록 넘겨 준다."""
    text = re.sub(r"<1e>.*?<04>\n?", "", text, flags=re.S)
    head_nl = text.startswith("\n") and "<05>" not in text  # 맨 앞 개행은 앞 구간 화자 머리의 개행이라 본문 줄이 아니다
    text = text.rsplit("<05>", 1)[-1]
    rows = text.count("\n") - head_nl
    last = text.rsplit("\n", 1)[-1]
    return sum(width(t, names) for t in _TOK.findall(last)), rows


def chain_state(text: str, lead: tuple[int, int] | None, names: dict | None = None) -> tuple[int, int]:
    """`end_state` 의 이어 쓰기 판 — `text` 가 `lead`(앞 구간이 끝난 줄 폭, 쪽 줄 수)에서 이어 쓰였다면 끝난 자리. 줄바꿈·쪽 넘김이 없으면 앞 구간의 줄 폭·줄 수를 이어받는다."""
    if "<05>" in text or not lead or text.startswith(_FRESH):
        return end_state(text, names)
    t = re.sub(r"<1e>.*?<04>\n?", "", text, flags=re.S)
    last = t.rsplit("\n", 1)[-1]
    w = sum(width(x, names) for x in _TOK.findall(last))
    if "\n" in t:
        return w, lead[1] + t.count("\n")
    return lead[0] + w, lead[1]


def worse(a: tuple[int, int] | None, b: tuple[int, int] | None) -> tuple[int, int] | None:
    """두 이어 쓰기 자리 가운데 더 빡빡한 쪽(성분별 큰 값) — 한 조각에 여러 길이 들어올 때 모두에 맞는 조판을 얻는다."""
    if a is None or b is None:
        return a or b
    return max(a[0], b[0]), max(a[1], b[1])


CLAUSE = int(os.environ.get("ED_CLAUSE", "2"))  # 쪽 나눔 — 한 쪽보다 긴 문장이 꼬리 한 줄만 다음 쪽에 남기게 되면 앞 쪽 둘째 줄까지의 마지막 연결어미·쉼표에서 쪽을 끊는다(마스터 10-24 J6 B)
_CONN = ("고", "며", "면", "서", "니", "데", "만", "나", "다가", "도록", "려고", "므로", "라고", "으며", "으니", "으나", "지만", "는데", "인데")  # 연결어미로 끝나는 어절(쉼표 없이도 쉼의 자리)
LINE_CLAUSE = int(os.environ.get("ED_LINECLAUSE", "1"))  # 줄 나눔 — 줄이 넘칠 때 이 줄에서 시작한 절(쉼표·마침표·연결어미 뒤부터)이 한 줄에 다 들어가면 절째 다음 줄로 보낸다(마스터 10-25 「왕자님, / 버려서 에서 끊어야」)
SOFTNL = int(os.environ.get("ED_SOFTNL", "1"))  # 번역 원고에 든 문장 중간 손 개행(줄 맞춤용)은 공백으로 읽고 조판기가 정한다 — 문장 끝·쪽·화자 머리 뒤 개행은 그대로(마스터 10-25 「전체 개행 점검」)
_END_RE = re.compile(r"[.!?…~」』]$")
_CONN_RE = re.compile(r"(?:아서|어서|여서|해서|려서|러서|라서|워서|니까|으니|면서|으며|하며|지만|는데|인데|으나|다가|도록|려고|므로|고|며|면)$")


_CONJ = {"그리고", "하지만", "그러나", "그래서", "게다가", "그러면", "그런데", "그러니", "그렇다면", "그러므로", "따라서", "그렇지만", "그래도", "그러자"}  # 문장 머리 접속어 — 뒤 말에 붙는다(경계 아님)
MIN_LEFT = 20  # 줄·쪽을 끊고 앞에 남는 줄이 이보다 짧으면(낱말 하나 정도) 그 자리에서는 끊지 않는다


_OLD_RULES = False  # 켜면 공용 krwrap 10-28/29 보강(관형형+의존명사 · 관용구 · 이름+호칭 조사꼴 · 「-아 다오」)을 끈다 — `typeset()` 의 쪽·줄 늘어남 판정 기준
_OLD_TITLES = ("군", "양", "씨", "경", "공", "님", "전하", "폐하", "각하")


def _is_new_reason(r: str, b: str) -> bool:
    w = b.rstrip(".,!?…~")
    if r == "관용구":
        return True
    if r == "관형형+의존명사":
        return w.startswith(("자", "리", "데", "법", "대로", "참", "척", "체", "탓", "김", "셈", "모양"))
    if r == "이름+호칭":
        return w not in _OLD_TITLES
    return r == "본용언+보조용언" and w.startswith(("다오", "달라", "달란"))


_NO_GEON = False  # 「건·게·걸」 이음 예외를 끈 조판(창 내용 보존 판정의 기준 — `typeset`)


def _split_reason(a: str, b: str):
    """공용 판정(`krwrap.split_reason`) + 이 게임의 로컬 이음 — 「하고 싶다」 · 「싶어 견디다」(규칙 2-16 f)."""
    r = krwrap.split_reason(a, b)
    if r and _OLD_RULES and _is_new_reason(r, b):
        r = None
    if r == "관형사형 고아" and a.rstrip(".,!?…") in ("건",) and not _NO_GEON:  # 「것은」 줄임 — 관형형이 아니라 명사+조사(「이야기할 수 있는 건 / 바바라님뿐인데」)
        return None
    if r or not a or not b:
        return r
    a2, b2 = a.rstrip(".,!?…"), b.lstrip("「『")
    if a2.endswith("고") and b2.startswith("싶"):
        return "-고 싶다"
    if a2.endswith(("싶어", "싶어서")) and b2.startswith("견"):
        return "싶어 견디다"
    return None


def _bonded(c, words, names) -> bool:
    """후보 자리 앞 어절과 뒤 어절이 본용언+보조용언 같은 한 덩어리면 거기서 쪽을 끊지 않는다."""
    nx = next((x for x in words[c[0] :] if x[0] not in (" ", "\n", "<05>")), None)
    nxp = _plain(nx, names) if nx else None
    return bool(nxp and c[4] and _split_reason(c[4], nxp))


def _bkind(plain: str | None) -> int:
    """줄 나눔 후보의 세기 — 3 문장 끝(. ? ! …) > 2 쉼표(감탄사 「오,」·「칫,」 처럼 두 음절 이하는 제외) > 1 연결어미 > 0 아님(마스터 10-25)."""
    if not plain:
        return 0
    if _END_RE.search(plain):
        return 3
    if plain.endswith(","):
        return 2 if len(plain.rstrip(",")) > 2 else 0
    return 1 if (plain not in _CONJ and _CONN_RE.search(plain)) else 0


RULE = True  # 쪽 나눔 — 문장 단위(아래 `_typeset` 의 `cur`). `tools/sim_pagebreak.py` 가 끄고 켜서 잰다
SPLITS: list = []  # (종류, 어절 색인) — 쪽 사이에서 문장이 갈린 자리(시뮬레이션 계측, 조판 결과엔 영향 없음)


class _Fail(Exception):
    pass


def _typeset_clause(text, names=None, lead=None):
    global LINE_CLAUSE
    if not LINE_CLAUSE:
        return typeset_plain(text, names, lead)
    clause = typeset_plain(text, names, lead)  # 절째 내리는 줄 나눔이 쪽을 늘리면 그 구간은 쓰지 않는다(쪽 수는 그대로)
    LINE_CLAUSE = 0
    try:
        plain = typeset_plain(text, names, lead)
    finally:
        LINE_CLAUSE = 1
    return clause if clause.count("<05>") <= plain.count("<05>") else plain
GLUE_PAIRS: set = set()  # 굳은 [명사+명사] 구(앞 어절, 뒤 어절) — 빌드가 문안 전량에서 구해 넣는다(`compound_pairs`)
_JOSA = "은는이가을를의에도와과로"
_ENDING = set("은는이가을를의에도와과로고며면만다요죠네까니라야지든나서게데기해히")  # 조사·어미·관형형·부사형으로 끝나는 어절은 굳은 구의 앞 마디가 아니다


def compound_pairs(texts) -> set:
    """굳은 [명사+명사] 구 — 앞 어절이 맨 명사(조사가 둘 이상 붙은 꼴이 문안에 있고 조사·어미로 안 끝난다)이고 같은 이음이 문안 전량에 2회 이상(규칙 2-16 e)."""
    grams: dict = {}
    ev: dict = {}
    for t in texts:
        flat = re.sub(r"<[^>]*>", "", t.replace("<05>", "\n\n"))
        for para in flat.split("\n\n"):
            w = para.replace("\n", " ").split()
            for a, b in zip(w, w[1:]):
                grams[(a, b)] = grams.get((a, b), 0) + 1
            for x in w:
                if len(x) >= 3 and x[-1] in _JOSA and re.fullmatch(r"[가-힣]+", x):
                    ev.setdefault(x[:-1], set()).add(x[-1])
    nouns = {x for x, j in ev.items() if len(j) >= 2}
    return {(a, b) for (a, b), n in grams.items() if n >= 2 and a in nouns and a[-1] not in _ENDING and re.fullmatch(r"[가-힣]{2,}", a) and re.fullmatch(r"[가-힣]{2,}", b)}


def _wb(text: str):
    """조판된 문안 → (어절 열, 어절 뒤 끊김 열: '' · 'n'(줄) · 'p'(쪽)). 화자 머리·제어 토큰은 뺀다."""
    t = re.sub(r"<1e>.*?<04>\n?", "", text, flags=re.S)
    t = re.sub(r"<(?!05>)[^>]*>|\{\*[^{}/]+/[^{}/]+\}", "", t)
    parts = re.split(r"(\s+|<05>)", t)
    words, brk = [], []
    for x in parts:
        if not x:
            continue
        if x == "<05>" or x.isspace():
            if words:
                brk[-1] = "p" if "<05>" in x else (brk[-1] or ("n" if "\n" in x else ""))
        else:
            words.append(x)
            brk.append("")
    return words, brk


def _noncut(w: str) -> bool:
    """쪽 경계를 두면 안 되는 어절 — 관형어(관형형 ㄴ·ㄹ 받침·「의」)·목적어(을/를)·주어/주제어(이/가/은/는) 뒤. 절 경계·부사어(에서·에게서·로 …) 뒤는 된다."""
    if w[-1:] in ".!?…":  # 문장 끝(「~한 거라고.」)은 절 경계다 — 쪽을 끊어도 된다
        return False
    w = w.rstrip(".,!?…」』")
    if w.endswith("라고"):  # 인용 「~라고」 는 뒤의 서술어(적힌·말하는)에 걸린다 — 절 경계로 안 친다
        return True
    if not w or _bkind(w):
        return False
    c = w[-1]
    if c in "을를이가의은는":
        return True
    return "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 in (4, 8)


def regress(old: str, new: str) -> list:
    """규칙이 원판 조판보다 **나쁘게 만든** 끊김(규칙 2-16 f) — 원판엔 없던 끊김 가운데 보조용언·의존명사·관형사 고아(`krwrap.split_reason`)에 걸리는 것 +
    원판에서 한 줄이던 문장이 갈린 것. 어절 열이 다르면(문안이 바뀜) 비교하지 않는다."""
    wo, bo = _wb(old)
    wn, bn = _wb(new)
    if wo != wn:
        return []
    bad = []
    for i in range(len(wn) - 1):
        if bn[i] and not bo[i] and _split_reason(wn[i].replace(NBSP, " "), wn[i + 1]):
            bad.append((i, "bonded"))
    for i in range(len(wn) - 1):  # 쪽 경계 — 전에 문장 끝이던 쪽 경계를 없애 문장 중간으로 옮기거나, 절 경계도 아닌 자리(관형어·목적어·주어 뒤)에 새 쪽 경계를 만들지 않는다
        if bo[i] == "p" and wo[i][-1:] in ".!?…」』" and bn[i] != "p":
            bad.append((i, "pagemove"))
        if bn[i] == "p" and bo[i] != "p" and _noncut(wn[i]):
            bad.append((i, "pagecut"))
    pc_o = sum(1 for i in range(len(wo) - 1) if bo[i] == "p" and (not _bkind(wo[i]) or _split_reason(wo[i], wo[i + 1])))  # 절 경계가 아닌(또는 보조용언 등이 갈리는) 자리의 쪽 경계 수 — 늘면 거부
    pc_n = sum(1 for i in range(len(wn) - 1) if bn[i] == "p" and not _bkind(wn[i]))
    if pc_n > pc_o:
        bad.append((0, "pageclause"))
    nc_o = sum(1 for i in range(len(wo) - 1) if bo[i] and not _bkind(wo[i]))  # 줄 끝이 절 경계(문장 끝·쉼표·연결어미)가 아닌 줄 수 — 늘면 거부(「있으면 좋으련만⏎」 → 「있으면⏎좋으련만」)
    nc_n = sum(1 for i in range(len(wn) - 1) if bn[i] and not _bkind(wn[i]))
    if nc_n > nc_o and sum(1 for b in bn if b) >= sum(1 for b in bo if b):  # 줄이 줄어 끝이 준 것은 퇴행이 아니다
        bad.append((0, "clause"))
    start = 0
    for i, w in enumerate(wn):
        if w[-1:] in ".!?…」』" or i == len(wn) - 1:
            if start < i and not any(bo[j] for j in range(start, i)) and any(bn[j] for j in range(start, i)):
                bad.append((i, "split"))
            start = i + 1
    return bad


def _orphan(text: str) -> bool:
    """쪽이 둘 이상인데 마지막 쪽이 낱말 하나뿐이고 앞 쪽이 문장 끝이 아니다(마스터 10-26 ① 창 분배)."""
    pages = [[l for l in re.sub(r"<[^>]*>", "", p).split("\n") if l.strip()] for p in re.sub(r"<1e>.*?<04>\n?", "", text, flags=re.S).split("<05>")]
    pages = [p for p in pages if p]
    return len(pages) > 1 and len(pages[-1]) == 1 and " " not in pages[-1][0].strip() and pages[-2][-1].strip()[-1:] not in ".!?…~」』"


def _midone(text: str) -> int:
    """쪽 끝 줄이 낱말 하나이고 문장 끝이 아닌 쪽 수(문장 중간 한 낱말 쪽)."""
    pages = [[l for l in re.sub(r"<[^>]*>", "", p).split("\n") if l.strip()] for p in re.sub(r"<1e>.*?<04>\n?", "", text, flags=re.S).split("<05>")]
    pages = [p for p in pages if p]
    return sum(1 for p in pages[:-1] if " " not in p[-1].strip() and p[-1].strip()[-1:] not in ".!?…~」』")


def rebalance(text: str, src: str = "", lead=None) -> str:
    """창 분배(마스터 10-26 ①) — 조판기가 쪽을 나눈 구간(원본 손 쪽나눔·화자 머리·이어 쓰기가 없는 구간)에서 창 줄 수 차가 2 이상이면 쪽 경계를 한 줄씩 옮겨 고르게 한다.
    제약: 문장 끝이던 쪽 경계는 안 옮기고, 새 쪽 경계는 문장 끝·절 경계(`_bkind`)에서만 둔다(관형어·목적어·주어 뒤에서 쪽을 끊지 않는다). 창 수는 그대로."""
    if lead or "<05>" in src or re.search(r"<(1e|08|02|04)\b", src) or "<05>" not in text or text.startswith("\n") or "<1e>" in text:
        return text
    pages = [p.split("\n") for p in text.split("<05>")]
    if pages[-1] == [""] or any(not p or p == [""] for p in pages):
        return text

    def kind(line: str) -> int:
        w = re.sub(r"<[^>]*>|\{\*[^{}/]+/[^{}/]+\}", "", line).split()
        return _bkind(w[-1]) if w else 0

    for _ in range(8):
        r = [len(p) for p in pages]
        if max(r) - min(r) < 2:
            break
        moved = False
        for i in range(len(pages) - 1):
            a, b = pages[i], pages[i + 1]
            if kind(a[-1]) == 3:
                continue  # 문장 끝 쪽 경계는 둔다
            if len(a) >= len(b) + 2 and kind(a[-2]) > 0 and len(b) < 3:
                b.insert(0, a.pop())
                moved = True
                break
            if len(b) >= len(a) + 2 and kind(b[0]) > 0 and len(a) < 3:
                a.append(b.pop(0))
                moved = True
                break
        if not moved:
            break
    return "<05>".join("\n".join(p) for p in pages)


def refit_tail(text: str, names=None) -> str:
    """마지막 두 쪽의 줄을 다시 감아 마지막 쪽이 한 어절로 남지 않게 한다(마스터 10-26 ① 창 분배 — 관형어·목적어·주어 뒤 쪽 끊기는 안 된다).
    쪽 경계는 문장 끝·절 경계·부사어 뒤에만, 줄 끝은 보조용언 등이 갈리지 않는 자리에만 둔다. 마땅한 감기가 없으면 그대로 둔다."""
    if text.count("<05>") < 1:
        return text
    closer = "<05>" if text.endswith("<05>") else ""  # 끝이 쪽 넘김으로 닫힌 문안 — 마지막 쪽은 그 앞 쪽
    pages = text[: len(text) - len(closer)].split("<05>")
    if len(pages) < 2:
        return text
    pre = ""
    if len(pages) == 2 and pages[0].startswith("<04>\n"):  # 화자 머리 뒷부분(이어 쓰기 조각 앞)은 폭에 안 센다
        pre, pages[0] = "<04>\n", pages[0][5:]
    elif len(pages) == 2 and (hm := re.match(r"<1e>[^\n]*?<04>\n", pages[0])):  # 화자 머리 줄(이름 변수가 든 것 포함)은 폭에 안 센다
        pre, pages[0] = hm.group(0), pages[0][hm.end() :]
    elif "<1e>" in "".join(pages[-2:]):
        return text
    P, Q = pages[-2].split("\n"), pages[-1].split("\n")
    if len(Q) != 1 or " " in Q[0].strip():
        return text
    if re.search(r"<[^E1][^>]*>", "".join(P + Q)) or any(l.startswith(" ") for l in P + Q) or not P[0].strip():
        return text
    W = " ".join(P + Q).split(" ")
    if len(W) < 3 or P[-1].strip()[-1:] in ".!?…~」』":
        return text

    def wid(ws):
        return sum(width(t, names) for w in ws for t in _TOK.findall(w)) + 2 * (len(ws) - 1)

    def plain(w):
        return _plain([w], names) if _plain([w], names) is not None else re.sub(r"<[^>]*>", "", w)

    def bonded(i):  # W[i] / W[i+1] 사이를 가르면 안 되는가
        a, b = plain(W[i]), plain(W[i + 1])
        return bool(a and b and _split_reason(a, b))

    n = len(W)
    best = []

    def lines_from(i, k, acc):  # i 번째 어절부터 k 줄로 채우는 모든 감기
        if k == 0:
            if i == n:
                yield list(acc)
            return
        for j in range(i + 1, n + 1):
            if wid(W[i:j]) > LINE_UNITS:
                break
            if j < n and bonded(j - 1):
                continue
            acc.append((i, j))
            yield from lines_from(j, k - 1, acc)
            acc.pop()

    cands = []
    for kp in (1, 2, 3):
        for kq in (2, 1, 3):
            if kq > 3:
                continue
            for lay in lines_from(0, kp + kq, []):
                cut = lay[kp - 1][1]  # 첫 쪽 마지막 어절 다음 색인
                tail = n - cut
                if tail < 2 and kq == 1:
                    continue
                if tail < 2:
                    continue
                last = plain(W[cut - 1])
                if _noncut(last):
                    continue
                single = sum(1 for a, b in lay if b - a == 1)
                clause = sum(1 for a, b in lay[:-1] if _bkind(plain(W[b - 1])) == 0)
                cands.append((kp + kq, single, 0 if _bkind(last) else 1, clause, lay, kp))
    if not cands:
        return text
    cands.sort(key=lambda c: c[:4])
    _, _, _, _, lay, kp = cands[0]
    out = ["\n".join(" ".join(W[a:b]) for a, b in lay[:kp]), "\n".join(" ".join(W[a:b]) for a, b in lay[kp:])]
    if pre:
        out[0] = pre + out[0]
    return "<05>".join(pages[:-2] + out) + closer


def regress_net(old: str, new: str) -> list:
    """`regress` 에서 창 분배를 나아지게 한 이동(쪽 끝 고아·문장 중간 한 낱말 쪽을 줄임)의 절 경계·쪽 자름 퇴행은 뺀 것(그 둘이 더 나쁘다 — 마스터 10-26 ① 창 분배 > ② 가독성)."""
    r = regress(old, new)
    gain = (_orphan(old) and not _orphan(new)) or _midone(new) < _midone(old)
    return [x for x in r if x[1] != "clause"] if gain else r


def _base(text, names=None, lead=None):
    """원판 조판(규칙 끔) — 퇴행 판정의 기준."""
    global CLAUSE, LINE_CLAUSE, SOFTNL, _NO_GEON
    saved = (CLAUSE, LINE_CLAUSE, SOFTNL, _NO_GEON)
    try:
        CLAUSE = LINE_CLAUSE = SOFTNL = 0
        _NO_GEON = True  # 원판 조판 기준 — 「건·게·걸」 이음 예외도 끈다(퇴행 판정이 새 예외까지 기준으로 삼지 않게)
        return _typeset_glue(text, names, lead)
    finally:
        CLAUSE, LINE_CLAUSE, SOFTNL, _NO_GEON = saved


_NO_CARRY = False  # 본용언+보조용언 붙임(2-6)을 끈 조판 — 조판 여유가 없을 때만 쓴다(규칙 2-17, 마스터 11-05)
LEANS: list = []  # 붙임을 포기해 원문 창 수를 지킨 문안(진단용 — `check_layout` 이 퇴행 판정에서 빼고 한도로 센다)


def typeset(text, names=None, lead=None):
    """붙임(2-6 본용언+보조용언)을 지키느라 쪽이 늘면 붙임을 끈 조판으로 돌린다 — 원문 한 창을 조판 규칙으로 둘로 가르지 않는다
    (글은 줄이지 않고 줄 배치만 바꾼다. 규칙 2-17: 「2-6 붙임은 조판 여유가 있을 때만 지킨다」, 마스터 11-05)."""
    global _NO_CARRY
    r = _typeset_rules(text, names, lead)
    if lead or _NO_CARRY or _NO_GEON or _OLD_RULES:
        return r
    _NO_CARRY = True
    try:
        lean = _typeset_rules(text, names, lead)
    finally:
        _NO_CARRY = False
    if lean.count("<05>") < r.count("<05>"):
        LEANS.append(text)
        r = lean
    return _sentence_break(r, text)


def no_empty_window(text, names=None, lead=None, fn=None):
    """`typeset` 결과에 내용 없는 쪽(`<05><05>`)이 끼면 — 쪽 끝 앞 개행이 줄 배치와 겹친 것(11-06 $C83508, ▼만 기다리는 빈 대사창) — 그 개행만 떼고 다시 조판한다."""
    fn = fn or typeset
    out = fn(text, names, lead)
    if "\n<05>" in text and "<05><05>" in re.sub(r"(<05>)+$", "", out):
        out = fn(re.sub(r"\n+(<05>)", r"\1", text), names, lead)
    return out


_SENT_LINE_END = re.compile(r"[.!?…~」』]+\)?$")


def _flat(s: str) -> str:
    return re.sub(r"\s|<[^>]*>", "", s)


def _sentence_break(out: str, text: str) -> str:
    """조판기가 낸 쪽 경계가 문장 한가운데면 꼬리 문장을 다음 쪽 머리로 옮겨 문장 경계에서 나눈다(규칙 2-17: 창이 늘면 문장 경계에서 — 마스터 11-05).
    원문이 가른 쪽 경계는 안 건드린다. 쪽 끝 줄들이 앞 문장 끝 줄 뒤에 통째로 이어진 꼬리이고, 옮긴 뒤 다음 쪽이 3줄을 안 넘을 때만."""
    pages = out.split("<05>")
    if len(pages) < 2:
        return out
    src_cum, n = set(), 0
    for p in text.removesuffix("<05>").split("<05>"):
        n += len(_flat(p))
        src_cum.add(n)
    cum, moved = 0, False
    for i in range(len(pages) - 1):
        cum += len(_flat(pages[i]))
        if cum in src_cum or "<" in pages[i + 1][:1]:
            continue
        a, b = pages[i].split("\n"), pages[i + 1].split("\n")
        if _SENT_LINE_END.search(a[-1].rstrip()) or any("<" in x or "{" in x for x in a[1:] + b):
            continue  # 쪽이 문장 끝으로 끝났다 · 변수·토큰이 든 쪽은 폭을 몰라 건드리지 않는다
        k = next((j for j in range(len(a) - 2, -1, -1) if _SENT_LINE_END.search(a[j].rstrip())), None)
        if k is None or k < 0:
            continue
        tail = a[k + 1 :]
        if len(tail) + len(b) > PAGE_ROWS or not "".join(a[: k + 1]).strip():
            continue
        pages[i], pages[i + 1] = "\n".join(a[: k + 1]), "\n".join(tail + b)
        moved = True
    return "<05>".join(pages) if moved else out


def _typeset_rules(text, names=None, lead=None):
    """공용 묶음 규칙(10-28/29 보강)은 「지키면 좋은 것」이다 — 지키느라 이 문안의 쪽·줄이 늘면 그 문안은 보강 전 규칙으로 되돌린다
    (쪽이 늘어 문장 한가운데서 끊기는 쪽이 더 나쁘다, 규칙 2-16 · 마스터 10-29)."""
    out = _typeset_final(text, names, lead)
    global _OLD_RULES
    if _OLD_RULES:
        return out
    _OLD_RULES = True
    try:
        old = _typeset_final(text, names, lead)
    finally:
        _OLD_RULES = False
    if old != out and (out.count("<05>") > old.count("<05>") or out.count("\n") > old.count("\n")):
        FALLBACKS.append(text)
        return _keep_windows(old, text, names, lead)
    return _fresh_sentence(_keep_windows(out, text, names, lead), lead)


_SENT_END = re.compile(r"[.!?…~」』]+\)?(?= |$)")


def _fresh_sentence(out: str, lead) -> str:
    """한 줄에 나올 수 있는 문장은 한 줄로(규칙 2-10, 마스터 10-10) — 줄 가운데서 시작해 다음 줄로 넘어가는 문장이 한 줄(50단위)에 들어가면
    새 줄에서 시작한다. 쪽·줄 수는 안 바뀐다(다음 줄에 앞머리를 합쳐 한 줄에 들어갈 때만). 이름·호출 변수나 다른 토큰이 든 줄, 앞 구간에 이어 붙는 구간은 폭을 몰라 건드리지 않는다."""
    if lead or "<E" in out or "{" in out or "<10" in out:
        return out
    pages = out.split("<05>")
    for pi, pg in enumerate(pages):
        pre = ""
        m = re.match(r"(?:<1e>[^\n]*?<04>\n)", pg)
        if m:
            pre, pg = pg[: m.end()], pg[m.end() :]
        ls = pg.split("\n")
        for i in range(len(ls) - 1):
            a, b = ls[i], ls[i + 1]
            if "<" in a or "<" in b or not a.strip() or not b.strip():
                continue
            ends = list(_SENT_END.finditer(a))
            if not ends or ends[-1].end() >= len(a.rstrip()):
                continue  # 줄이 문장 끝으로 끝났거나 문장 끝이 없다
            head = a[ends[-1].end() :].lstrip()
            mm = _SENT_END.search(b)
            if not head or not mm:
                continue
            if sum(width(c) for c in head + " " + b[: mm.end()]) > LINE_UNITS:
                continue
            nb = head + " " + b
            if sum(width(c) for c in nb) > LINE_UNITS:
                continue
            ls[i], ls[i + 1] = a[: ends[-1].end()], nb
        pages[pi] = pre + "\n".join(ls)
    return "<05>".join(pages)


def _sig(t: str) -> list:
    return [re.sub(r"[\s]|<[^>]*>", "", p) for p in t.split("<05>")]


def _keep_windows(out, text, names, lead):
    """창(쪽)마다 원문 창 내용을 그대로 둔다 — 창 사이 낱말 재분배는 마지막 창 고아 어절을 풀 때만 쓴다(규칙 2-17, 마스터 10-31).
    「건」 이음 예외는 예외를 끈 조판이 마지막 창 고아일 때만 쓴다(아니면 옛 조판 그대로)."""
    global _NO_GEON
    if _NO_GEON:
        return out
    _NO_GEON = True
    try:
        prev = typeset(text, names, lead)
    finally:
        _NO_GEON = False
    if prev != out and not _orphan(prev):  # 이어 쓰기 구간은 한 줄 채움 차이가 뒤 구간의 쪽 경계까지 옮기므로 줄 단위 차이도 되돌린다
        return prev
    return out


FALLBACKS: list = []  # 보강 규칙을 포기하고 보강 전 조판으로 돌린 문안(진단용)


def _typeset_final(text, names=None, lead=None):
    out = _typeset_guard(text, names, lead)
    if REBALANCE:
        base = None
        r = rebalance(out, text, lead)
        if r != out:
            base = _base(text, names, lead)
            out = r if not regress_net(base, r) else out
        if not lead and _orphan(out) and re.sub(r"\s", "", out.removesuffix("<05>").rsplit("<05>", 1)[-1]) != re.sub(r"\s", "", text.removesuffix("<05>").rsplit("<05>", 1)[-1]):  # 마지막 쪽 경계를 조판기가 만들었을 때만(원본 손 쪽나눔은 둔다)
            r = refit_tail(out, names)
            if not _orphan(r):
                base = base or _base(text, names, lead)
                if not regress_net(base, r):
                    out = r
    return out


REBALANCE = int(os.environ.get("ED_REBALANCE", "1"))  # 창 분배(쪽 경계를 줄 단위로 옮겨 창 줄 수를 고르게)


def _typeset_guard(text, names=None, lead=None):
    """줄·쪽 나눔 + 굳은 명사구 묶기 — 묶은 꼴이 줄·쪽 수를 안 늘릴 때만 쓴다(늘면 묶지 않는다).
    규칙이 원판 조판보다 나쁜 끊김을 만들면(`regress`) 그 이동은 거부하고 덜 공격적인 길로 물러난다(규칙 2-16 f)."""
    global CLAUSE, LINE_CLAUSE, SOFTNL
    cand = _typeset_glue(text, names, lead)
    if not (CLAUSE or LINE_CLAUSE or SOFTNL):
        return cand
    saved = (CLAUSE, LINE_CLAUSE, SOFTNL)
    try:
        CLAUSE = LINE_CLAUSE = SOFTNL = 0
        base = _typeset_glue(text, names, lead)  # 원판 조판
    finally:
        CLAUSE, LINE_CLAUSE, SOFTNL = saved
    def bad(a):
        return regress_net(base, a)

    if not bad(cand):
        return cand
    for flags in ((saved[0], 0, saved[2]), (0, 0, saved[2]), (0, 0, 0)):
        try:
            CLAUSE, LINE_CLAUSE, SOFTNL = flags
            alt = _typeset_glue(text, names, lead)
        finally:
            CLAUSE, LINE_CLAUSE, SOFTNL = saved
        if not bad(alt) and alt.count("<05>") <= base.count("<05>"):
            return alt
    return base


def _typeset_glue(text, names=None, lead=None):
    base = _typeset_clause(text, names, lead)
    pairs = [(a, b) for a, b in GLUE_PAIRS if re.search(re.escape(a) + r"[ \n]" + re.escape(b), text)]
    if not pairs:
        return base
    g = text
    for a, b in pairs:
        g = re.sub(re.escape(a) + r"[ \n]" + re.escape(b), a + NBSP + b, g)
    alt = _typeset_clause(g, names, lead)
    return alt if alt.count("\n") <= base.count("\n") and alt.count("<05>") <= base.count("<05>") else base


def typeset_plain(text, names=None, lead=None):
    skip: set = set()
    while True:
        del SPLITS[:]
        try:
            return _typeset(text, names, lead, skip)
        except _Fail as e:
            skip.add(e.args[0])


_END = set(".!?…」』~")
_FRESH = ("<1e>", "\n", "<08>", "<02>", "<05>")  # 맨 앞이 화자 머리·개행·쪽 넘김이면 새 자리에서 시작한다 — 앞 구간 줄에 안 이어진다


def _typeset(text: str, names: dict | None, lead: tuple[int, int] | None, skip: set) -> str:
    """쪽 나눔은 문장 단위다(마스터 「이어지는 어절은 한 줄에」의 쪽 단위 적용, 10-21): 줄이 넘쳐 쪽이 넘어가는 자리가 문장 한가운데이고
    그 문장이 새 쪽에서 시작하면 한 쪽(3줄)에 들어가면, 문장 앞에서 쪽을 넘긴다. 한 쪽보다 긴 문장은 그대로 둔다(`skip` — 다시 돌린다).
    손 개행이 만드는 쪽 넘김은 번역자가 정한 자리라 건드리지 않는다."""
    """줄바꿈·쪽 넘김을 넣은 문안. 이미 든 `⏎`/`<05>` 는 강제로 지킨다.
    `lead` = (앞 구간이 끝난 줄 폭, 쪽에 쓴 줄 수) — 앞 구간 끝에 이어 붙는 구간(이름 변수 뒤 조각)은 그 줄의 남은 폭에서 시작한다."""
    # 화자 머리(`<1e>이름<04>` + 뒤 개행)와 맨 앞 개행은 폭·줄 수에 안 센다 — 자리표시자로 바꿨다가 되돌린다
    lead_ok = bool(lead) and not text.startswith(_FRESH)  # 맨 앞이 화자 머리·개행이면 새 줄에서 시작한다
    heads: list[str] = []

    def hold(m):
        heads.append(m.group(0))
        return f"<H{len(heads) - 1}>"

    text = re.sub(r"<1e>.*?<04>\n?", hold, text, flags=re.S)
    if text.startswith("\n"):
        heads.append("\n")
        text = f"<H{len(heads) - 1}>" + text[1:]
    if SOFTNL:

        def soft(m):  # 문장 끝·쪽 넘김·화자 머리 둘레의 개행은 번역자가 정한 자리라 둔다 — 구간 맨 끝 개행도 둔다(뒤에 이어지는 호출 조각·이름의 폭을 이 조판기가 모른다 — 「몬스터쪽을」이 낱말 가운데서 꺾였다)
            i = m.start()
            before, after = text[:i], text[m.end() :]
            if not before or not after or before[-1] in ".!?…~」』\n" or re.search(r"<(?:0[0-9a-f]|1[0-9a-f])>$|<H\d+>$", before) or after.startswith(("<H", "<05>", "\n")):
                return "\n"
            return " "

        text = re.sub(r"\n", soft, text)
    text = _glue(text)
    toks = _TOK.findall(text)
    # 어절 묶음: 공백으로 끊기는 연속 토큰
    words: list[list[str]] = []
    cur: list[str] = []
    for t in toks:
        if t in (" ", "\n", "<05>"):
            if cur:
                words.append(cur)
                cur = []
            words.append([t])
        else:
            cur.append(t)
    if cur:
        words.append(cur)
    starts = set()
    prev_end = True
    for i, w in enumerate(words):
        if w[0] in (" ", "\n"):
            continue
        if w[0] == "<05>":
            prev_end = True
            continue
        if prev_end:
            starts.add(i)
        pl = re.sub(r"<[^>]*>|\{\*[^{}/]+/[^{}/]+\}", "", "".join(w))
        prev_end = bool(pl) and pl[-1] in _END
    first_start = min(starts) if starts else -1  # 앞 구간에 이어 붙는 첫 문장은 쪽 자리를 모른다 — 그 뒤 문장부터 문장 단위 쪽 나눔을 쓴다
    cur = None  # (어절 색인, out 길이, 줄 폭, 쪽 줄 수) — 지금 문장의 시작 자리
    tried: set = set()
    out: list[str] = []
    u = 0  # 현재 줄 폭
    rows = 0  # 이 쪽에 이미 쓴 완결 줄 수
    if lead_ok:
        u, rows = lead
    glued = bool(lead_ok and u and not text[:1].isspace())  # 앞 구간 글자에 바로 붙는 첫 어절은 줄을 바꾸지 않는다(이름과 조사가 갈린다)
    header = False

    def newline():
        nonlocal u, rows
        out.append("\n")
        u = 0
        rows += 1
        linewords.clear()

    def page():
        nonlocal u, rows
        out.append("<05>")
        u = 0
        rows = 0
        linewords.clear()
        clauses.clear()
        anyb.clear()

    soften = False  # (CLAUSE) 연결어미에서 쪽을 끊은 뒤 그 문장 끝까지는 번역의 손 개행을 공백으로 읽는다 — 옛 줄 나눔대로 두면 새 쪽 첫머리에 짧은 줄이 남는다
    anyb: list = []  # (CLAUSE==2) 쪽 안 모든 어절 뒤 자리 — 연결어미·쉼표 자리가 없을 때 쓰는 후보(붙여 써야 할 덩어리를 가르지 않는 곳만)
    clauses: list = []  # 이 쪽에서 문장 중간 연결어미·쉼표로 끝난 어절 뒤의 자리 (다음 어절 색인, out 길이, 줄 폭, 쪽 줄 수) — 꼬리 한 줄 방지(CLAUSE)용
    started = False
    linewords: list[tuple[int, list, int, str | None]] = []  # 이 줄의 낱말들 (out 색인, 토큰, 폭, 글자) — 뒤 낱말과 한 덩어리면 함께 다음 줄로 보낸다
    def tail_width(start: int) -> int:
        n = 0
        for x in words[start:]:
            if x[0] == "<05>":
                break
            if x[0] in (" ", "\n"):  # 손 개행도 문장 안이면 공백으로 센다(번역 원고는 줄마다 `\n` 이 들어 있다)
                n += 2
                continue
            n += sum(width(t, names) for t in x)
            px = _plain(x, names) or ""
            if px and px[-1] in _END:
                break
        return n

    def clause_break(nxt: int) -> bool:
        """쪽이 넘어가는 자리(다음에 새 쪽 맨 앞에 올 어절 색인 `nxt`)에서 문장이 갈리고 그 뒤 남는 글이 한 줄 이하(= 꼬리 한 줄)이면,
        이 쪽에서 문장 중간 연결어미·쉼표로 끝난 자리 가운데 「뒤에 남는 글이 한 줄(50단위) 넘게」 남는 **가장 늦은** 자리에서 쪽을 끊는다 — 앞 쪽에 한 줄 이상은 남긴다."""
        nonlocal wi, soften
        if linewords and linewords[-1][3] and linewords[-1][3][-1] in _END:
            return False
        if tail_width(nxt) > LINE_UNITS:
            return False
        cand = [c for c in clauses if c[3] >= 1 and c[2] >= MIN_LEFT and c[0] != nxt and tail_width(c[0]) > LINE_UNITS and not _bonded(c, words, names)]
        if not cand and CLAUSE == 2:
            for c in anyb:
                nx = next((x for x in words[c[0] :] if x[0] not in (" ", "\n", "<05>")), None)
                nxp = _plain(nx, names) if nx else None
                if c[3] >= 1 and c[2] >= MIN_LEFT and c[0] != nxt and tail_width(c[0]) > LINE_UNITS and nxp and not _split_reason(c[4], nxp):
                    cand = [c[:4]]
        if not cand:
            return False
        ci, olen, _u, _rows = cand[-1][:4]
        del out[olen:]
        while out and out[-1] == " ":
            out.pop()
        page()
        soften = True
        wi = ci - 1
        return True

    wi = -1
    while wi + 1 < len(words):
        wi += 1
        w = words[wi]
        t0 = w[0]
        if wi in starts:
            cur = (wi, len(out), u, rows)
        if t0 == "\n" and linewords and linewords[-1][3]:
            # 번역에 손으로 넣은 개행이 한 덩어리(본용언+보조용언 등)를 가르면 공백으로 읽는다 — 어디서 끊을지는 조판기가 정한다
            nxt = next((x for x in words[wi + 1 :] if x[0] not in (" ", "\n")), None)
            if nxt and nxt[0] != "<05>" and _plain(nxt, names) and _split_reason(linewords[-1][3], _plain(nxt, names)):
                w = [" "]
                t0 = " "
        if soften and t0 == "\n":
            w = [" "]
            t0 = " "
        if t0 == "\n":
            if rows + 1 >= PAGE_ROWS:
                # (CLAUSE) 손 개행이 쪽을 넘기는 자리도 문장 단위 규칙을 건다 — 문장이 이 쪽 가운데서 시작해 한 쪽에 들어가면 문장 앞에서 쪽을 넘긴다(기존엔 줄 넘침 쪽만 걸었다)
                if CLAUSE and RULE and cur and cur[0] not in skip and cur[0] != wi and not (cur[2] == 0 and cur[3] == 0) and not (lead_ok and cur[0] == first_start) and linewords and linewords[-1][3] and linewords[-1][3][-1] not in _END and tail_width(wi + 1) > 0:
                    if cur[0] in tried:
                        raise _Fail(cur[0])
                    tried.add(cur[0])
                    del out[cur[1] :]
                    while out and out[-1] == " ":
                        out.pop()
                    if out and out[-1] == "\n":
                        out.pop()
                    page()
                    wi = cur[0] - 1
                    continue
                if CLAUSE and clauses and clause_break(wi + 1):
                    continue
                if linewords and not (linewords[-1][3] and linewords[-1][3][-1] in _END):
                    SPLITS.append(("hand", wi))
                page()  # 강제 개행이 쪽을 넘기면 쪽 넘김으로
            else:
                newline()
            continue
        if t0 == "<05>":
            soften = False
            page()
            continue
        if t0 == " ":
            if u == 0 and (out or heads):  # 줄 첫 공백 금지 — 단 문안 맨 앞은 앞 구간 끝의 이름 변수에 이어 붙는 자리라 남긴다
                continue
            if u + 2 > LINE_UNITS:
                continue
            out.append(" ")
            u += 2
            continue
        ww = sum(width(t, names) for t in w)
        # 화자 머리 `<1e>…<04>` 는 폭을 세지 않고 뒤 개행도 쪽 줄 수에 안 센다(맨 앞일 때만)
        started = True
        if ww > LINE_UNITS:  # 한 어절이 한 줄보다 길면 글자 단위로
            for t in w:
                wt = width(t, names)
                if u + wt > LINE_UNITS:
                    newline()
                out.append(t)
                u += wt
            continue
        if glued:
            glued = False
            out.extend(w)
            u += ww
            continue
        if u + ww > LINE_UNITS:
            # 앞 공백 제거 후 줄바꿈(쪽이 차면 쪽 넘김)
            if rows + 1 >= PAGE_ROWS and RULE and cur and cur[0] != wi and cur[0] not in skip and not (cur[2] == 0 and cur[3] == 0) and not (lead_ok and cur[0] == first_start):
                if cur[0] in tried:
                    raise _Fail(cur[0])
                tried.add(cur[0])
                del out[cur[1] :]
                while out and out[-1] == " ":
                    out.pop()
                if out and out[-1] == "\n":
                    out.pop()
                page()
                wi = cur[0] - 1
                continue
            if CLAUSE and rows + 1 >= PAGE_ROWS and clauses and clause_break(wi):
                continue
            plain = _plain(w, names)
            carry: list = []
            if plain:  # 본용언+보조용언 등 — 앞 낱말(들)을 함께 다음 줄로(`사` / `오라고` → `사 오라고`, `해 줄 거야`)
                k, first = len(linewords), plain
                while k > 1 and not _NO_CARRY and linewords[k - 1][3] and _split_reason(linewords[k - 1][3], first):
                    k -= 1
                    first = linewords[k][3]
                if k < len(linewords) and sum(x[2] + 2 for x in linewords[k:]) + ww <= LINE_UNITS:
                    carry = linewords[k:]
                    del out[carry[0][0] :]
            if LINE_CLAUSE and len(linewords) > 1:
                for kind in (3, 2, 1):  # 센 경계부터 — 같은 줄에 문장 끝이 있으면 거기서 먼저 끊는다
                    kk = next((j for j in range(len(linewords) - 1, 0, -1) if _bkind(linewords[j - 1][3]) == kind), None)
                    if kk is None or kk >= len(linewords) or sum(x[2] + 2 for x in linewords[:kk]) - 2 < MIN_LEFT:
                        continue
                    run = sum(x[2] + 2 for x in linewords[kk:]) + ww
                    for x in words[wi + 1 :]:
                        if x[0] in ("\n", "<05>"):
                            break
                        if x[0] != " ":
                            run += 2 + sum(width(t, names) for t in x)
                            if _bkind(_plain(x, names)):
                                break
                    if run <= LINE_UNITS:
                        if not carry or kk < linewords.index(carry[0]):
                            carry = linewords[kk:]
                            del out[carry[0][0] :]
                        break
            while out and out[-1] == " ":
                out.pop()
            if rows + 1 >= PAGE_ROWS:
                if wi not in starts:
                    SPLITS.append(("auto-long" if (cur and cur[0] in skip) else "auto-pgstart" if (cur and cur[2]==0 and cur[3]==0) else "auto-other", wi))
                page()
            else:
                newline()
            u = 0
            for x in carry:
                linewords.append((len(out), x[1], x[2], x[3]))
                out.extend(x[1])
                out.append(" ")
                u += x[2] + 2
        # 줄 머리 부호 고아 방지는 어절 단위라 자연히 지켜진다
        linewords.append((len(out), w, ww, _plain(w, names)))
        out.extend(w)
        u += ww
        if soften and (_plain(w, names) or "")[-1:] in _END:
            soften = False
        if CLAUSE == 2 and linewords:
            anyb.append((wi + 1, len(out), u, rows, _plain(w, names) or ""))
        if CLAUSE:
            pw = _plain(w, names) or ""
            if pw and pw[-1] not in _END and (pw.endswith(",") or pw.rstrip(",").endswith(_CONN)):
                clauses.append((wi + 1, len(out), u, rows, pw))
    s = "".join(out)
    return re.sub(r"<H(\d+)>", lambda m: heads[int(m.group(1))], s).replace(NBSP, " ")


if __name__ == "__main__":
    import sys

    print(typeset(sys.argv[1] if len(sys.argv) > 1 else "그 얘긴 벌써 몇 번이나 들었어. 이제 그만 시시한 놀이는 그만두십시오. 한동안 공부할 시간을 못 냈으니 오늘부터는 그만큼 빡빡하게 해 주셔야겠습니다."))
