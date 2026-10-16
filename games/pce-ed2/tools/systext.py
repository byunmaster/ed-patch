"""시스템 문구(메뉴 · 라벨 · 표) — 본 프로그램 안의 **00 끝 문자열**을 정본으로 바꾼다.

문자열을 부르는 길은 둘이다(2026-10-12 역공학):
  ① **리터럴** — `JSR $503E`(또는 `$4ED5`) 바로 뒤 `BIT $xxxx` 의 피연산자가 같은 뱅크 안 문자열 주소다(뱅크 0x69~0x71 에 149곳).
  ② **표** — `LDY #hi / LDX #lo` 로 표 시작을 주고 `JSR $452B` 가 A 번째 문자열까지 `00` 을 세어 건너뛴다(뱅크 0x71: 아이템 ·
     주문 · 지명 · 이름 · 설정 선택지 · 상태 아이콘). 그래서 표는 **항목 수와 순서만 지키면** 어디든 옮길 수 있고, 시작 주소 즉치만 고치면 된다.
고치는 법: 문자열을 줄(`0D`)로, 줄을 **글 덩이**(하드 제어 사이)로 나눠 덩이마다 정본 문구(`@문맥` 열쇠 우선)를 찾는다 —
**줄 전체가 정본에 걸린 문자열만** 바꾸고(일부만 바꾸면 한일 혼합이 된다), 아니면 원문 그대로 두고 `MISSING` 에 모은다.
덩이의 여백(`a0` 12px · `60` 4px)은 글 앞은 두고 **뒤쪽 여백으로 px 폭을 맞춘다**(고정 열 정렬 유지). 제어(`01` `15 nn` `08 08` `1A` …)는 그대로.
자리가 모자라면 같은 뱅크의 자유 공간(0xFF 패딩 · 비운 칸)으로 옮기고 참조를 고친다 — 못 옮기면 빌드가 멈춘다.
"""

import itertools
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon
import compose
import font
import jptext
import layout

CELL_PX = 12
SPACE_PX = 4
PAD = 0xA0
SPACE = 0x60
STYLE = {0x04, 0x05, 0x06, 0x07}
ARGS = {
    **jptext.ARGS,
    0x13: 1,
    0x16: 4,
    0x18: 4,
}  # 시스템 문자열에서는 창 머리(`16`/`18`)가 인자 4바이트, `13` 이 1바이트
CATS = ("ui", "item", "spell", "place", "person", "monster", "speaker", "battle", "system")

# 문맥 — 같은 원문이 칸마다 다른 값인 것(정본 열쇠 `원문@문맥`). 문자열 주소(뱅크, 오프셋)로 건다.
CONTEXT = {
    (0x6A, 0x030C): "파티메뉴",
    (0x6A, 0x0392): "파티메뉴",
    (0x6A, 0x050D): "능력치",
    (0x6F, 0x0000): "전투설정",
    (0x6F, 0x0016): "전투설정",
    (0x6F, 0x003A): "전투커맨드",
}

# 표 — (이름, 뱅크, 시작 오프셋, 끝 오프셋(배타)). 시작 주소 즉치 `LDY #hi / LDX #lo` 를 고친다. 0xC71~0xC85 는 리터럴 문자열이라 안 건드린다.
TABLES = [
    ("items", 0x71, 0x0C86, 0x0FF6),
    ("spells", 0x71, 0x0FF6, 0x10B9),
    ("places", 0x71, 0x10B9, 0x136C),
    ("names", 0x71, 0x136C, 0x1388),
    ("onoff", 0x71, 0x1388, 0x13CD),
    ("status", 0x71, 0x13CD, 0x13FB),
]

NOPAD = {"items", "spells"}  # 이름 뒤 폭 맞춤 여백을 두지 않는 표 — 문장 속 `1A` 로도 쓰인다

