"""sfc-ed2 대사 조판 — 한국어 문안을 대사창 규격(줄 폭 50단위 · 쪽당 3줄)에 맞춰 줄바꿈·쪽 넘김을 넣는다.

규격(대사 출력기 `$C0:A9F5` 와 에뮬 실측 2026-10-12):
  · 글자 폭 단위: 전각(2바이트) 3 · 반각(1바이트·공백) 2 — 한 줄은 **50단위**(= 200px)까지(전각 16자 + 반각 1칸)
  · 한 쪽 = 본문 3줄(화자 이름 줄은 따로 한 줄 더 붙는다). 넘치면 `<05>`(키 대기 + 쪽 지우기)
번역 문안 표기: `⏎`(실제 개행)은 강제 줄바꿈, `<05>` 는 강제 쪽 넘김, 그 밖의 `<..>` 는 폭 0 제어. 어절(공백) 단위로 끊고(규칙 2-6),
줄 첫머리에 부호만 넘기지 않으며(2-3), 줄 첫 공백을 두지 않는다(2-5). 화자 머리(`<1e>이름<04>` + 개행)는 쪽 줄 수에 안 센다.
"""

import re

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


def end_state(text: str, names: dict | None = None) -> tuple[int, int]:
    """조판된 문안이 끝난 자리의 (마지막 줄 폭, 이 쪽에 쓴 완결 줄 수) — 바로 이어지는 다음 구간이 이 줄에서 이어 쓰도록 넘겨 준다."""
    text = re.sub(r"<1e>.*?<04>\n?", "", text, flags=re.S)
    text = text.rsplit("<05>", 1)[-1]
    rows = text.count("\n")
    last = text.rsplit("\n", 1)[-1]
    return sum(width(t, names) for t in _TOK.findall(last)), rows


def typeset(text: str, names: dict | None = None, lead: tuple[int, int] | None = None) -> str:
    """줄바꿈·쪽 넘김을 넣은 문안. 이미 든 `⏎`/`<05>` 는 강제로 지킨다.
    `lead` = (앞 구간이 끝난 줄 폭, 쪽에 쓴 줄 수) — 앞 구간 끝에 이어 붙는 구간(이름 변수 뒤 조각)은 그 줄의 남은 폭에서 시작한다."""
    # 화자 머리(`<1e>이름<04>` + 뒤 개행)와 맨 앞 개행은 폭·줄 수에 안 센다 — 자리표시자로 바꿨다가 되돌린다
    lead_ok = bool(lead) and not text.startswith(("<1e>", "\n"))  # 맨 앞이 화자 머리·개행이면 새 줄에서 시작한다
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

    def page():
        nonlocal u, rows
        out.append("<05>")
        u = 0
        rows = 0

    started = False
    for w in words:
        t0 = w[0]
        if t0 == "\n":
            if rows + 1 >= PAGE_ROWS:
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
            while out and out[-1] == " ":
                out.pop()
            if rows + 1 >= PAGE_ROWS:
                page()
            else:
                newline()
        # 줄 머리 부호 고아 방지는 어절 단위라 자연히 지켜진다
        out.extend(w)
        u += ww
    s = "".join(out)
    return re.sub(r"<H(\d+)>", lambda m: heads[int(m.group(1))], s)


if __name__ == "__main__":
    import sys

    print(typeset(sys.argv[1] if len(sys.argv) > 1 else "그 얘긴 벌써 몇 번이나 들었어. 이제 그만 시시한 놀이는 그만두십시오. 한동안 공부할 시간을 못 냈으니 오늘부터는 그만큼 빡빡하게 해 주셔야겠습니다."))
