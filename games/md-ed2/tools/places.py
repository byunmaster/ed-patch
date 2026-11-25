"""필드 HUD 지명 표 — 65 레코드(06 종결 · 앞 공백으로 가운데), 워드 오프셋 표로 찾는다.

    python3 tools/places.py          # 표 구조 검산 + 우리 표기 대조

구조(2026-10-12 실측, ED1 `$1EB5A` 와 같은 조회 루틴):
- 0x3B256 = **개수 워드(65)** + 65 워드 — 레코드 i 는 `(0x3B258 + 2i) + 워드[i]` 에 있다(자기 워드 주소 기준 상대).
- 레코드 = 앞 공백 + 이름 + `06`. 레코드 0 은 공백 열둘(빈 칸), 1~6 은 도시 여섯(ED1 의 place_a), 7~64 는 나머지 지명·길 이름.
- 소비자 셋(0x22870 · 0x228A2 · 0x32AB4)이 **06 까지** 복사한다(길이 무제한) — 그래서 레코드 길이를 바꿔도 되고,
  구역(0x3B2DA~0x3B5A8, 뒤는 다른 표)을 다시 깔며 오프셋 표를 같이 고친다. 이름 최대폭은 원문대로 12B(반각 가나 포함).

우리 표기는 사전(고유명사 `place`)에서 읽는다 — 게임 폴더에 표를 두지 않는다. 길 이름(「A～B」)은 부분마다 읽어 `～` 로 잇는다.
"""

import struct
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import captions
import common
import dict_names
import field_hud
import hangul

from shared import canon

BASE = 0x3B256  # 개수 워드
REGION = (0x3B2DA, 0x3B5A8)  # 레코드 구역 — 뒤(0x3B5A8~)는 다른 표(lea 로 참조)라 못 쓴다
OFFSETS = (BASE + 2, BASE + 2 + 2 * 65)
CENTER = 14  # 가운데 맞춤 기준 폭(B) — 지명 칸 안쪽 90px ÷ 반각 6.3px ≈ 14B(실측 11-08: 칸 안쪽 x3~92, 반각 6.3px·한글 12.3px, 첫 글자 시작 x6). 원문 최장은 12B 였다
WIDTH = 14  # 이름 최대 폭(B) — 복사 루프가 06 까지라 길이 무제한, 칸(박스)은 한글 8자쯤까지 들어간다(2026-10-12 시험 롬: 9자는 왼쪽이 잘렸다) → 7자(14B)까지
# ── 마을 HUD 전용 표(마스터 11-09 「최대한 가운데」, 관리자 11-09 「레코드 복제 말고 다른 길」) ──
# 마을 HUD(0x22864 길)와 월드 HUD(0x22892 길 · 첫 루틴)가 같은 레코드를 읽는데 월드는 입구·방위 둘이 이미 왼쪽 쏠림(−2~−3px)이라 레코드를 같이 옮길 수 없다.
# 마을 길의 `lea 0x3B256,a1` 피연산자만 새 오프셋 표로 돌린다 — 새 표는 옛 레코드(월드·워프가 계속 읽는다)를 그대로 가리키고, 마을 이름이 오른쪽으로 치우친 32곳(좌−우 +1~+2px, 11-09 잉크 경계 실측)만
# **글자마다 1px 왼쪽으로 민 합성 글자**(PUA U+E400~, 코드 자리는 `hangul_codes.json`)로 쓴 마을 전용 문자열을 가리킨다. 글리프 잉크가 칸 1열부터라 한 열 밀어도 안 잘린다(2px 는 잘려 못 한다 → +2 는 0, +1 은 −1 동점이라 왼쪽).
# 공간은 엔딩 자막을 꼬리로 옮기고 남은 옛 영역 둘(0x34E86·0x34FF8, 독약 대조 11-07 로 읽히지 않음 확인)이다.
TOWN_TABLE_SITE = 0x22870  # `lea.l $3b256.l,a1`(0x2286e) 의 32비트 피연산자
TOWN_SPANS = captions.TOWN_CARVE  # {"ending-a": (lo,hi), "ending-b": (lo,hi)}
_TOWN_NAMES = (
    "엘아스타 루디아 베르가 네리아 론도 랄파 시리카 마스쿤 낫슈 암다 세달 보아드해운 루드라 카울 바즈눈 나슬 이슈타 아훌 이즈 큐베라 베른 유이시스 "
    "곶의동굴 시련의동굴 왕가의묘 아네스의탑 네사의변토 안뜰 테크니카 옥좌의방 라누라 모레스톤")
