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
import common
import dict_names

from shared import canon

BASE = 0x3B256  # 개수 워드
REGION = (0x3B2DA, 0x3B5A8)  # 레코드 구역 — 뒤(0x3B5A8~)는 다른 표(lea 로 참조)라 못 쓴다
OFFSETS = (BASE + 2, BASE + 2 + 2 * 65)
CENTER = 12  # 가운데 맞춤 기준 폭(B) — 원문 최장이 12B
WIDTH = 14  # 이름 최대 폭(B) — 복사 루프가 06 까지라 길이 무제한, 칸(박스)은 한글 8자쯤까지 들어간다(2026-10-12 시험 롬: 9자는 왼쪽이 잘렸다) → 7자(14B)까지
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


def plan(d: bytes, names: dict, encode) -> list[tuple[str, int, bytes]]:
    """정본 → 쓰기(라벨, 자리, 바이트). 구역을 앞에서부터 다시 깔고(번역 없는 레코드는 원본 그대로) 오프셋 표를 다시 쓴다.

    이름은 12B 칸 기준 **앞 공백 (12−길이)/2**(14B 이름은 0) 로 가운데(원본이 하던 그대로, 뒤 공백 없음). 12B 를 넘는 이름은 실패로 모아 알린다.
    """
    recs = records(d)
    blob = bytearray()
    starts = []
    over = []
    for i, (_p, raw) in enumerate(recs):
        ours = names.get(str(i), {}).get("ours", "")
        if ours:
            enc = encode(ours)
            if len(enc) > WIDTH:  # 칸 판정 대기 — 원문 그대로 두고 알린다(줄이지 않는다)
                over.append(f"place[{i}] {ours!r} {len(enc)}B > {WIDTH}B")
                body = raw
            else:
                body = b" " * max(0, (CENTER - len(enc)) // 2) + enc
        else:
            body = raw
        starts.append(REGION[0] + len(blob))
        blob += body + b"\x06"
    for line in over:
        print(f"  ⚠ 지명 표 칸 넘침(원문 그대로 둔다 — 관리자 판정 대기): {line}")
    room = REGION[1] - REGION[0]
    if len(blob) > room:
        raise SystemExit(f"지명 표가 구역 {room}B 를 {len(blob) - room}B 넘는다")
    offs = b"".join(struct.pack(">H", s - (BASE + 2 + 2 * i)) for i, s in enumerate(starts))
    blob += b" " * (room - len(blob))  # 남는 자리 — 레코드가 아니다(06 으로 끝난 뒤)
    return [("table:place_list", REGION[0], bytes(blob)), ("table:place_offsets", OFFSETS[0], offs)]


def verify_readback(buf: bytes, d: bytes, names: dict, encode) -> int:
    """🔴 되읽기 게이트 — 구운 이미지에서 개수 워드·오프셋 표를 **따라가** 읽은 레코드 65개가 의도(번역 있으면 가운데 정렬한 이름,
    없으면 원문)와 같은지. 오프셋 표가 조용히 어긋나면 지명이 엉뚱한 칸에 뜬다."""
    old = records(d)
    new = records(buf)
    if len(new) != len(old):
        raise SystemExit(f"지명 되읽기: 레코드 수 {len(new)} ≠ {len(old)}")
    for i, ((_p, raw), (_q, got)) in enumerate(zip(old, new, strict=True)):
        ours = names.get(str(i), {}).get("ours", "")
        enc = encode(ours) if ours else b""
        want = b" " * max(0, (CENTER - len(enc)) // 2) + enc if ours and len(enc) <= WIDTH else raw
        if got != want:
            raise SystemExit(f"지명 되읽기 {i}: 구운 레코드가 의도와 다르다")
    return len(new)


def allowed() -> dict[str, tuple[int, int]]:
    return {"table:place_list": REGION, "table:place_offsets": OFFSETS}


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
