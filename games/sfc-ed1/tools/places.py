"""맵ID → 지명 — HUD 지명(A6③)·세이브 슬롯 지명(A5)을 한글로 굽는다.

원본은 포인터 표 둘(`$02:A793` · `$02:A8B1` = 필드 HUD·로드 슬롯 목록, 뱅크 `$02` 2바이트)이 10칸 문자열(`$FF` 끝)을
가리키고, `$02:A67F`·`$02:A6DB` 가 그걸 칸 배열 `$0305` 에 **바이트 그대로** 옮긴다 — 대사 훅을 안 거쳐
한글 2바이트를 못 푼다(슬롯 목록의 「운겠다터저속태사」). ⇒ 한글 문자열과 새 포인터 표를 사전 뱅크에 굽고,
복사 루프를 훅의 `placecopy_*`(= `namecopy` 와 같은 꼴 — 선두 코드면 글리프를 잡는다)로 바꾼다(`hook.PLACE_SITES`).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001  (common 보다 먼저)
import common
import dicts
import encode

TABLES = {"a": (0x02A793, 160), "b": (0x02A8B1, 149)}  # (원본 포인터 표, 항목 수)
CELLS = 10


def names() -> dict[str, str]:
    d = json.loads((common.GAME_DIR / "textmap" / "places.json").read_text(encoding="utf-8"))
    return d["names"]


def texts() -> list[str]:
    return list(names().values())


def _orig(rom: bytes, base: int, i: int) -> str:
    o = common.snes2off(base) + 2 * i
    p = rom[o] | rom[o + 1] << 8
    so = common.snes2off(0x020000 | p)
    return text.decode(rom[so : rom.index(b"\xff", so)], text.resolver(rom)).strip("　")


def _encode(kr: str, rep_index: dict[str, int]) -> bytes:
    if len(kr) > CELLS:
        raise SystemExit(f"지명 {kr!r} 이 {CELLS}칸을 넘는다")
    pad = (CELLS - len(kr)) // 2
    b = bytearray([encode.KR_TABLE[" "]] * pad)
    for ch in kr:
        if encode.is_glyph(ch):
            b += encode.glyph_code(rep_index[ch])
        elif ch in encode.KR_TABLE:
            b.append(encode.KR_TABLE[ch])
        else:
            raise SystemExit(f"지명에 못 넣는 글자: {ch!r}")
    b.append(dicts.TERM)  # 복사 루프가 `$FF` 에서 멈추고 나머지 칸을 공백으로 채운다
    return bytes(b)


def bake(out: bytearray, rom: bytes, rep_index: dict[str, int], org: int) -> dict:
    """사전 뱅크 `org` 부터 포인터 표 둘 + 문자열을 굽는다 → {"a": 표 롱주소, "b": …, "next": …}."""
    kr = names()
    info: dict = {}
    cur = org
    tables = {}
    for key, (_base, n) in TABLES.items():
        tables[key] = cur
        cur += 2 * n
    strings: dict[bytes, int] = {}
    missing = set()
    for key, (base, n) in TABLES.items():
        for i in range(n):
            jp = _orig(rom, base, i)
            if jp not in kr:
                missing.add(jp)
                continue
            b = _encode(kr[jp], rep_index)
            if b not in strings:
                strings[b] = cur
                so = common.snes2off((dicts.BANK << 16) | cur)
                out[so : so + len(b)] = b
                cur += len(b)
            to = common.snes2off((dicts.BANK << 16) | tables[key]) + 2 * i
            out[to] = strings[b] & 0xFF
            out[to + 1] = strings[b] >> 8
    if missing:
        raise SystemExit(f"places.json 에 없는 지명 {len(missing)}: {sorted(missing)[:6]}")
    if cur > 0x10000:
        raise SystemExit(f"사전 뱅크가 넘친다: 지명 {cur:#x}")
    for key in TABLES:
        info[key] = (dicts.BANK << 16) | tables[key]
    info["문자열"] = len(strings)
    info["next"] = cur
    return info