TOWN_SHIFT = frozenset(_TOWN_NAMES.split())  # 11-09 마을 HUD 전수 실측(잉크 경계, 빈 칸 차분 — `center-all/town-hud-before-after.tsv`)에서 좌−우 ≥ +1px 인 이름. 한 열 밀면 좌−우가 2 줄어: +2→0, +1→−1(동점이라 왼쪽). 「～」·가운뎃점이 낀 이름 넷은 제외(그 글자는 원본 글리프라 못 민다)
TOWN_PUA_BASE = 0xE400
_town_registered = False


def _town_syllables() -> list[str]:
    return sorted({c for n in TOWN_SHIFT for c in n})


def town_pua(ch: str) -> str:
    return chr(TOWN_PUA_BASE + _town_syllables().index(ch))


def ensure_town_glyphs() -> None:
    """마을 전용 합성 글자 — 표 0 글리프를 한 열 왼쪽으로 민 것(채움·테두리 모두 같은 규칙이 구울 때 새로 그려진다)."""
    global _town_registered
    if _town_registered:
        return
    for ch in _town_syllables():
        f = hangul.glyph_fill(ch)
        if any(row[0] for row in f):
            raise SystemExit(f"마을 합성 글자 「{ch}」 가 0열에 잉크가 있다 — 한 열 밀면 잘린다")
        hangul.CUSTOM_GLYPHS[town_pua(ch)] = [row[1:] + [0] for row in f]
    _town_registered = True


def town_chars() -> set[str]:
    ensure_town_glyphs()
    return {town_pua(c) for c in _town_syllables()}


SEP = "～"
# 단독 「城」(길 이름의 끝) — 정본에 단독 항목은 없고 접미 규칙(「の城」)의 값을 쓴다
CASTLE_KEY = "の城@지명칸"


def records(d: bytes) -> list[tuple[int, bytes]]:
    """레코드 → [(자리, 본문(06 앞))] — 오프셋 표를 따라간다."""
    n = struct.unpack(">H", d[BASE : BASE + 2])[0]
    out = []
    for i in range(n):
        wa = BASE + 2 + 2 * i
        r = wa + struct.unpack(">H", d[wa : wa + 2])[0]
        out.append((r, d[r : d.index(6, r)]))
    return out


def jp_of(raw: bytes) -> str:
    """원문 → 정규화(반각 가나 → 전각, 공백 제거, 물결표 통일)."""
    t = unicodedata.normalize("NFKC", raw.decode("cp932", "replace")).strip()
    return t.replace("~", SEP)


def _part(p: str) -> str | None:
    v = dict_names.from_dict(p, ("place",)) or dict_names.from_canon(p, "place")
    if v is None and p == "城":
        v = canon.table("ui", "ed1").get(CASTLE_KEY)
    return v


def kr(jp: str) -> str | None:
    """원문 지명 → 우리 표기(없으면 None)."""
    parts = [_part(p) for p in jp.split(SEP)]
    return None if any(p is None for p in parts) else SEP.join(parts)


def _bytes(s: str) -> int:
    return sum(1 if ord(c) < 0x80 else 2 for c in s)


def table(d: bytes | None = None) -> dict:
    """`{색인: {jp, ours, src}}` — `dict_names.names()` 가 같은 모양으로 합친다(글자 수집·검사가 같이 본다)."""
    d = d if d is not None else common.rom()
    out = {}
    for i, (_p, raw) in enumerate(records(d)):
        jp = jp_of(raw)
        v = kr(jp) if jp else ""
        out[str(i)] = {"jp": jp, "ours": v or "", "src": "glossary" if v else ""}
    return out


