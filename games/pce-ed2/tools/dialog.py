"""대사 줄 — PCE 덩이 한 줄(말)을 읽고(`parse`) 한국어 쪽으로 다시 짜(`rebuild`)는 도구.

줄 꼴(실측 — 마을·성 계열 패키지에서 가장 흔한 꼴 90%): `16 <화자 글자> 14 0D <쪽> 13 0D <쪽> … 13` — 화자가 있는 줄은 `16` 으로 시작하고
화자 글자는 `14` 까지, 쪽은 `13`(쪽 넘김)으로 나뉜다. 쪽 안의 `0D` 는 줄바꿈. 화자 없는 줄(이어 가는 쪽)은 글로 시작한다.
다른 제어(`10 nn` 말 속도 · `11 nn nn` 멈춤 · `12` · `1C nn` · `1A/1B` 값 넣기 …)가 낀 줄은 **단순하지 않다** — 연출 줄이라 건드리지 않는다(원문 유지).
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jptext

SIMPLE_CTRL = {0x0D, 0x0E, 0x0F, 0x13, 0x14, 0x16}


@dataclass
class Line:
    speaker: bytes | None  # 화자 글자 바이트(`16` 뒤 ~ `14` 앞) — 화자 없는 줄은 None
    pages: list[bytes]  # 쪽 본문(줄바꿈 `0D` 포함, 앞의 쪽 넘김 뒤 `0D` 는 뗀다)
    end13: bool  # 줄이 `13` 으로 끝나는가


def parse(line: bytes) -> Line | None:
    """단순한 줄이면 `Line`, 아니면 None."""
    i = 0
    speaker = None
    if line[:1] == b"\x16":
        j = line.find(b"\x14", 1)
        if j < 0:
            return None
        speaker = line[1:j]
        i = j + 1
        if line[i : i + 1] == b"\x0d":
            i += 1
        else:
            return None
    body = line[i:]
    # 본문의 제어는 단순 집합뿐 — 인자를 갖는 제어가 있으면 중단
    k = 0
    while k < len(body):
        a = body[k]
        if a < 0x20:
            if a not in SIMPLE_CTRL or a in (0x14, 0x16):
                return None
            k += 1
        elif 0x80 <= a <= 0x9F or a >= 0xE0:
            k += 2
        else:
            k += 1
    parts = body.split(b"\x13")
    end13 = len(parts) > 1 and parts[-1] == b""
    if end13:
        parts = parts[:-1]
    pages = [p[1:] if p[:1] == b"\x0d" and n > 0 else p for n, p in enumerate(parts)]
    return Line(speaker, pages, end13)


def page_jp(page: bytes) -> str:
    return jptext.decode(page)


def jp_text(line: Line) -> str:
    return "".join(re.sub(r"\{[^}]*\}", "", page_jp(p)) for p in line.pages)


MID_OK = {0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x13}  # 본문 한복판에 끼어도 버려도 되는 제어(속도 · 멈춤 · 줄·쪽 · 가나 모드)


@dataclass
class Frame:
    """줄 = 머리(제어) + [화자] + 화자 뒤(제어) + 본문 글 + 꼬리(제어). 본문 글만 다시 짜고 나머지는 원문 바이트 그대로 둔다."""

    head: bytes  # 화자 앞(없으면 본문 앞)까지의 제어
    speaker: bytes | None
    post: bytes  # `14` 뒤 ~ 본문 첫 글자 앞의 제어(`0D` · `10 33` …)
    tail: bytes  # 본문 끝 뒤의 제어(`13` · `11 33 30` · `12` …)
    marks: tuple = ()  # 본문 한복판의 연출 타이밍 제어 `(앞선 원문 글자 수, 바이트, 문장 끝 뒤인가)` — 번역문의 구절 경계에 되살린다
    jp_n: int = 0  # 본문 원문 글자 수(공백 제외)


def parse_frame(line: bytes) -> Frame | None:
    """연출 제어(`10`/`11`)가 끼어도 본문을 갈라낼 수 있는 줄이면 `Frame`. 본문 한복판에 속도·멈춤·가나 모드·줄바꿈·쪽 넘김 말고 다른 제어가 있으면 None."""
    toks: list[tuple[str, bytes]] = []
    i = 0
    while i < len(line):
        a = line[i]
        if a < 0x20:
            if a == 0x16:
                j = line.find(b"\x14", i + 1)
                if j < 0:
                    return None
                toks.append(("spk", line[i + 1 : j]))
                i = j + 1
                continue
            n = 1 + (jptext.ARGS.get(a, 0) if a != 0x13 else 0)
            toks.append(("c", line[i : i + n]))
            i += n
        else:
            n = 2 if (0x80 <= a <= 0x9F or a >= 0xE0) else 1
            toks.append(("t", line[i : i + n]))
            i += n
    if sum(1 for k, _ in toks if k == "spk") > 1:
        return None
    t_ids = [n for n, (k, _) in enumerate(toks) if k == "t"]
    if not t_ids:
        return None
    first, last = t_ids[0], t_ids[-1]
    for k, b in toks[first : last + 1]:
        if k == "spk" or (k == "c" and b[0] not in MID_OK):
            return None
    s_ids = [n for n, (k, _) in enumerate(toks) if k == "spk"]
    if s_ids and s_ids[0] > first:
        return None
    sp = s_ids[0] if s_ids else None
    j = lambda a, b: b"".join(x for _k, x in toks[a:b])  # noqa: E731
    marks, n, end = [], 0, False
    for k, b in toks[first : last + 1]:
        if k == "t":
            if b not in (b"\xa0", b"`"):  # 여백(12px)·반각 공백은 글자로 안 센다
                n += 1
                end = b in _SENT_END
        elif k == "c" and b[0] in (0x10, 0x11):
            marks.append((n, b, end))  # 셋째 = 이 멈춤 바로 앞 글자가 문장 끝 부호인가
    if sp is None:
        return Frame(j(0, first), None, b"", j(last + 1, len(toks)), tuple(marks), n)
    # 화자 글자의 가나 모드 짝(`0E`/`0F` 단독 제어) — 한글엔 없다. ⚠ 바이트 단위로 지우면 `11 37 0F` 의 둘째 인자 `0F` 까지 지워 뒤 글 첫 바이트를 인자로 먹는다(642:28:47, 10-18)
    post = b"".join(x for _k, x in toks[sp + 1 : first] if x not in (b"\x0e", b"\x0f"))
    return Frame(j(0, sp), toks[sp][1], post, j(last + 1, len(toks)), tuple(marks), n)


# 문장 끝 글자(원문) — SJIS 。！？ · 단일 바이트 가나 점 `A1` · 전각 ASCII ！？ · `｜`(=!!). 멈춤이 이 글자 바로 뒤면 한글도 문장 끝 뒤에 놓는다(`dialogue._encode`)
_SENT_END = {b"\x81\x42", b"\x81\x49", b"\x81\x48", b"\xa1", b"\x21", b"\x3f", b"\x7c"}


HARD_OK = {0x12, 0x1C}  # 문장 사이에 끼는 연출 제어 — 글을 가르지만 뜻은 「말 바꿈」 · 「창 비움」
_JP = re.compile("[ぁ-ヿ一-鿿]")


@dataclass
class Seg:
    """줄 = 항목들의 열: `("c", 바이트)` 원문 그대로 · `("s", 화자 글자 바이트)` · `("t", 머리 제어, 꼬리 제어, 원문 글)` 다시 짤 글 덩이."""

    items: list


def parse_segments(line: bytes) -> Seg | None:
    """화자(`16 .. 14`)·`1C`·`12` 로 갈리는 여러 말이 한 줄에 든 연출 줄 → `Seg`. 다른 제어(이름·값 넣기 · 스타일 · 창 호출 …)가 끼면 None."""
    toks: list[tuple[str, bytes]] = []
    i = 0
    while i < len(line):
        a = line[i]
        if a < 0x20:
            if a == 0x16:
                j = line.find(b"\x14", i + 1)
                if j < 0:
                    return None
                toks.append(("spk", line[i + 1 : j]))
                i = j + 1
                continue
            n = 1 + (jptext.ARGS.get(a, 0) if a != 0x13 else 0)
            toks.append(("c", line[i : i + n]))
            i += n
        else:
            n = 2 if (0x80 <= a <= 0x9F or a >= 0xE0) else 1
            toks.append(("t", line[i : i + n]))
            i += n
    items: list = []
    run: list = []

    def flush():
        if not run:
            return
        ids = [n for n, (k, _) in enumerate(run) if k == "t"]
        text = b"".join(b for k, b in run if k == "t")
        if not ids or not _JP.search(jptext.decode(text)):
            items.append(("c", b"".join(b for _k, b in run)))
        else:
            lead = b"".join(b for _k, b in run[: ids[0]])
            tail = b"".join(b for _k, b in run[ids[-1] + 1 :])
            marks, n, end = [], 0, False
            for k, b in run[ids[0] : ids[-1] + 1]:
                if k == "t":
                    if b not in (b"\xa0", b"`"):
                        n += 1
                        end = b in _SENT_END
                elif b[0] in (0x10, 0x11):
                    marks.append((n, b, end))
            items.append(("t", lead, tail, jptext.decode(b"".join(b for _k, b in run[ids[0] : ids[-1] + 1])), tuple(marks), n))
        run.clear()

    for k, b in toks:
        if k == "spk":
            flush()
            items.append(("s", b))
        elif k == "c" and b[0] in HARD_OK:
            flush()
            items.append(("c", b))
        elif k == "c" and b[0] not in MID_OK:
            return None
        else:
            run.append((k, b))
    flush()
    if not any(it[0] == "t" for it in items):
        return None
    return Seg(items)
