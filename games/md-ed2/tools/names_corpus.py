"""공용 이름·정본 검사 어댑터(`scripts/check/check_names.py`·`check_canon.py`) — **이름을 안 든다**, 원문·문안을 읽어 넘길 뿐이다.

`pairs()` = `[(자리, 원문 줄, 우리 줄 또는 None, 갈래)]`. 미번역은 None 으로 내어 분모에 든다. 대본 씬 모듈 356 · 코드 영역 문안(`sysmsg`) ·
이름·라벨 표를 낸다. 전투 문안은 이식 전이다.
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
import sysmsg

CANON = "ed2"  # 공통 문안 정본(shared/canon)
CANON_GATE = (
    False  # 정본 어긋남을 실패로 치는 전환은 시스템 메시지·전투 문안이 정본과 맞은 뒤에 켠다
)
CANON_SKIP = (
    r"^script:"  # 장면 대사는 정본 범위 밖(마스터 10-08) — 정본은 메뉴·호칭·시스템·전투 문구
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


def _sysmsg_pairs(rom: bytes):
    import build

    smap = build.load_sysmsg(rom)
    for addr, e in sysmsg.streams(rom).items():
        jp = sysmsg.render(e["stream"])
        ours = smap.get(f"{addr:06x}", {}).get("ours") or None
        yield f"sysmsg:{addr:06x}", _t(jp), _t(ours), DIALOG


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
    yield from _sysmsg_pairs(rom)
    yield from _names_pairs(rom)


if __name__ == "__main__":
    n = 0
    for _where, _jp, _ours, _kind in pairs():
        n += 1
    print(f"  names_corpus: 줄 {n}")