def want_body(raw: bytes, ours: str, encode) -> bytes | None:
    """레코드 한 개의 의도한 본문(06 앞). 번역 있으면 앞 공백 `(CENTER−길이)//2` + 이름, 없으면 원문(전부 공백인 빈 레코드는 한 칸).
    WIDTH 를 넘으면 None."""
    if not ours:
        return b" " if raw.strip(b" ") == b"" else raw
    if ours in field_hud.CONDENSED_NAMES:  # 길 A 긴 이름 둘 — 콘덴스드 8px 합성 글자(접미와 같은 방식), 앞 공백은 따로 정한 칸 수
        return b" " * field_hud.CONDENSED_LEAD + encode("".join(field_hud.CONDENSED_NAMES[ours]))
    enc = encode(ours)
    if len(enc) > WIDTH:
        return None
    return b" " * max(0, (CENTER - len(enc)) // 2) + enc


def plan(d: bytes, names: dict, encode) -> list[tuple[str, int, bytes]]:
    """정본 → 쓰기(라벨, 자리, 바이트). 구역을 앞에서부터 다시 깔고(번역 없는 레코드는 원본 그대로) 오프셋 표를 다시 쓴다.

    이름은 14B 칸 기준 **앞 공백 (14−길이)/2**(내림 — 홀수 여백의 반 칸 ≈3px 은 오른쪽에 남는다, 14B 이름은 0) 로 가운데(뒤 공백 없음; 11-08 이전엔 12 기준이라 왼쪽으로 한 칸쯤 쏠렸다). 14B 를 넘는 이름은 실패로 모아 알린다.
    """
    recs = records(d)
    blob = bytearray()
    starts = []
    over = []
    placed: dict[
        bytes, int
    ] = {}  # 같은 본문은 한 번만 — 중복을 합쳐 칸을 아낀다(앞 공백이 늘어 구역이 빠듯하다)
    for i, (_p, raw) in enumerate(recs):
        body = want_body(raw, names.get(str(i), {}).get("ours", ""), encode)
        if body is None:  # 칸 판정 대기 — 원문 그대로 두고 알린다(줄이지 않는다)
            over.append(f"place[{i}] {names[str(i)]['ours']!r} > {WIDTH}B")
            body = raw
        if body not in placed:
            placed[body] = REGION[0] + len(blob)
            blob += body + b"\x06"
        starts.append(placed[body])
    for line in over:
        print(f"  ⚠ 지명 표 칸 넘침(원문 그대로 둔다 — 관리자 판정 대기): {line}")
    room = REGION[1] - REGION[0]
    if len(blob) > room:
        raise SystemExit(f"지명 표가 구역 {room}B 를 {len(blob) - room}B 넘는다")
    offs = b"".join(struct.pack(">H", s - (BASE + 2 + 2 * i)) for i, s in enumerate(starts))
    blob += b" " * (room - len(blob))  # 남는 자리 — 레코드가 아니다(06 으로 끝난 뒤)
    out = [("table:place_list", REGION[0], bytes(blob)), ("table:place_offsets", OFFSETS[0], offs)]
    return out + town_plan(recs, names, encode, starts)


def town_body(ours: str, raw: bytes, encode) -> bytes | None:
    """마을 전용 레코드 본문(06 앞) — 치우친 이름이면 한 열 민 글자로, 아니면 None(옛 레코드를 그대로 가리킨다)."""
    if ours in field_hud.CONDENSED_NAMES:  # 길 A(「입구」 접미 22px) 때문에 좁게 굽는 둘 — 접미가 없는 마을 HUD 에선 보통 12px 글자(14B 칸에 6자 12B 가 든다, 마스터 11-10)
        enc = encode(ours)
        return b" " * max(0, (CENTER - len(enc)) // 2) + enc if len(enc) <= WIDTH else None
    if ours not in TOWN_SHIFT:
        return None
    ensure_town_glyphs()
    plain = want_body(raw, ours, encode)
    if plain is None:
        return None
    return b" " * (len(plain) - len(plain.lstrip(b" "))) + encode("".join(town_pua(c) for c in ours))


def town_plan(recs, names, encode, starts) -> list[tuple[str, int, bytes]]:
    """새 오프셋 표(66 워드: 개수 + 65) + 마을 전용 문자열 — 엔딩 옛 영역 둘에 앉히고 남는 칸은 0 으로 채운다."""
    (a_lo, a_hi), (b_lo, b_hi) = TOWN_SPANS["ending-a"], TOWN_SPANS["ending-b"]
    table_at = a_lo
    strs_a = a_lo + 2 + 2 * 65  # 표 뒤
    spans = [[strs_a, a_hi, bytearray()], [b_lo, b_hi, bytearray()]]
    placed: dict[bytes, int] = {}
    target = []
    for i, (_p, raw) in enumerate(recs):
        body = town_body(names.get(str(i), {}).get("ours", ""), raw, encode)
        if body is None:
            target.append(starts[i])
            continue
        if body not in placed:
            for sp in spans:
                if sp[0] + len(sp[2]) + len(body) + 1 <= sp[1]:
                    placed[body] = sp[0] + len(sp[2])
                    sp[2] += body + b"\x06"
                    break
            else:
                raise SystemExit("마을 전용 문자열 자리가 모자란다(엔딩 옛 영역 둘)")
        target.append(placed[body])
    tbl = struct.pack(">H", 65) + b"".join(
        struct.pack(">H", (t - (table_at + 2 + 2 * i)) & 0xFFFF) for i, t in enumerate(target)
    )
    a_blob = tbl + bytes(spans[0][2])
    a_blob += b"\x00" * (a_hi - a_lo - len(a_blob))
    b_blob = bytes(spans[1][2]) + b"\x00" * (b_hi - b_lo - len(spans[1][2]))
    site = struct.pack(">I", table_at)
    return [
        ("town-table-a", a_lo, a_blob),
        ("town-table-b", b_lo, b_blob),
        ("town-table-site", TOWN_TABLE_SITE, site),
    ]


def verify_readback(buf: bytes, d: bytes, names: dict, encode) -> int:
    """🔴 되읽기 게이트 — 구운 이미지에서 개수 워드·오프셋 표를 **따라가** 읽은 레코드 65개가 의도(번역 있으면 가운데 정렬한 이름,
    없으면 원문)와 같은지. 오프셋 표가 조용히 어긋나면 지명이 엉뚱한 칸에 뜬다."""
    old = records(d)
    new = records(buf)
    if len(new) != len(old):
        raise SystemExit(f"지명 되읽기: 레코드 수 {len(new)} ≠ {len(old)}")
    for i, ((_p, raw), (_q, got)) in enumerate(zip(old, new, strict=True)):
        ours = names.get(str(i), {}).get("ours", "")
        want = want_body(raw, ours, encode)
        if want is None:
            want = raw
        if got != want:
            raise SystemExit(f"지명 되읽기 {i}: 구운 레코드가 의도와 다르다")
        # 마을 전용 표 — 새 표를 따라가 읽은 레코드가 (치우친 이름이면) 한 열 민 글자, 아니면 같은 레코드인지
        tb = TOWN_SPANS["ending-a"][0]
        at = tb + 2 + 2 * i
        w = struct.unpack(">h", buf[at : at + 2])[0]
        end = buf.index(b"\x06", at + w)
        tgot = bytes(buf[at + w : end])
        tw = town_body(ours, raw, encode)
        if tgot != (tw if tw is not None else want):
            raise SystemExit(f"마을 지명 표 되읽기 {i}: 구운 레코드가 의도와 다르다")
    if struct.unpack(">I", buf[TOWN_TABLE_SITE : TOWN_TABLE_SITE + 4])[0] != TOWN_SPANS["ending-a"][0]:
        raise SystemExit("마을 지명 표 피연산자가 새 표를 가리키지 않는다")
    return len(new)


def allowed() -> dict[str, tuple[int, int]]:
    return {
        "table:place_list": REGION,
        "table:place_offsets": OFFSETS,
        "town-table-a": TOWN_SPANS["ending-a"],
        "town-table-b": TOWN_SPANS["ending-b"],
        "town-table-site": (TOWN_TABLE_SITE, TOWN_TABLE_SITE + 4),
    }


def check(d: bytes) -> None:
    recs = records(d)
    if len(recs) != 65:
        raise SystemExit(f"지명 표 레코드 {len(recs)} (기대 65)")
    pos = REGION[0]
    for i, (p, raw) in enumerate(recs):
        if p != pos:
            raise SystemExit(f"지명 표 {i}: 자리 {p:#x} ≠ 연속 {pos:#x}")
        pos = p + len(raw) + 1
    if pos != REGION[1]:
        raise SystemExit(f"지명 표 끝 {pos:#x} ≠ 구역 끝 {REGION[1]:#x}")
    t = table(d)
    miss = [(i, e["jp"]) for i, e in t.items() if e["jp"] and not e["ours"]]
    over = [(i, e["ours"]) for i, e in t.items() if e["ours"] and _bytes(e["ours"]) > WIDTH]
    print(
        f"  지명 표 65 레코드 · 우리 표기 {sum(1 for e in t.values() if e['ours'])} · 없음 {miss} · 12B 초과 {over}"
    )


if __name__ == "__main__":
    check(common.rom())
