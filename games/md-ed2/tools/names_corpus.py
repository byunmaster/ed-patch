"""공용 이름·정본 검사 어댑터(`scripts/check/check_names.py`·`check_canon.py`) — **이름을 안 든다**, 원문·문안을 읽어 넘길 뿐이다.

`pairs()` = `[(자리, 원문 줄, 우리 줄 또는 None, 갈래)]`. 미번역은 None 으로 내어 분모에 든다. 대본 씬 모듈 356 · 코드 영역 문안(`sysmsg`) ·
이름·라벨 표를 낸다 + 전투 문안(`battle:`).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import dict_names
import halfspace
import scene
import stream_join
import sysmsg

CANON = "ed2"  # 공통 문안 정본(shared/canon)
CANON_GATE = True  # 정본 어긋남을 실패로 친다(2026-10-18 어긋남 0 — 이후 커밋은 이 게이트 아래에서)
CANON_SKIP = (
    r"^script\+?:"  # 장면 대사는 정본 범위 밖(마스터 10-08) — 정본은 메뉴·호칭·시스템·전투 문구
)
DIALOG, SLOT = "dialog", "slot"


_TAG = re.compile(r"<([0-9a-f]{2,6})(?::[0-9a-f]+)?(?:\|[^>]*)?>")
_JOSA_PAIR = (
    "은(는)",
    "이(가)",
    "을(를)",
    "과(와)",
    "으로(로)",
)  # 조사 훅 하위 니블 p 0~4 (josa.py)
_NAME_CODES = {
    "02",
    "0b",
    "0900",
    "0901",
    "0902",
    "0903",
    "0904",
    "0905",
}  # 배우·리더·파티원 이름 자리
_ITEM_CODES = {"0e"}  # 아이템·주문 이름 자리


def _t(s):
    """정본 검사용 줄 정규화 — **제어태그를 정본의 꼴로 푼다**(2026-10-08).

    정본은 줄 전체(`^…$`)로 재고 자리표(`{name}`·`{item}`)와 병기 조사(`은(는)`)로 적혀 있다. 어댑터가 제어태그를 그대로 내면
    (끝 `<0a|끝>`·이름 자리 `<02>`·조사 훅 `<eb00>`) 문구가 통째로 안 잡혔다 — 정본 값이 바뀌었는데 어긋남 0 이었다.
    · 이름 자리 → `{name}` · 아이템 자리 → `{item}` · 조사 훅 `<eb|ec p>` → 병기 조사(`p` 하위 니블)
    · 줄바꿈 `<01>` → 줄바꿈 · 나머지 제어태그(끝·쪽·참조·피치 …)는 뗀다."""
    if not isinstance(s, str):
        return s

    def sub(m):
        c = m.group(1)
        if c in _NAME_CODES:
            return "{name}"
        if c in _ITEM_CODES:
            return "{item}"
        if c[:2] in ("eb", "ec") and len(c) == 4:
            return _JOSA_PAIR[min(int(c[3], 16), 4)]
        if c == "01":
            return "\n"
        return ""

    return _TAG.sub(sub, s)


def _script_pairs(rom: bytes):
    for blk, k, b in archives.modules(rom):
        mod = scene.parse_module(b)
        p = common.GAME_DIR / "script" / f"{blk:03d}-{k}.json"
        kr_map = json.loads(p.read_text(encoding="utf-8")).get("streams", {}) if p.exists() else {}
        for off, st in sorted(mod.streams.items()):
            ours = kr_map.get(f"{off:04x}", {}).get("ours") or None
            yield f"script:{blk:03d}-{k}:{off:04x}", st.text(), ours, DIALOG


_KANA = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
_HEAD = re.compile(r"<(?:[0-9a-f]{2}){3,}4e71>")


def _joined_script_pairs(rom: bytes):
    """이어진 문장 — call/goto 로 조각을 부르는 스트림은 **흐름대로 편 줄**을 더 낸다(`script+:BBB-K:오프셋#갈래`). 원문·우리 쪽을 같은 걸음으로 펴 갈래 번호를 맞춘다.

    조각 단위로만 내면 한 문장이 여럿으로 쪼개져 이름·정본·인사 검사가 이어진 자리를 못 본다. 조건 꼬리는 갈래 둘(`stream_join`)이라 이어 붙이지 않는다.
    우리 쪽 조각에 번역이 없으면(원문에 가나·한자가 있을 때) None — 분모에 든다. 갈래 수가 어긋나면 `script+!` 로 알린다(구조가 갈렸다)."""
    for blk, k, b in archives.modules(rom):
        yield from _joined_module(blk, k, scene.parse_module(b))


def _joined_module(blk: int, k: int, mod):
    p = common.GAME_DIR / "script" / f"{blk:03d}-{k}.json"
    kr_map = json.loads(p.read_text(encoding="utf-8")).get("streams", {}) if p.exists() else {}
    jp_cache, kr_cache = {}, {}

    def jp_items(off):
        if off not in jp_cache:
            st = mod.streams.get(off)
            jp_cache[off] = stream_join.jp_items(st) if st is not None else None
        return jp_cache[off]

    def kr_items(off):
        if off not in kr_cache:
            ours = kr_map.get(f"{off:04x}", {}).get("ours")
            st = mod.streams.get(off)
            if ours:
                kr_cache[off] = stream_join.kr_items(ours)
            elif st is not None and not _KANA.search(st.text()):
                # 글자가 없는 조각(제어만) — 번역이 따로 없고 흐름은 원문 그대로
                kr_cache[off] = jp_items(off)
            else:
                kr_cache[off] = None
        return kr_cache[off]

    for off in sorted(mod.streams):
        if not stream_join.has_ref(jp_items(off)):
            continue
        if _HEAD.match(kr_map.get(f"{off:04x}", {}).get("ours") or ""):
            continue  # 상점 표 머리(포인터 워드 + 4E71) — 글이 아니라 표다
        jp = stream_join.paths(jp_items, off)
        kr = stream_join.paths(kr_items, off)
        key = f"script+:{blk:03d}-{k}:{off:04x}"
        if len(jp) != len(kr):
            yield key + "!", " | ".join(x or "" for x in jp), None, DIALOG
            continue
        for n, (j, q) in enumerate(zip(jp, kr, strict=True)):
            yield f"{key}#{n}", j or "", q, DIALOG


# 칸에 박힌 이름 표 스트림(용의 알 이름 · 지명) — 칸은 붙여쓴 꼴(규칙 3-4), 대사가 아니다
SLOT_STREAMS = frozenset(
    {0x22C60, 0x22C6E, 0x22C7C, 0x22C8A, 0x22C98, 0x3B0B6, 0x3B22E, 0x3B23B, 0x3B248}
)

# 화면에 안 나가는 죽은 자료 — 롬 전체에서 가리키는 곳이 0(절대 32비트·pc 상대 lea/pea·16비트 상대 워드 탐색, 테스트가 고정한다).
# 0x29DC8 = 0x2468C 「…을 가지고 있었다」의 참조 없는 사본(칸 17B 제자리 고정). 참조가 생기면 테스트가 깨지니 그때 분모에 되돌린다.
DEAD_STREAMS = frozenset({0x29DC8})


def _sysmsg_pairs(rom: bytes):
    import build

    smap = build.load_sysmsg(rom)
    for addr, e in sysmsg.streams(rom).items():
        if addr in DEAD_STREAMS:
            continue
        jp = sysmsg.render(e["stream"])
        ours = smap.get(f"{addr:06x}", {}).get("ours") or None
        yield f"sysmsg:{addr:06x}", _t(jp), _t(ours), SLOT if addr in SLOT_STREAMS else DIALOG


def _battle_pairs(rom: bytes):
    """전투 문안 — 블록마다 `battle.refs` 스트림의 원문 줄과 정본(`textmap/battle.json`)의 우리 줄. 이름 자리 `{몬스터|조사}` 는 `expand_names` 로 펴서 낸다.

    미번역(번역 칸이 빈 것)은 None — 분모에 든다. call/goto 조각은 조각째 낸다(펴기는 따로)."""
    import battle

    bmap = (
        json.loads(battle.MAP_JSON.read_text(encoding="utf-8")) if battle.MAP_JSON.exists() else {}
    )
    monsters = battle.monsters(rom)
    for n, (_s, b, _e) in enumerate(battle.blocks(rom)):
        for tgt, e in battle.refs(b).items():
            st = e["stream"]
            ent = bmap.get(battle.pos_key(st, n, tgt)) or bmap.get(battle.jp_key(st)) or {}
            ours = ent.get("ours") or None
            if ours:
                ours = battle.expand_names(ours, monsters)
            yield f"battle:{n:03d}:{tgt:04x}", _t(sysmsg.render(st)), _t(ours), DIALOG


def _names_pairs(rom: bytes):
    d = dict_names.names(rom)
    for cat, tbl in d.items():
        if not isinstance(tbl, dict):
            continue
        for idx, ent in tbl.items():
            if not isinstance(ent, dict):
                continue
            jp = ent.get("jp")
            if not jp:
                continue
            yield f"names:{cat}[{idx}]", jp, (halfspace.plain(ent.get("ours") or "") or None), SLOT


def pairs():
    rom = common.rom()
    yield from _script_pairs(rom)
    yield from _joined_script_pairs(rom)
    yield from _sysmsg_pairs(rom)
    yield from _battle_pairs(rom)
    yield from _names_pairs(rom)


if __name__ == "__main__":
    n = 0
    for _where, _jp, _ours, _kind in pairs():
        n += 1
    print(f"  names_corpus: 줄 {n}")
