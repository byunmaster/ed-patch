"""조각 펴기 — call/goto 로 이어진 문장을 **실제 흐름대로** 한 줄로 편다(이름·정본·인사 검사용 입력).

call(`10`)은 돌아오니 그 자리에 조각 글을 끼우고, goto(`0F`)는 꼬리라 거기서 흐름이 넘어간다. 조건 꼬리(`11·12·F2·F6·F8` 바로 뒤 goto)는
**갈래 둘**이다 — 조건이 맞아 꼬리로 가는 흐름과, 건너뛰고 아래로 이어지는 흐름. 둘을 이어 붙이면 없는 문장이 생긴다(587건 오탐의 원인).
그래서 갈래마다 한 줄씩 낸다(상한 `CAP`, 넘으면 `truncated` 로 알린다).

원문(모듈 바이트)과 우리 문안(`script/*.json` 의 `ours`)을 **같은 걸음**으로 펴서 갈래 번호를 맞춘다.
"""

import re

import scene

CAP = 16  # 한 스트림에서 내는 갈래 상한(넘으면 앞쪽만)
_COND_CODES = {"11", "12", "f2", "f6", "f8"}
# 우리 문안의 태그 — `<10:0b5c>` call · `<0f:099a>` goto · 조건 `<f2:09ff>`/`<f6843d>` … · 나머지는 글자처럼 둔다(정규화는 검사기 몫)
_TAG = re.compile(r"<([0-9a-f]{2})(?::([0-9a-f]+))?(?:\|[^>]*)?>|<[0-9a-f]{4,}>")
_END_CODES = {"00", "06", "07", "0a", "0d"}
_KANA = re.compile(r"[぀-ヿ一-鿿]")


def jp_items(st) -> list[tuple]:
    """Stream → [("t", 글), ("call", off), ("goto", off), ("cond",), ("end",)]"""
    out, prev, prev2 = [], None, None
    for t in st.tokens:
        if t.kind == "text":
            out.append(("t", t.raw.decode("cp932", "replace")))
        elif t.kind in ("end", "eof"):
            out.append(("end",))
        elif t.ref == scene.CALL and t.target is not None:
            out.append(("call", t.target))
        elif t.ref == scene.GOTO and t.target is not None:
            # F8 은 인자가 3B 인데 파서는 1B 로 읽는다 — 뒤 2B 가 글자 토큰으로 갈려 나오므로 그 앞 토큰이 F8 이면 조건 꼬리다
            quirk = (
                prev is not None
                and prev.kind == "text"
                and len(prev.raw) == 2
                and prev2 is not None
                and prev2.code == 0xF8
            )
            out.append(("goto", t.target, (prev is not None and prev.code in scene.COND) or quirk))
        else:
            out.append(("t", f"<{t.raw.hex()}>"))
        prev2, prev = prev, t
    return out


def kr_items(ours: str) -> list[tuple]:
    """우리 문안 → 같은 항목열. 조건 태그(`<f2:…>`·`<f6…>` 등) 바로 뒤의 `<0f:…>` 는 조건 꼬리."""
    out, pos, cond = [], 0, False
    for m in re.finditer(r"<([0-9a-f]{2})(?::([0-9a-f]+))?[^>]*>", ours):
        if m.start() > pos:
            seg = ours[pos : m.start()]
            out.append(("t", seg))
            if not (
                cond == "f8" and len(seg) <= 3
            ):  # F8 은 뒤 2B 가 글자처럼 보이는 꼬리를 단다(`<f827><84>?`)
                cond = False
        pos = m.end()
        code, arg = m.group(1), m.group(2)
        if code in _END_CODES and arg is None and m.group(0) == f"<{code}>":
            out.append(("end",))  # 조각의 끝(06 돌아옴·07·00 …) — 글자가 아니다
            cond = False
        elif code == "10" and arg:
            out.append(("call", int(arg, 16)))
            cond = False
        elif code == "0f" and arg:
            out.append(("goto", int(arg, 16), bool(cond)))
            cond = False
        else:
            out.append(("t", m.group(0)))
            if code in _COND_CODES:
                cond = code
            elif cond != "f8":
                cond = False
    if pos < len(ours):
        out.append(("t", ours[pos:]))
    return out


def _cat(a, b):
    return None if a is None or b is None else a + b


def flow(items_of, items, i=0, seen=frozenset(), cap=CAP):
    """items[i:] 에서 끝까지 가는 흐름을 갈래별 글 목록으로(없는 조각을 거치면 None 갈래)."""
    if i >= len(items):
        return [""]
    it = items[i]
    k = it[0]
    if k == "end":
        return [""]
    if k == "t":
        return [_cat(it[1], r) for r in flow(items_of, items, i + 1, seen, cap)][:cap]
    sub = paths(items_of, it[1], seen, cap)
    if k == "call":
        rest = flow(items_of, items, i + 1, seen, cap)
        return [_cat(a, b) for a in sub for b in rest][:cap]
    if it[2]:  # 조건 꼬리 — 맞으면 꼬리로, 아니면 아래로
        return (sub + flow(items_of, items, i + 1, seen, cap))[:cap]
    return sub[:cap]  # 무조건 꼬리


def paths(items_of, off, seen=frozenset(), cap=CAP):
    items = items_of(off)
    if items is None or off in seen:
        return [None]
    return flow(items_of, items, 0, seen | {off}, cap)


def has_ref(items) -> bool:
    return any(it[0] in ("call", "goto") for it in items)