# 개발자 오류 문구(화면에 안 뜨는 길) — 뱅크 자리가 모자랄 때 글만 줄여 자리를 만든다(제어 앞뒤는 그대로, 전각 라틴이라 일본어 게이트와 무관).
SHRINK = {(0x6F, 0x062F): "ＶＲＡＭ　ＥＲＲ！！"}
OVERFLOW: list[
    tuple[int, int, int, int, str]
] = []  # 같은 뱅크에 자리가 없어 못 바꾼 문자열 (뱅크, 오프셋, 원래 B, 필요 B, 원문)
MISSING: dict[str, set[str]] = {}  # 문맥/표 → 정본에 없는 원문 문구


def _variants(jp: str) -> list[str]:
    """같은 원문의 표기차(장음 `ー` ↔ `－`)를 같은 원문으로 본다 — PS1 정본은 `－`, 이 게임은 `ー`."""
    return list(dict.fromkeys([jp, jp.replace("ー", "－"), jp.replace("－", "ー")]))


def lookup(jp: str, ctx: str | None) -> str | None:
    for v in _variants(jp):
        if ctx:
            for c in (ctx, "경험치표시") if ctx == "onoff" else (ctx,):  # 설정 값 표의 「あと」 = 경험치 표시 문맥
                for cat in CATS:
                    r = canon.lookup(f"{v}@{c}", cat, "ed2")
                    if r:
                        return r
        for cat in CATS:
            r = canon.lookup(v, cat, "ed2")
            if r:
                return r
    return compose.place(jp)  # 정본 어간 + 정본 접미 조합(지명 표 · 구간 라벨)


def tokens(raw: bytes):
    out = []
    i = 0
    while i < len(raw):
        a = raw[i]
        if a < 0x20:
            n = 1 + ARGS.get(a, 0)
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


def _tok_px(k: str, b: bytes) -> int:
    if k == "glyph" and len(b) == 1 and 0x21 <= b[0] <= 0x5F:  # ASCII 단일 바이트는 8px 반각으로 그려진다
        return font.NARROW_PX
    return {"glyph": CELL_PX, "pad": CELL_PX, "space": SPACE_PX}.get(k, 0)


def _px(toks) -> int:
    return sum(_tok_px(k, b) for k, b in toks)


