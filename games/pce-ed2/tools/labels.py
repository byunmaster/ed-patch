"""지명 라벨 줄 — 덩이의 **첫 줄**(패널 지명 칸)과 지명만 든 덩이(왕국·도시 목록)의 줄을 정본 지명으로 바꾼다.

줄 꼴(실측): `[제어…] [여백] [0E 가타카나 0F · 가나 · 한자 …] [여백] [제어…]` — 여백 = `a0`(12px) · `60`(4px), 스타일 토글
`06 … 04`(여백을 감싼다), `08 08`(좌표), `10 30` · `11 33 30`(머리·꼬리). 글(글리프)은 한 글자 12px.
고치는 법: 첫 글리프 앞 · 마지막 글리프 뒤의 **제어**(스타일 토글 `04~07` 제외)는 그대로 두고, 여백은 원문과 같은 **px 폭**으로
**가운데 정렬해 다시** 채운다. 정본(`canon` ui → place)에 없는 줄은 건드리지 않고 `missing` 으로 모은다(관리자 후보).
"""

import os
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
BOX_CENTER_PX = 88  # 박스 안쪽(94px)에서 글 시작이 +3 이라 앞 여백 pad 의 가운데 맞춤은 2·pad + 글 폭 = 88 (실측 11-08: 요르도항구 pad 12·글 60 → 잉크 왼 15 · 오른 19 · 안쪽 94)
BANNER_BOX_PX = 84  # 월드맵 입장 배너 박스 안쪽 폭(실측: 요르도항구 a0+글 60+a0 · 스엘마을 a0 60+48+a0 60 60 이 84 이고 정상, 96 이 깨짐)
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
    base = canon.aliases("ed2").get(base, base)
    return canon.lookup(base, "monster", "ed2") is not None


def _lookup(jp: str) -> str | None:
    import systext  # 시험 롬 전용 후보 주입(`ED_SYS_EXTRA`, test- 꼬리표만) — 정본 확정 전 칸·화면 검증용

    ex = systext._extra()
    if jp in ex:
        return ex[jp]
    # 정본 표기와 원문 표기의 잔차: 장음 ー↔－ · 가운뎃점 ・↔･(정본은 반각 가나 점) · 작은 ィ ↔ イ(「クィーン」=「クイーン」)
    al = canon.aliases("ed2")  # 정본 별칭(같은 원문의 표기 흔들림 — 「毒かづら」→「毒カヅラ」 · 「レッドラッド」→「レッドラット」, 마스터 11-09)
    for v in dict.fromkeys([jp, jp.replace("ー", "－"), jp.replace("・", "･"), jp.replace("クィ", "クイ"), al.get(jp, jp)]):
        for cat in ("ui", "place", "monster"):
            r = canon.lookup(v, cat, "ed2")
            if r:
                return r
        m = re.match(
            r"^(.+?)([Ａ-Ｚ])$", v
        )  # 몬스터 이름 + 구별 문자(스라임Ａ) — 정본 battle 의 「{name}Ａ」 꼴: 글자는 반각 알파벳
        if m:
            r = canon.lookup(al.get(m.group(1), m.group(1)), "monster", "ed2")
            if r:
                return r + chr(ord(m.group(2)) - 0xFEE0)
    return None


# 패널 지명 칸(필드 우측 위 틀) — 실측(11-04, 헤드리스 캡처 343×243 1:1): 틀 안쪽 x 227~315(89px, 가운데 271), 글 시작 기준 x 234
FULLWIDTH_LETTER = os.environ.get("ED_FWLETTER", "0") == "1"  # 몬스터 구별 문자 — 기본은 원판대로 ASCII 반각 A(원판 이름 줄 바이트 `06 41 04`, 화면도 8px, 마스터 11-16 「pce2 원본대로」 — 원판 실화면 대조). 시험용 ED_FWLETTER=1 이면 전각 Ａ(옛 11-08 판)
PANEL_INNER_L, PANEL_INNER_R, PANEL_ORIGIN = 227, 315, 234
LEAD_PX = {0x08: 4, 0x09: -4}  # 머리 제어 `08` 하나 = 오른쪽으로 4px(실측 — `08 08 60` 줄의 글이 `60` 줄보다 8px 오른쪽) · `09` = 왼쪽으로 4px(핸들러 `$6891`: DEC $73 · DEC $71 — `08` 의 짝)


def lead_px(lead: bytes) -> int:
    return sum(LEAD_PX.get(b, 0) for b in lead if b in LEAD_PX)


