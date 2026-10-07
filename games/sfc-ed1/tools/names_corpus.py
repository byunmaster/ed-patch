"""sfc-ed1 이름 검사 어댑터 — `pairs()` 가 `(자리, 원문 줄, 우리 줄|None)` 을 문안 전체에 대해 낸다.

🔴 이름 표를 **들지 않는다**(마스터 2026-10-07 — 워커는 독자 데이터를 못 갖는다). 원문·문안을
읽어 넘길 뿐이고, 잣대는 공용 `shared/glossary/names.py` 하나다.

- **대사·전투·시스템** — `units.segments()`(END 로 끝나는 조각, `textmap/segments.json` 의 키와
  같다)를 그대로 돈다. 사전 치환(`{D3:08}` 등)은 `text.decode()` 가 이미 그 자리의 **원문을
  풀어 중괄호로 박아 두므로**(히라가나 표기까지 그대로) 따로 더 풀 필요가 없다 — 이게 바로
  `ほのおのつるぎ` 를 찾아낸 자리다(07C441, status.md 참조).
- **칸** — 갈래 `slot`: 사전 항목 · `places.json`(HUD·슬롯 지명) · `menus.json`(메뉴 라벨). 문장은 `dialog`.
- **사전 D0~D5 항목 자체** — `textmap/dict.json` 의 각 칸도 원문·문안 쌍이다(사전 항목도
  화면에 그대로 나간다).

미번역(`kr` 이 없는) 자리는 `None` 으로 낸다 — 분모(`units`)에는 들지만 이름 비교는 안 한다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001  (common 보다 먼저)
import common
import textmap
import namesrc
import units

CANON = "ed1"  # 공통 문안 정본 — PS1 기반(마스터 10-08)
CANON_GATE = True  # 전환을 마쳤다 — check_canon.py 가 어긋남을 실패로 친다(마스터 10-08)

# 우리 문안은 사전 치환 자리를 **토큰으로 품는다**(`{D0:80}` 등, 화면에선 런타임에 사전 칸의
# 한국어로 풀린다 — `units.py:token_of`). 원문 쪽은 `text.decode()` 가 이미 그 자리를 풀어
# 문자 그대로 박아 두므로, 우리 쪽도 같은 자리에서 **사전 문안의 번역**으로 풀어야 둘이
# 같은 말을 비교한다 — 안 풀면 「세리오스」 같은 이름이 전부 「우리 줄에 없다」로 오탐 난다.
_DICT_TOKEN = re.compile(r"\{([0-9A-F]{2}):([0-9A-F]{2})\}")


def _resolve_tokens(kr, dict_cur):
    """`text.decode()` 와 같은 규칙 — `$D0 8x` 는 강조색 표시고 실제 항목은 `x&$7F`
    (`text.py:decode`). 안 맞추면 `{D0:80}` 이 D0 표 0x80 번(표 밖)을 찾다 늘 빈다."""

    def repl(m):
        code, idx = m.group(1), int(m.group(2), 16)
        if code == "D0":
            idx &= 0x7F
        v = dict_cur.get(f"{code}:{idx:02X}", {})
        return v.get("kr") or m.group(0)

    return _DICT_TOKEN.sub(repl, kr)


def _bare(jp):
    """`text.decode()` 가 사전 치환 자리에 박은 `{…}` 를 벗긴 원문 글자 그대로 — 중괄호가
    가타카나 낱말(`キャリオンク{ロー}ラー`)을 끊으면 낱말 경계 검사가 무력해진다."""
    return jp.replace("{", "").replace("}", "")


def _segment_pairs(rom, dict_cur):
    items, _ = units.extract(rom)
    res = text.resolver(rom)
    tm = textmap.load()
    for s in units.segments(items, res):
        v = tm.get(s["id"])
        kr = v.get("kr") if v else None
        yield (
            f"seg:{s['id']}@{s['addr']}",
            _bare(s["jp"]),
            _resolve_tokens(kr, dict_cur) if kr else None,
            "dialog",
        )


def _dict_pairs(rom, dict_cur):
    for code in text.DICT_TABLES:
        for i, b in enumerate(text.dict_entries(code, rom)):
            key = f"{code:02X}:{i:02X}"
            jp = text.decode(b).strip()
            kr = dict_cur.get(key, {}).get("kr")
            yield f"dict:{key}", jp, kr or None, "slot"


def _slot_pairs():
    """HUD·슬롯 지명(`places.json`)과 메뉴 라벨(`menus.json`) — 고정 폭 칸이다."""
    tdir = common.GAME_DIR / "textmap"
    for jp, kr in namesrc.places_map()["names"].items():
        yield f"place:{jp}", jp, kr or None, "slot"
    for key, v in json.loads((tdir / "menus.json").read_text(encoding="utf-8")).items():
        yield f"menu:{key}", key.split("@")[0], v.get("kr") or None, "slot"


def pairs():
    rom = common.rom_bytes()
    dict_cur = namesrc.dict_map(rom)
    yield from _segment_pairs(rom, dict_cur)
    yield from _dict_pairs(rom, dict_cur)
    yield from _slot_pairs()


if __name__ == "__main__":
    n = sum(1 for _ in pairs())
    print(f"자리 {n:,}")
