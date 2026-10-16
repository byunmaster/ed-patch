"""지명 라벨 줄 — 덩이의 **첫 줄**(패널 지명 칸)과 지명만 든 덩이(왕국·도시 목록)의 줄을 정본 지명으로 바꾼다.

줄 꼴(실측): `[제어…] [여백] [0E 가타카나 0F · 가나 · 한자 …] [여백] [제어…]` — 여백 = `a0`(12px) · `60`(4px), 스타일 토글
`06 … 04`(여백을 감싼다), `08 08`(좌표), `10 30` · `11 33 30`(머리·꼬리). 글(글리프)은 한 글자 12px.
고치는 법: 첫 글리프 앞 · 마지막 글리프 뒤의 **제어**(스타일 토글 `04~07` 제외)는 그대로 두고, 여백은 원문과 같은 **px 폭**으로
**가운데 정렬해 다시** 채운다. 정본(`canon` ui → place)에 없는 줄은 건드리지 않고 `missing` 으로 모은다(관리자 후보).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon
import compose
import font
import jptext

CELL_PX = 12
SPACE_PX = 4
PAD = 0xA0
SPACE = 0x60
STYLE = {0x04, 0x05, 0x06, 0x07}
OVERFLOW: dict[
    str, tuple[str, int, int]
] = {}  # 칸 폭(px)을 넘어 못 바꾼 라벨 — 원문 · 정본 값 · 폭


def _tokens(raw: bytes):
    """(종류, 바이트) — 종류 = ctrl · pad · space · glyph."""
    out = []
    i = 0
    while i < len(raw):
        a = raw[i]
        if a < 0x20:
            n = 1 + jptext.ARGS.get(a, 0)
            out.append(("ctrl", raw[i : i + n]))
            i += n
        elif a == PAD:
            out.append(("pad", raw[i : i + 1]))
            i += 1
        elif a == SPACE:
            out.append(("space", raw[i : i + 1]))
            i += 1
        elif 0x80 <= a <= 0x9F or a >= 0xE0:
            out.append(("glyph", raw[i : i + 2]))
            i += 2
        else:
            out.append(("glyph", raw[i : i + 1]))
            i += 1
    return out


def split(raw: bytes):
    """라인 → (앞 제어, 뒤 제어, 일본어 문구, 원문 px 폭) 또는 None(라벨 꼴이 아님)."""
    toks = _tokens(raw)
    g = [k for k, (kind, _b) in enumerate(toks) if kind == "glyph"]
    if not g:
        return None
    first, last = g[0], g[-1]
    kinds = {b[0] for kind, b in toks if kind == "ctrl"}
    if kinds & {0x16, 0x14, 0x13, 0x12, 0x01, 0x1C, 0x1D}:  # 대사·메뉴 제어가 있으면 라벨이 아니다
        return None
    drop = STYLE | {
        0x0E,
        0x0F,
    }  # 스타일 토글은 여백과 함께 · 가나 모드는 한글 글리프에 무관해 같이 버린다
    lead = b"".join(b for kind, b in toks[:first] if kind == "ctrl" and b[0] not in drop)
    trail = b"".join(b for kind, b in toks[last + 1 :] if kind == "ctrl" and b[0] not in drop)
    mode = b""  # 첫 글리프 앞에서 켜진 가나 모드를 문구 읽기에 되살린다
    for kind, b in toks[:first]:
        if kind == "ctrl" and b[0] in (0x0E, 0x0F):
            mode = b
    body = mode + b"".join(
        b for kind, b in toks[first : last + 1] if not (kind == "ctrl" and b[0] in STYLE)
    )
    if any(kind == "ctrl" and b[0] not in drop for kind, b in toks[first : last + 1]):
        return None  # 글 사이에 스타일 토글·가나 모드 말고 제어가 끼면 라벨이 아니다
    jp = jptext.decode(body).replace("{0E}", "").replace("{0F}", "").replace("　", "")
    px = sum(
        font.NARROW_PX
        if kind == "glyph" and len(_b) == 1 and 0x21 <= _b[0] <= 0x5F
        else {"glyph": CELL_PX, "pad": CELL_PX, "space": SPACE_PX}.get(kind, 0)
        for kind, _b in toks
    )
    return lead, trail, jp, px


def lookup(jp: str) -> str | None:
    """원문 → 정본 값. 몬스터 이름은 정본 표기 그대로(공백 포함) — 칸 규칙(붙여 쓰기)은 지명 칸 몫이다."""
    r = _lookup(jp)
    return r if r is not None else compose.place(jp)  # 정본 어간 + 정본 접미 조합(원문 꼴 그대로)


def is_monster(jp: str) -> bool:
    base = re.sub(r"[Ａ-Ｚ]$", "", jp)
    return canon.lookup(base, "monster", "ed2") is not None


def _lookup(jp: str) -> str | None:
    for v in dict.fromkeys([jp, jp.replace("ー", "－")]):
        for cat in ("ui", "place", "monster"):
            r = canon.lookup(v, cat, "ed2")
            if r:
                return r
        m = re.match(
            r"^(.+?)([Ａ-Ｚ])$", v
        )  # 몬스터 이름 + 구별 문자(스라임Ａ) — 정본 battle 의 「{name}Ａ」 꼴: 글자는 반각 알파벳
        if m:
            r = canon.lookup(m.group(1), "monster", "ed2")
            if r:
                return r + chr(ord(m.group(2)) - 0xFEE0)
    return None


def _pad(px: int) -> bytes:
    n12, rest = divmod(px, CELL_PX)
    return bytes([PAD]) * n12 + bytes([SPACE]) * (rest // SPACE_PX)


def edit_line(raw: bytes, tab, missing: set, hud: bool = False) -> bytes:
    """`hud` = 패널 지명 줄(덩이 첫 줄) — 패널 폭이 원문 글 폭보다 넓어 **가운데 맞춤 여백이 글을 오른쪽으로 민다**(10-13 「엘아스타마을」 오른쪽 치우침).
    원문처럼 앞에 반각 공백 하나만 두고 왼쪽에서 시작한다."""
    s = split(raw)
    if s is None:
        return raw
    lead, trail, jp, px = s
    kr = lookup(jp)
    if kr is None:
        missing.add(jp)
        return raw
    w = sum(font.adv(c) for c in kr)
    if (
        w > px and " " in kr
    ):  # 칸(슬롯)은 붙여 쓰는 꼴이 규칙이다(naming.md 「지명 칸」) — 공백을 걷으면 들어가는지 본다
        kr = kr.replace(" ", "")
        w = sum(font.adv(c) for c in kr)
    if w > px:  # 칸을 넘는다 — 문안을 줄여야만 들어가는 칸이다(관리자 판정). 원문을 두고 모은다
        OVERFLOW[jp] = (kr, w, px)
        return raw
    if is_monster(jp):  # 전투 이름 줄은 문장 가운데(`1B`)에 끼므로 칸 맞춤 여백을 두지 않는다 — 두면 이름 뒤에 빈틈이 생긴다(「슬라임A 에게」, 10-13 화면)
        if re.search(r"[A-Z]$", kr):  # 구별 문자(A·B…)는 **ASCII 한 바이트** 로 낸다 — 엔진이 8px 반각으로 그린다(글리프 코드는 12px 칸이라 뒤에 빈틈이 남는다). 규칙 1-6: 전 기종 반각
            return lead + tab.enc(kr[:-1], space=SPACE) + kr[-1].encode("ascii") + trail
        return lead + tab.enc(kr, space=SPACE) + trail
    if hud:
        return lead + bytes([SPACE]) + tab.enc(kr, space=SPACE) + trail
    if not any(kind == "pad" for kind, _b in _tokens(raw)):  # 원문이 여백 없이 칸 왼쪽부터 채운 줄(예: 왕국 이름 8글자 96px)은 왼쪽 맞춤 그대로 — 가운데 여백을 두면 글 블록이 패널 오른쪽 테두리를 넘는다(마스터 10-14 「파렌왕국」)
        return lead + tab.enc(kr, space=SPACE) + trail
    extra = px - w
    left = (extra // 2) // SPACE_PX * SPACE_PX
    return lead + _pad(left) + tab.enc(kr, space=SPACE) + _pad(extra - left) + trail


def edit_chunk(d: bytes, tab, missing: set) -> bytes:
    """덩이 → 새 덩이. 지명 목록 덩이(12줄 이하 · 줄 거의 전부가 라벨 꼴)는 모든 줄, 그 밖(대사 덩이)은 첫 줄만."""
    lines = d.split(b"\x00")
    n = len(lines) - 1
    like = sum(1 for l in lines[:n] if split(l) is not None)
    every = n <= 12 and like >= n - 1
    for i in range(n if every else min(1, n)):
        lines[i] = edit_line(lines[i], tab, missing, hud=not every)
    return b"\x00".join(lines)


def edit_any_lines(d: bytes, tab, missing: set, skip: set[int]) -> bytes:
    """덩이의 **나머지 줄**(`skip` 제외)도 라벨 꼴이면 정본으로 바꾼다 — 전투 덩이의 몬스터 이름(+Ａ·Ｂ) · 지명 배너 따위. 정본에 없는 줄은 건드리지 않는다(`missing` 에 안 모은다)."""
    lines = d.split(b"\x00")
    for i, l in enumerate(lines[:-1]):
        if i in skip:
            continue
        s = split(l)
        if s is None or lookup(s[2]) is None:
            continue
        lines[i] = edit_line(l, tab, set())
    return b"\x00".join(lines)