INK_CENTER = 545  # 글 시작 x s, 글 폭 w 일 때 잉크 쏠림 d = 2·s + w − 545 (실측 11-08: 한글 칸 잉크가 왼쪽 0 · 오른쪽 빈틈 2px — 4글자 s=246 → 왼 19 · 오른 24)
PANEL_INK_LAST = PANEL_INNER_R - 1  # 글 잉크가 틀 오른쪽 선에 닿지 않는 마지막 x


def panel_pad(w: int, lead: bytes = b"") -> int:
    """글 폭 `w`(px) 를 칸 한가운데로 보내는 앞 여백(px, 4 의 배수) — 잉크 쏠림 |2·s + w − 545| 가 가장 작은 4px 격자(같으면 왼쪽 — 마스터 11-09 「최대한 가운데」)."""
    base = PANEL_ORIGIN + lead_px(lead)
    fit = [p for p in range(0, 90, SPACE_PX) if base + p + w - 3 <= PANEL_INK_LAST] or [0]
    return min(fit, key=lambda p: (abs(2 * (base + p) + w - INK_CENTER), p))  # 마스터 11-09 「최대한 가운데」 — 가장 가까운 칸, 같을 때만 왼쪽(번역 규칙 2-8 개정)


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
        w > px and " " in kr and not is_monster(jp)
    ):  # (몬스터 이름은 칸이 없다 — 공백을 걷으면 「붉은슬라임A」 가 되어 틀 줄의 「붉은 슬라임A」 와 갈린다, qa 10-20) 칸(슬롯)은 붙여 쓰는 꼴이 규칙이다(naming.md 「지명 칸」) — 공백을 걷으면 들어가는지 본다
        kr = kr.replace(" ", "")
        w = sum(font.adv(c) for c in kr)
    if w > px and not is_monster(jp):  # (몬스터 이름은 전투 메시지 창으로만 흘러 칸 폭이 없다 — 전투 화면은 이름 목록 창이 없다, 10-16 실측)
        # 칸을 넘는다 — 문안을 줄여야만 들어가는 칸이다(관리자 판정). 원문을 두고 모은다
        OVERFLOW[jp] = (kr, w, px)
        return raw
    if is_monster(jp):  # 전투 이름 줄은 문장 가운데(`1B`)에 끼므로 칸 맞춤 여백을 두지 않는다 — 두면 이름 뒤에 빈틈이 생긴다(「슬라임A 에게」, 10-13 화면)
        if re.search(r"[A-Z]$", kr):  # 구별 문자(A·B…)는 **ASCII 한 바이트** 로 낸다 — 엔진이 8px 반각으로 그린다(글리프 코드는 12px 칸이라 뒤에 빈틈이 남는다). 규칙 1-6: 전 기종 반각
            if FULLWIDTH_LETTER:  # 마스터 11-08 「SFC·MD·PCE 는 원판 꼴(전각)」 — 구별 문자를 원판 글자(전각 Ａ~Ｄ, 12px)로 낸다(규칙 1-6 개정)
                return lead + tab.enc(kr[:-1] + chr(ord(kr[-1]) + 0xFEE0), space=SPACE) + trail
            return lead + tab.enc(kr[:-1], space=SPACE) + kr[-1].encode("ascii") + trail
        return lead + tab.enc(kr, space=SPACE) + trail
    if hud:
        return lead + bytes([SPACE]) + tab.enc(kr, space=SPACE) + trail
    if not any(kind == "pad" for kind, _b in _tokens(raw)):  # 원문이 여백 없이 칸 왼쪽부터 채운 줄(예: 왕국 이름 8글자 96px)은 왼쪽 맞춤 그대로 — 가운데 여백을 두면 글 블록이 패널 오른쪽 테두리를 넘는다(마스터 10-14 「파렌왕국」)
        return lead + tab.enc(kr, space=SPACE) + trail
    if lead.startswith(b"\x10\x30") and trail.endswith(b"\x11\x33\x30"):  # 월드맵 입장 배너 박스(`10 30 … 11 33 30`) — 안쪽 84px(7칸)을 넘으면 글이 지워지고 흰 줄만 남는다
        px = min(px, BANNER_BOX_PX)  # (11-06 낫슈마을 앞뒤 여백 `a0 a0` ×2 = 96px — 원판은 가나 한 바이트 글자라 이름이 좁아 여백이 커도 들어갔다)
    extra = px - w
    left = (extra // 2) // SPACE_PX * SPACE_PX
    if lead.startswith(b"\x10\x30") and trail.endswith(b"\x11\x33\x30"):
        left = _box_left(w, px)
    return lead + _pad(left) + tab.enc(kr, space=SPACE) + _pad(extra - left) + trail


def _box_left(w: int, total: int = BANNER_BOX_PX) -> int:
    """입장 배너 박스 줄의 앞 여백(px, 4 의 배수) — 글 가운데가 박스 가운데에 가장 가까운 칸(2·pad + w = 88 에 가장 가까운 것, 같으면 왼쪽 — 마스터 11-09 「최대한 가운데」), 앞뒤 여백 합(total)을 넘지 않게."""
    fit = range(0, max(0, total - w) + 1, SPACE_PX)
    return min(fit, key=lambda p: (abs(2 * p + w - BOX_CENTER_PX), p))


def recenter_box(raw: bytes) -> bytes:
    """입장 배너 박스 줄(`10 30 … 11 33 30`, 안쪽엔 글자·여백뿐)의 앞뒤 여백을 박스 가운데 맞춤으로 다시 정한다 — 대사 정본이 여백 없이 글만 낸 줄(곶의동굴 따위)이 왼쪽에 붙던 것(11-08 실화면)."""
    if not (raw.startswith(b"\x10\x30") and raw.endswith(b"\x11\x33\x30")):
        return raw
    toks = _tokens(raw[2:-3])
    if any(kind == "ctrl" and b[0] not in STYLE for kind, b in toks) or not any(k == "glyph" for k, _b in toks):
        return raw
    g = [k for k, (kind, _b) in enumerate(toks) if kind == "glyph"]
    core = b"".join(b for _kind, b in toks[g[0] : g[-1] + 1])
    w = sum(
        font.NARROW_PX if kind == "glyph" and len(b) == 1 and 0x21 <= b[0] <= 0x5F else {"glyph": CELL_PX, "pad": CELL_PX, "space": SPACE_PX}.get(kind, 0)
        for kind, b in toks[g[0] : g[-1] + 1]
    )
    if w > BANNER_BOX_PX:
        return raw
    left = _box_left(w)
    return b"\x10\x30" + _pad(left) + core + _pad(BANNER_BOX_PX - w - left) + b"\x11\x33\x30"


def strip_narrow(raw: bytes) -> bytes:
    """줄의 좁은 글꼴 토글 `06` 을 걷는다 — 한글이 그 안에서 깨진다(HUD 「———--」 · 테크니카의방 빈 칸, 11-08 실화면). 대사·메뉴 제어가 낀 줄은 그대로."""
    toks = _tokens(raw)
    if any(kind == "ctrl" and b[0] in {0x16, 0x14, 0x13, 0x12, 0x01, 0x1C, 0x1D} for kind, b in toks):
        return raw
    return b"".join(b for kind, b in toks if not (kind == "ctrl" and b[0] == 0x06))


def recenter_line(raw: bytes) -> bytes:
    """구운 줄의 앞뒤 여백을 걷고 패널 지명 칸 한가운데로 다시 맞춘다(마스터 11-04 「입장 배너 가운데 정렬」, 번역 규칙 2-8). 글(글리프) 폭은 그대로 — 글을 바꾼 쪽(라벨 · 대사 정본)과 무관하게 **여백만** 정한다.
    글 사이에 제어가 끼면(라벨 꼴이 아님) 그대로 둔다. 머리·꼬리 제어는 스타일 토글(04~07)·가나 모드(0E·0F)만 버린다(`split` 과 같다)."""
    toks = _tokens(raw)
    g = [k for k, (kind, _b) in enumerate(toks) if kind == "glyph"]
    if not g:
        return raw
    first, last = g[0], g[-1]
    drop = STYLE | {0x0E, 0x0F}
    if any(kind == "ctrl" and b[0] not in drop for kind, b in toks[first : last + 1]):
        return raw
    lead = b"".join(b for kind, b in toks[:first] if kind == "ctrl" and b[0] not in drop)
    trail = b"".join(b for kind, b in toks[last + 1 :] if kind == "ctrl" and b[0] not in drop)
    core = b"".join(b for _kind, b in toks[first : last + 1])
    w = sum(
        font.NARROW_PX
        if kind == "glyph" and len(b) == 1 and 0x21 <= b[0] <= 0x5F
        else {"glyph": CELL_PX, "pad": CELL_PX, "space": SPACE_PX}.get(kind, 0)
        for kind, b in toks[first : last + 1]
    )
    pad = panel_pad(w, lead)
    base = PANEL_ORIGIN + lead_px(lead)
    back = b""
    if base + pad + w - 3 > PANEL_INK_LAST:  # 글이 칸보다 넓어 시작을 앞당겨도 오른쪽 선에 닿는다(「모레스톤공화국」 7자 84px) — 이 줄만 `09`(왼쪽 4px)로 시작을 앞당긴다
        back = b"\x09" * -(-(base + pad + w - 3 - PANEL_INK_LAST) // 4)
    return lead + back + _pad(pad) + core + trail


def lookup_general(jp: str) -> str | None:
    """지명 **일반 꼴**(띄어쓰기 — 입장 배너·대사, 마스터 11-09 「지명 정본에 일반/hud 두가지」) — 정본 `place_general`, 없으면 HUD 꼴(`lookup`)."""
    for v in dict.fromkeys([jp, jp.replace("ー", "－"), jp.replace("・", "･"), jp.replace("クィ", "クイ")]):
        r = canon.place_general(v, "ed2")
        if r:
            return r
    return lookup(jp)


def box_line_general(lo_line: bytes, tab) -> bytes | None:
    """원판 입장 배너 박스 줄 → 정본 일반 꼴(띄어쓰기)로 다시 짠 줄. 박스 줄이 아니거나 이름·칸이 안 맞으면 None."""
    sp = split(lo_line)
    if sp is None:
        return None
    lead, trail, jp, _px = sp
    if not (lead.startswith(b"\x10\x30") and trail.endswith(b"\x11\x33\x30")):
        return None
    kr = lookup_general(jp)
    if kr is None or is_monster(jp):
        return None
    w = sum(font.adv(c) for c in kr)
    if w > BANNER_BOX_PX:
        return None
    left = _box_left(w)
    return lead + _pad(left) + tab.enc(kr, space=SPACE) + _pad(BANNER_BOX_PX - w - left) + trail


def recenter_chunk(orig: bytes, new: bytes, tab=None) -> bytes:
    """덩이 **첫 줄**(패널 지명 칸)이 원판에서 지명 라벨 꼴이고 한글로 바뀌었으면 가운데로 다시 맞춘다. 몬스터 이름(전투 덩이)·원문 그대로 둔 줄은 건드리지 않는다.
    첫 줄의 좁은 글꼴 토글 `06` 은 걷고, 입장 배너 박스 줄(둘째 줄 이후)은 박스 가운데로 다시 맞춘다."""
    lo, ln = orig.split(b"\x00"), new.split(b"\x00")
    for i in range(1, len(ln) - 1):
        if i < len(lo) and ln[i] != lo[i]:
            g = box_line_general(lo[i], tab) if tab is not None else None
            ln[i] = g if g is not None else recenter_box(ln[i])
    new = b"\x00".join(ln)
    s = split(lo[0])
    if s is None:  # 글 사이에 좌표 제어(`08`)가 낀 「～城」 꼴 — 대사 제어가 없고 지명 접미로 끝나면 지명 칸 줄이다
        kinds = {b[0] for kind, b in _tokens(lo[0]) if kind == "ctrl"}
        jp = re.sub(r"\{[0-9A-F ]+\}|[ \u3000]", "", jptext.decode(lo[0]))
        route = bool(kinds & {0x06, 0x08}) and not kinds & {0x10, 0x11, 0x13, 0x14, 0x16}  # 「イシュタ～イズー」 따위 길 이름(좁은 글꼴 · 좌표 제어)
        if kinds & {0x16, 0x14, 0x13, 0x12, 0x01, 0x1C, 0x1D} or not (route or re.search(r"(?:城|町|村|港|鉱山|洞窟|塔)$", jp)):
            if ln[0] != lo[0] and any(kind == "ctrl" and b[0] == 0x06 for kind, b in _tokens(lo[0])):  # 원판 첫 줄이 좁은 글꼴 토글을 쓴 지명 줄만
                ln[0] = strip_narrow(ln[0])
            return b"\x00".join(ln)
    elif is_monster(s[2]):
        return new
    elif s[3] > 110:  # 원문 첫 줄이 패널 칸(89px)보다 훨씬 넓다 — 패널 지명이 아니라 장 제목 띠 꼴 줄(디버그 마을·배틀 테스트 마을 「…バトルテスト」 14칸)이다. 가운데 여백을 다시 정하지 않는다
        return new
    if ln[0] == lo[0]:
        return new
    ln[0] = recenter_line(strip_narrow(ln[0]))
    return b"\x00".join(ln)


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