def _padbytes(px: int) -> bytes:
    n12, rest = divmod(px, CELL_PX)
    return bytes([PAD]) * n12 + bytes([SPACE]) * (rest // SPACE_PX)


def _soft(tok) -> bool:
    k, b = tok
    return k != "ctrl" or b[0] in STYLE or b[0] in (0x0E, 0x0F)


def _is_latin(jp: str) -> bool:
    return all(not re.match(r"[぀-ヿ一-鿿]", c) for c in jp)


def translate(raw: bytes, ctx: str | None, miss: set[str]) -> bytes | None:
    """문자열 → 새 문자열(끝 `00` 제외). 못 바꾸면 None(원문 유지)."""
    toks = tokens(raw)
    out = []
    i = 0
    changed = False
    while i < len(toks):
        if not _soft(toks[i]):
            out.append(toks[i][1])
            i += 1
            continue
        j = i
        while j < len(toks) and _soft(toks[j]):
            j += 1
        seg = toks[i:j]
        g = [k for k, (kind, _b) in enumerate(seg) if kind == "glyph"]
        if not g:
            out.append(b"".join(b for _k, b in seg))
            i = j
            continue
        first, last = g[0], g[-1]
        pre, core, post = seg[:first], seg[first : last + 1], seg[last + 1 :]
        mode = b""
        for kind, b in pre:
            if kind == "ctrl" and b[0] in (0x0E, 0x0F):
                mode = b
        body = mode + b"".join(b for _kind, b in core)
        jp = jptext.decode(body).replace("{0E}", "").replace("{0F}", "")
        jp = re.sub(r"\{[0-9A-F ]+\}", "", jp).replace("　", "").replace("\n", "")
        if not jp or (_is_latin(jp) and ctx != "onoff"):
            out.append(b"".join(b for _k, b in seg))
            i = j
            continue
        # 설정 값 표(ＯＮ·ＯＦＦ·ＣＤ·ＰＳＧ·ＥＰ)는 **전각**으로 그린다(마스터 10-13 「전각으로 나와야함」 · 규칙 1-4) — 원판은 ASCII 반각이다
        kr = jp if (_is_latin(jp) and ctx == "onoff") else lookup(jp, ctx)
        if kr is None:
            miss.add(jp)
            return None
        # 가나 모드(`0E`/`0F`)는 한글 글리프에 무관하고, **켜 둔 채 한글을 그리면 첫 글자만 나온다**(실측 — 설정 창 머리) → 버린다
        keep = lambda ts: [t for t in ts if not (t[0] == "ctrl" and t[1][0] in (0x0E, 0x0F))]
        out.append(("KR", kr, _px(core), keep(pre), keep(post)))
        changed = True
        i = j
    if not changed:
        return None
    return out  # 아래 `render` 가 글리프 코드로 바꾼다


def render(plan, tab) -> bytes:
    """`translate` 가 낸 조각 목록 → 바이트(글리프 코드는 `tab` — 두 단계 확정 규약)."""
    out = bytearray()
    for item in plan:
        if isinstance(item, bytes):
            out += item
            continue
        _tag, kr, core_px, pre, post = item
        out += b"".join(b for _k, b in pre)
        text = tab.enc(kr, space=SPACE)
        w = sum(font.adv(c) for c in kr)
        pad_after = core_px - w  # 원문 덩이 폭(px)을 지킨다
        post_b = list(post)
        if pad_after > 0:
            out += text + _padbytes(pad_after)
        else:  # 한국어가 더 넓다 — 뒤 여백을 줄인다(모자라면 그대로 넘친다)
            need = -pad_after
            while need > 0 and post_b and post_b[0][0] in ("pad", "space"):
                need -= CELL_PX if post_b[0][0] == "pad" else SPACE_PX
                post_b.pop(0)
            out += text
        out += b"".join(b for _k, b in post_b)
    return bytes(out)


def strings_of(raw_bank: bytes, off: int) -> bytes:
    return raw_bank[off : raw_bank.index(0, off)]


def scan_literals(prog: layout.Prog) -> dict[tuple[int, int], list[int]]:
    """{(뱅크, 문자열 오프셋): [피연산자 위치(뱅크 안)]} — `JSR $503E/$4ED5 · BIT $addr` 리터럴."""
    out: dict[tuple[int, int], list[int]] = {}
    for b in range(0x69, 0x72):
        s = prog.o(b, 0, layout.BANK)
        for m in re.finditer(rb"\x20(?:\x3e\x50|\xd5\x4e)\x2c(..)", s, re.DOTALL):
            addr = m.group(1)[0] | m.group(1)[1] << 8
            if 0x6000 <= addr < 0x8000:
                out.setdefault((b, addr - 0x6000), []).append(m.start(1))
    return out


def table_sites(prog: layout.Prog, bank: int, base_off: int) -> list[tuple[int, int, int]]:
    """표 시작 즉치 `LDY #hi / LDX #lo`(두 순서)의 (hi 위치, lo 위치, 뱅크 안 오프셋) — 뱅크 안 전체에서."""
    hi, lo = (0x6000 + base_off) >> 8, (0x6000 + base_off) & 0xFF
    s = prog.o(bank, 0, layout.BANK)
    out = []
    for m in re.finditer(bytes([0xA0, hi, 0xA2, lo]), s):
        out.append((m.start() + 1, m.start() + 3, m.start()))
    for m in re.finditer(bytes([0xA2, lo, 0xA0, hi]), s):
        out.append((m.start() + 3, m.start() + 1, m.start()))
    return out


def plan(prog: layout.Prog, tab, report: dict | None = None) -> None:
    """장부(`prog`)에 시스템 문구 패치를 적는다. 수집 단계(`tab.map is None`)에서도 같은 모양으로 돈다."""
    stat = {"literal": 0, "literal_kept": 0, "table": 0, "moved": 0}
    # ⓪ 줄이기 — 개발자 오류 문구
    for (bank, off), text in SHRINK.items():
        raw0 = strings_of(prog.o(bank, 0, layout.BANK), off)
        toks0 = tokens(raw0)
        g = [k for k, (kind, _b) in enumerate(toks0) if kind == "glyph"]
        pre = b"".join(b for _k, b in toks0[: g[0]])
        post = b"".join(b for _k, b in toks0[g[-1] + 1 :])
        new0 = pre + text.encode("cp932") + post
        if len(new0) < len(raw0):
            prog.put(bank, off, new0 + b"\x00", f"shrink {bank:02X}+{off:04X}")
            prog.vacate(bank, off + len(new0) + 1, len(raw0) - len(new0))
    # ① 표 — 항목 수 · 순서 보존, 필요하면 옮기고 시작 즉치를 고친다
    for name, bank, a, b in TABLES:
        raw = prog.o(bank, a, b - a)
        entries = (
            raw.rstrip(b"\x00").split(b"\x00") if name != "status" else raw.split(b"\x00")[:-1]
        )
        if name == "status":
            entries = raw[: raw.rindex(b"\x00") + 1].split(b"\x00")[:-1]
        miss = MISSING.setdefault(name, set())
        new = []
        for e in entries:
            r = translate(e, name, miss)  # 표 이름이 문맥이다(「あと@경험치표시」 · 「ＯＮ」 전각 등)
            if r is not None and name in NOPAD:  # 문장에 끼는 이름(`1A`)은 원문 폭만큼 뒤 여백을 채우면 「횃불    을 사용했다.」 처럼 벌어진다(10-13 화면) — 가나 4칸 폭이 한글 2칸보다 넓다
                r = [("KR", x[1], 0, x[3], x[4]) if isinstance(x, tuple) else x for x in r]
            new.append(render(r, tab) if r is not None else e)
            stat["table"] += r is not None
        blob = b"\x00".join(new) + b"\x00"
        orig_blob = b"\x00".join(entries) + b"\x00"
        assert raw.startswith(orig_blob), f"표 {name} 항목 분할이 원본과 다르다"
        if blob == orig_blob:
            continue
        sites = table_sites(prog, bank, a)
        if not sites:
            raise ValueError(f"표 {name}: 시작 주소 즉치를 못 찾았다")
        if len(blob) <= b - a:
            prog.put(bank, a, blob, f"table {name}")
            if len(blob) < b - a:
                prog.vacate(bank, a + len(blob), b - a - len(blob))
        else:
            prog.vacate(bank, a, b - a)
            off = prog.alloc(bank, len(blob))
            prog.put(bank, off, blob, f"table {name} (moved)")
            addr = 0x6000 + off
            for hi_pos, lo_pos, _s in sites:
                prog.put(bank, hi_pos, bytes([addr >> 8]), f"table {name} base hi")
                prog.put(bank, lo_pos, bytes([addr & 0xFF]), f"table {name} base lo")
            stat["moved"] += 1
    # ② 리터럴 문자열
    lits = scan_literals(prog)
    table_spans = [(bank, a, b) for _n, bank, a, b in TABLES]
    # 꼬리를 나눠 쓰는 문자열(한 문자열이 다른 문자열의 끝에서 시작) — 하나를 옮기면 다른 쪽이 깨지므로 둘 다 건드리지 않는다
    spans = sorted((bank, off, prog.o(bank, 0, layout.BANK).index(0, off)) for bank, off in lits)
    aliased = set()
    tails: dict[tuple[int, int], tuple[int, int]] = {}  # 앞 문자열 → 같은 끝을 나눠 쓰는 뒤 문자열(꼬리) — 둘 다 번역하고 꼬리 포인터를 새 끝으로 옮긴다
    for (b1, o1, e1), (b2, o2, e2) in itertools.pairwise(spans):
        if b1 == b2 and o2 <= e1:
            if e2 == e1 and o2 > o1 and (b1, o1) not in tails:
                tails[(b1, o1)] = (b2, o2)
            else:
                aliased |= {(b1, o1), (b2, o2)}
    tail_children = set(tails.values())
    pending: dict[int, list] = {}
    inplace: dict[int, list] = {}
    for (bank, off), sites in sorted(lits.items()):
        if any(bank == tb and ta <= off < te for tb, ta, te in table_spans):
            continue
        if (bank, off) in aliased or (bank, off) in tail_children:
            if (bank, off) not in tail_children:
                stat["literal_kept"] += 1
            continue
        s = prog.o(bank, 0, layout.BANK)
        end = s.index(0, off)
        raw = s[off:end]
        miss = MISSING.setdefault("literal", set())
        parts = []
        # 줄바꿈(0D)으로 줄을 나눠 줄마다 번역한다 — 한 줄이라도 정본에 없으면 문자열 전체를 원문으로 둔다
        lines = raw.split(b"\x0d")
        for line in lines:
            r = translate(line, CONTEXT.get((bank, off)), miss)
            parts.append(r if r is not None else line)
        if all(isinstance(p, bytes) for p in parts):
            import msgs  # 지연 임포트 — msgs 가 이 모듈을 쓴다

            newb = msgs.translate(raw, tab)  # 자리표(이름·수)가 낀 문장 — 정본 문장 틀과 맞댄다
            if newb is None:
                if _has_kana_or_kanji(raw):
                    miss.add(jptext.decode(raw).replace("\n", "/"))
                stat["literal_kept"] += 1
                continue
        else:
            rendered = [render(p, tab) if not isinstance(p, bytes) else p for p in parts]
            # 일부 줄만 정본에 걸리면(나머지는 일본어) 혼합이다 — 이름·수 자리표가 낀 문장은 조각 맞춤(`msgs.segments`)으로 한 번 더 본다
            if any(isinstance(p, bytes) and _has_kana_or_kanji(p) for p in parts):
                import msgs

                alt = msgs.translate(raw, tab)
                if alt is None:  # 그래도 안 되면 문자열 전체를 원문으로 둔다(문자열 전체 판정)
                    miss.add(jptext.decode(raw).replace("\n", "/"))
                    stat["literal_kept"] += 1
                    continue
                newb = alt
            else:
                newb = b"\x0d".join(rendered)
        tail = tails.get((bank, off))
        if tail is not None:  # 꼬리 문자열(「…{14}に」 의 「に」)도 번역해 앞 문자열의 끝에 겹치게 한다 — 안 겹치면 둘 다 원문으로 둔다
            import msgs

            rawt = s[tail[1] : end]
            tl = [translate(x, CONTEXT.get(tail), miss) for x in rawt.split(b"\x0d")]
            newt = b"\x0d".join(render(p, tab) if p is not None else x for p, x in zip(tl, rawt.split(b"\x0d"), strict=True))
            if newt == rawt or not newb.endswith(newt) or len(newb) == len(newt):
                stat["literal_kept"] += 1
                continue
            refs = [(pos, len(newb) - len(newt)) for pos in lits[tail]]
            # 꼬리의 꼬리 — 같은 NUL 을 가리키는 **빈 문자열**(`자기 자신에게`의 「대상 없음」 항목: 아이템 사용 줄 첫 `1A`) 포인터도 새 문자열의 끝(NUL)으로 옮긴다.
            # 안 옮기면 옛 NUL 자리가 새 글 한복판이 되어 화면에 그 꼬리가 찍힌다(10-13 「아트라스는 비를 했다.」 — 방어 준비 문장의 끝토막).
            chain, ok = tail, True
            while chain in tails:
                chain = tails[chain]
                if s[chain[1] : end] != b"":
                    ok = False
                    break
                refs += [(pos, len(newb)) for pos in lits[chain]]
            if not ok:
                stat["literal_kept"] += 1
                continue
            EXTRA_REFS[(bank, off)] = refs
        if len(newb) <= len(raw):
            inplace.setdefault(bank, []).append((off, raw, newb, sites))
        else:
            pending.setdefault(bank, []).append((off, raw, newb, sites))
    _place_pending(prog, pending, inplace, stat)
    if report is not None:
        report.update(stat)


FAR_BANKS = (0x6A, 0x6B, 0x71, 0x6C, 0x6D)  # 문자열을 옮겨 둘 뱅크(0xFF 패딩이 넉넉한 곳)


def _far_ok(prog: layout.Prog, bank: int, item) -> bool:
    s0 = prog.o(bank, 0, layout.BANK)
    return all(s0[p - 4 : p] == b"\x20\x3e\x50\x2c" for p in item[3])


def _place_far(prog: layout.Prog, bank: int, item, stat: dict) -> bool:
    """같은 뱅크에 자리가 없는 문자열을 **다른 뱅크로** 옮긴다. 호출부 `JSR $503E · BIT $addr`(6B)를 `JSR 중계 · NOP×3` 으로 바꾸고,
    중계(뱅크 0x68 의 0 칸, `$4000` 에 늘 걸려 있다)가 문자열 뱅크를 MPR4(`$8000`)에 걸어 `$7C/$7D` 를 주고 `$5066`(복사 루프)을 부른 뒤 되돌린다.
    `$503E` 가 하는 일은 피연산자 읽기 + `$7C/$7D` 설정 + `$5066` 분기뿐이라 같은 결과다. `$4ED5` 변형 호출부는 못 바꾼다(False)."""
    off, raw, newb, sites = item
    s0 = prog.o(bank, 0, layout.BANK)
    if any(s0[p - 4 : p] != b"\x20\x3e\x50\x2c" for p in sites):
        return False
    far = next((b for b in FAR_BANKS if b != bank and prog.fits(b, len(newb) + 1)), None)
    if far is None or not prog.fits(0x68, 22):
        return False
    f_off = prog.alloc(far, len(newb) + 1)
    t_off = prog.alloc(0x68, 22)
    win = 0x8000 + f_off
    code = bytes(
        [
            0x43,
            0x10,
            0x48,
            0xA9,
            far,
            0x53,
            0x10,
            0xA9,
            win & 0xFF,
            0x85,
            0x7C,
            0xA9,
            win >> 8,
            0x85,
            0x7D,
        ]
        + [0x20, 0x66, 0x50, 0x68, 0x53, 0x10, 0x60]
    )
    assert len(code) == 22
    prog.put(far, f_off, newb + b"\x00", f"literal {bank:02X}+{off:04X} (far)")
    prog.put(0x68, t_off, code, f"literal {bank:02X}+{off:04X} relay")
    t_addr = 0x4000 + t_off
    for p in sites:
        prog.put(
            bank,
            p - 4,
            bytes([0x20, t_addr & 0xFF, t_addr >> 8, 0xEA, 0xEA, 0xEA]),
            f"literal {bank:02X}+{off:04X} call",
        )
    prog.vacate(bank, off, len(raw) + 1)
    stat["literal"] += 1
    stat["moved"] += 1
    return True


EXTRA_REFS: dict[tuple[int, int], list[tuple[int, int]]] = {}  # 문자열 시작 → [(꼬리 포인터 위치, 시작에서 꼬리까지 새 오프셋)]
INTERIOR_WARN: list[str] = []  # 문자열 안쪽을 코드가 직접 쓰는데 새 문자열에 짝을 못 찾은 자리(관리자 후보 아님 — 화면에서 깨진다)
_STORE_OPS = {0x8D, 0x8E, 0x8C, 0x9C, 0xEE, 0xCE}  # STA/STX/STY/STZ/INC/DEC abs


def _ctrl_spans(raw: bytes) -> list[tuple[int, bytes]]:
    """제어 토큰의 (오프셋, 바이트) 목록 — 글·여백 토큰은 건너뛴다."""
    out, pos = [], 0
    for kind, b in tokens(raw):
        if kind == "ctrl" and b[0] not in (0x0E, 0x0F):  # 가나 모드 토글은 한국어에서 사라진다 — 짝 맞춤에서 뺀다
            out.append((pos, b))
        pos += len(b)
    return out


def _remap_interior(prog: layout.Prog, bank: int, off: int, raw: bytes, newb: bytes, new_off: int) -> None:
    """🔴 게임 코드가 **문자열 안쪽을 고정 주소로 직접 쓰는** 자리를 새 문자열에 맞춘다 — 필드 메뉴는 파티가 한 명이면 마지막 줄 끝 `0D` 를 `00` 으로 덮어
    「その他」 뒤를 자르고(주소 `$6332`), 전투 설정·도구 창은 줄머리 `01` 을 덮어 항목을 켜고 끈다. 한국어로 줄 길이가 바뀌면 그 주소가 글 한복판을 가리켜
    **줄이 잘리거나 항목이 사라진다**(10-13 「기타」 빈칸 · 「FFFF」). 쓰는 바이트가 든 **제어 토큰의 순번**으로 새 문자열의 같은 제어 토큰 자리를 찾아 피연산자를 바꾼다."""
    d = prog.o(bank, 0, layout.BANK)
    lo, hi = 0x6000 + off, 0x6000 + off + len(raw)
    sites = [(i, (d[i + 1] | d[i + 2] << 8) - lo) for i in range(len(d) - 2) if d[i] in _STORE_OPS and lo < (d[i + 1] | d[i + 2] << 8) < hi]
    if not sites:
        return
    oc, nc = _ctrl_spans(raw), _ctrl_spans(newb)
    for code_pos, k in sites:
        m = next((n for n, (p, b) in enumerate(oc) if p <= k < p + len(b)), None)
        if m is None or len(oc) != len(nc):
            INTERIOR_WARN.append(f"{bank:02X}+{off:04X} k={k} (코드 {bank:02X}+{code_pos:04X})")
            continue
        new_k = nc[m][0] + (k - oc[m][0])
        if new_off == off and new_k == k:
            continue
        prog.put(bank, code_pos + 1, (0x6000 + new_off + new_k).to_bytes(2, "little"), f"interior write {bank:02X}+{code_pos:04X} → +{new_k}")


def _place_pending(
    prog: layout.Prog, pending: dict[int, list], inplace: dict[int, list], stat: dict
) -> None:
    """바꾼 문자열을 뱅크마다 **한꺼번에** 앉힌다. 제자리에 들어가는 것(`inplace`)과 옮겨야 하는 것(`pending`)을 같이 본다.
    옮길 것은 큰 것부터 가장 작은 맞는 빈 곳에, 한국어가 똑같은 것은 한 벌만. 모자라면 **복사 변형(`$503E`) 호출부의 문자열을 다른 뱅크로**
    보내(`_place_far`) 자리를 낸다 — 제자리 것도 원래 칸을 통째로 돌려준다. 그래도 못 앉는 것은 원문을 두고 `OVERFLOW`(가장 큰 실패 하나를 빼고 다시 본다)."""
    for bank in sorted(set(pending) | set(inplace)):
        items = sorted(pending.get(bank, []))
        stay = sorted(inplace.get(bank, []))
        while items:
            uniq = sorted({i[2] for i in items})
            plus = [(i[0], len(i[1]) + 1) for i in items] + [
                (o + len(n) + 1, len(r) - len(n)) for o, r, n, _s in stay if len(r) > len(n)
            ]
            fails = prog.pack_failures(bank, [len(u) + 1 for u in uniq], plus)
            if not fails:
                break
            movable = [("p", i) for i in items if _far_ok(prog, bank, i)] + [
                ("s", i) for i in stay if _far_ok(prog, bank, i) and len(i[1]) >= 8
            ]
            moved = False
            for kind, it in sorted(
                movable, key=lambda m: -(len(m[1][1]) + 1 if m[0] == "s" else len(m[1][2]))
            ):
                if _place_far(prog, bank, it, stat):
                    (items if kind == "p" else stay).remove(it)
                    moved = True
                    break
            if moved:
                continue
            drop = uniq[max(fails, key=lambda k: len(uniq[k]))]
            for it in [i for i in items if i[2] == drop]:
                items.remove(it)
                OVERFLOW.append(
                    (
                        bank,
                        it[0],
                        len(it[1]) + 1,
                        len(it[2]) + 1,
                        jptext.decode(it[1]).replace("\n", "/"),
                    )
                )
                stat["literal_kept"] += 1
        for off, raw, newb, _s in stay:
            _remap_interior(prog, bank, off, raw, newb, off)
            prog.put(bank, off, newb + b"\x00", f"literal {bank:02X}+{off:04X}")
            for pos, delta in EXTRA_REFS.get((bank, off), []):
                prog.put(bank, pos, (0x6000 + off + delta).to_bytes(2, "little"), f"literal {bank:02X}+{off:04X} tail ref")
            if len(newb) < len(raw):
                prog.vacate(bank, off + len(newb) + 1, len(raw) - len(newb))
            stat["literal"] += 1
        for off, raw, _n, _s in items:
            prog.vacate(bank, off, len(raw) + 1)
        groups: dict[bytes, list] = {}
        for it in items:
            groups.setdefault(it[2], []).append(it)
        for newb, its in sorted(groups.items(), key=lambda kv: (-len(kv[0]), kv[0])):
            n_off = prog.alloc(bank, len(newb) + 1)
            first = its[0]
            prog.put(bank, n_off, newb + b"\x00", f"literal {bank:02X}+{first[0]:04X} (moved)")
            addr = 0x6000 + n_off
            for off, raw_, _n, sites in its:
                for pos, delta in EXTRA_REFS.get((bank, off), []):
                    prog.put(bank, pos, (0x6000 + n_off + delta).to_bytes(2, "little"), f"literal {bank:02X}+{off:04X} tail ref")
                _remap_interior(prog, bank, off, raw_, newb, n_off)
                for pos in sites:
                    prog.put(
                        bank, pos, addr.to_bytes(2, "little"), f"literal {bank:02X}+{off:04X} ref"
                    )
                stat["literal"] += 1
                stat["moved"] += 1


def _has_kana_or_kanji(b: bytes) -> bool:
    jp = re.sub(r"\{[0-9A-F ]+\}", "", jptext.decode(b)).replace("　", "")
    return not _is_latin(jp)


def is_menu_chunk(d: bytes) -> bool:
    """패키지의 짧은 메뉴 덩이(상점 「살래요/팔래요」 · 「예/아니오」) — 줄마다 `01` 로 시작하고 대사 제어(`12`~`16`)가 없다."""
    lines = d.split(b"\x00")[:-1]
    if not lines or len(lines) > 2:
        return False
    for l in lines:
        t = tokens(l)
        if not any(k == "ctrl" and b[0] == 0x01 for k, b in t) or any(
            k == "ctrl" and b[0] in (0x12, 0x13, 0x14, 0x16) for k, b in t
        ):
            return False
    return True


def edit_menu_chunk(d: bytes, tab, miss: set) -> bytes:
    out = []
    for line in d.split(b"\x00")[:-1]:
        parts = [translate(x, None, miss) for x in line.split(b"\x0d")]
        if any(p is None for p in parts):
            out.append(line)
            continue
        out.append(b"\x0d".join(render(p, tab) for p in parts))
    return b"".join(x + b"\x00" for x in out)
