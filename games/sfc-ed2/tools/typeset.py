"""sfc-ed2 대사 조판 — 한국어 문안을 대사창 규격(줄 폭 50단위 · 쪽당 3줄)에 맞춰 줄바꿈·쪽 넘김을 넣는다.

규격(대사 출력기 `$C0:A9F5` 와 에뮬 실측 2026-10-12):
  · 글자 폭 단위: 전각(2바이트) 3 · 반각(1바이트·공백) 2 — 한 줄은 **50단위**(= 200px)까지(전각 16자 + 반각 1칸)
  · 한 쪽 = 본문 3줄(화자 이름 줄은 따로 한 줄 더 붙는다). 넘치면 `<05>`(키 대기 + 쪽 지우기)
번역 문안 표기: `⏎`(실제 개행)은 강제 줄바꿈, `<05>` 는 강제 쪽 넘김, 그 밖의 `<..>` 는 폭 0 제어. 어절(공백) 단위로 끊고(규칙 2-6),
줄 첫머리에 부호만 넘기지 않으며(2-3), 줄 첫 공백을 두지 않는다(2-5). 화자 머리(`<1e>이름<04>` + 개행)는 쪽 줄 수에 안 센다.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from text import krwrap  # 줄바꿈 금지 판정(본용언+보조용언 등)의 정본 — 규칙을 다시 짓지 않는다(DRY)

LINE_UNITS = 50
PAGE_ROWS = 3
_TOK = re.compile(r"<[^>]*>|\{\*[^{}/]+/[^{}/]+\}|\n|.", re.S)
_PUNCT = set(".,!?…」』)~:;")


def width(tok: str, names: dict | None = None) -> int:
    if tok.startswith("<E") and names is not None:
        m = re.match(r"<E([01]):(\d+)>", tok)
        t = names.get(f"E{m.group(1)}:{m.group(2)}", "") if m else ""
        return sum(2 if 0x20 <= ord(c) <= 0x7E else 3 for c in t)
    if tok.startswith("<10 ") and names is not None:  # 호출(`$10 lo hi`) — 같은 뱅크 조각 문자열을 끼워 넣는다. 폭은 대상 조각의 문안 폭(빌드가 `call:lohi` 로 넣어 준다)
        m = re.match(r"<10 ([0-9a-f]{2}) ([0-9a-f]{2})>", tok)
        t = names.get(f"call:{m.group(1)}{m.group(2)}", "") if m else ""
        return sum(2 if 0x20 <= ord(c) <= 0x7E else 3 for c in re.sub(r"<[^>]*>", "", t))
    if tok.startswith("{*"):
        return 3  # 런타임 조사는 전각 한 글자
    if tok.startswith("<"):
        return 0
    return 2 if 0x20 <= ord(tok) <= 0x7E else 3


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


RULE = True  # 쪽 나눔 — 문장 단위(아래 `_typeset` 의 `cur`). `tools/sim_pagebreak.py` 가 끄고 켜서 잰다
SPLITS: list = []  # (종류, 어절 색인) — 쪽 사이에서 문장이 갈린 자리(시뮬레이션 계측, 조판 결과엔 영향 없음)


class _Fail(Exception):
    pass


def typeset(text, names=None, lead=None):
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

    started = False
    linewords: list[tuple[int, list, int, str | None]] = []  # 이 줄의 낱말들 (out 색인, 토큰, 폭, 글자) — 뒤 낱말과 한 덩어리면 함께 다음 줄로 보낸다
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
            if nxt and nxt[0] != "<05>" and _plain(nxt, names) and krwrap.split_reason(linewords[-1][3], _plain(nxt, names)):
                w = [" "]
                t0 = " "
        if t0 == "\n":
            if rows + 1 >= PAGE_ROWS:
                if linewords and not (linewords[-1][3] and linewords[-1][3][-1] in _END):
                    SPLITS.append(("hand", wi))
                page()  # 강제 개행이 쪽을 넘기면 쪽 넘김으로
            else:
                newline()
            continue
        if t0 == "<05>":
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
            if rows + 1 >= PAGE_ROWS and RULE and cur and cur[0] != wi and cur[0] not in skip and not (cur[2] == 0 and cur[3] == 0) and not lead_ok:
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
            plain = _plain(w, names)
            carry: list = []
            if plain:  # 본용언+보조용언 등 — 앞 낱말(들)을 함께 다음 줄로(`사` / `오라고` → `사 오라고`, `해 줄 거야`)
                k, first = len(linewords), plain
                while k > 1 and linewords[k - 1][3] and krwrap.split_reason(linewords[k - 1][3], first):
                    k -= 1
                    first = linewords[k][3]
                if k < len(linewords) and sum(x[2] + 2 for x in linewords[k:]) + ww <= LINE_UNITS:
                    carry = linewords[k:]
                    del out[carry[0][0] :]
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
    s = "".join(out)
    return re.sub(r"<H(\d+)>", lambda m: heads[int(m.group(1))], s)


if __name__ == "__main__":
    import sys

    print(typeset(sys.argv[1] if len(sys.argv) > 1 else "그 얘긴 벌써 몇 번이나 들었어. 이제 그만 시시한 놀이는 그만두십시오. 한동안 공부할 시간을 못 냈으니 오늘부터는 그만큼 빡빡하게 해 주셔야겠습니다."))
