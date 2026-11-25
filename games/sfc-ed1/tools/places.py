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
import namesrc

TABLES = {"a": (0x02A793, 160), "b": (0x02A8B1, 149), "c": (0x02A8B1, 149)}  # c = 로드 슬롯 목록 전용(앞 빈칸·반 칸 합성 없이 왼쪽 맞춤)  # (원본 포인터 표, 항목 수)
CELLS = 10


def names() -> dict[str, str]:
    return namesrc.places_map()["names"]


def texts() -> list[str]:
    return list(names().values())


def glyph_texts() -> list[str]:
    return [cells(kr) for kr in names().values()] + texts()  # 슬롯 목록(c)은 합성 없이 낱글자라 원문도 올린다 — 글리프표 원천 — 합성 칸(사설 영역)까지 올려야 한다


def _orig(rom: bytes, base: int, i: int) -> str:
    o = common.snes2off(base) + 2 * i
    p = rom[o] | rom[o + 1] << 8
    so = common.snes2off(0x020000 | p)
    return text.decode(rom[so : rom.index(b"\xff", so)], text.resolver(rom)).strip("　")


# 홀수로 남는 칸을 어느 쪽에 둘지의 스위치 — False: 오른쪽(왼 ≤ 오, 글자 덩이 중심 −6px, 마스터 11-08),
# True: 앞(+2px, 가까운 쪽 — 마스터 답이 「가까운 쪽」이면 이것 한 줄. 게이트 place_center_axes 도 이 값을 따른다).
ODD_TO_FRONT = False
# 홀수 칸 차이일 때 글자 덩이를 **반 칸(4px) 시작**으로 합성해 정확히 가운데에 앉힌다(sfc-ed2 와 같은 취지, 마스터 11-08).
# 4px 공백을 앞에 두고 8px 칸으로 다시 끊은 걸친 칸은 사설 영역 글리프(`battle_ui.halfspace`)로 올린다. True 면 위 스위치는 무시.
HALF_PHASE = True


def half_phase(kr: str) -> bool:
    return HALF_PHASE and (CELLS - len(kr)) % 2 == 1


def cells(kr: str) -> str:
    """칸에 실제로 굽는 문자열(앞 빈칸 포함) — 반 칸 시작이면 합성 글리프가 섞인다."""
    pad = pad_cells(kr)[0]
    if not half_phase(kr):
        return " " * pad + kr
    import battle_ui

    return battle_ui.halfspace(" " * (2 * pad + 1) + kr)


def pad_cells(kr: str) -> tuple[int, int]:
    """10칸 안의 (앞 빈칸, 뒤 빈칸) — 가운데 정렬(번역 규칙 2-8, 마스터 11-08 「HUD·입장 배너 가운데정렬」).
    칸은 8px 고정이라 짝수 차이는 정확히 가운데, 홀수 차이는 **남는 한 칸을 오른쪽(뒤)에 둔다** — 왼쪽 여백 ≤ 오른쪽 여백
    (마스터 11-08 「딱 가운데가 아니라면 왼쪽 여백을 더 짧게, 왼쪽으로 조금 더 치우치게」; 앞 칸 올림은 폐기)."""
    pad = (CELLS - len(kr) + (1 if ODD_TO_FRONT and not HALF_PHASE else 0)) // 2
    return pad, CELLS - len(kr) - pad


def _encode(kr: str, rep_index: dict[str, int], plain: bool = False) -> bytes:
    if len(kr) > CELLS:
        raise SystemExit(f"지명 {kr!r} 이 {CELLS}칸을 넘는다")
    b = bytearray()
    for ch in kr if plain else cells(kr):
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
            b = _encode(kr[jp], rep_index, plain=key == "c")
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
