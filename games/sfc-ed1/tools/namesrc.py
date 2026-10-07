"""sfc-ed1 이름 읽기 — 고유명사는 사전(`shared/glossary`)에서, 호칭·라벨은 정본(`shared/canon` ed1)에서 읽는다.

마스터 2026-10-08 「사전 먼저」: 게임 폴더에 JP→KR 표를 따로 두지 않는다. `textmap/dict.json`(D0~D4)·`places.json`·
`battle_ui.json` 의 `names` 는 **원문 열쇠(와 사전에 없는 것의 임시 표기)만** 들고, 사전·정본에 있는 이름의 표기는
빌드가 **여기서** 읽는다 — 그래서 사전이 바뀌면 이 게임도 바뀌고(`rebase main` 으로 받는다), 갈릴 수가 없다.

- **원문이 같을 때만.** 열쇠는 원문 글자 그대로 → 사전·정본 `_aliases`(가나 ↔ 한자 표기, 같은 말) 순으로 찾는다.
  가나로 쓴 `とうぞく` 가 사전 `盗賊` 에 닿는 건 **별칭이 이어 줄 때뿐**이다 — 읽기를 기계로 맞추지 않는다.
- **칸 꼴과 대사 꼴.** 사전 place 값은 지명 **칸** 꼴(붙임)이다. 대사에 들어가는 사전 D1 은 `dialog_place` 로 대사 꼴
  (「구엔의 탑」·「크루즈 마을」)로 바꾼다. 칸(`places.json`)은 그대로 쓴다(원문 꼴 그대로, 마스터 10-07).
- **사전에 없는 것**(사전 후보 · 이 기종 원문만의 이름)은 JSON 에 임시 표기가 남는다 — 그게 독자 데이터라
  `coverage()` 가 몇 개인지 센다(걷을 때까지 줄이는 숫자).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001  (common 보다 먼저)
import common

sys.path.insert(0, str(common.ROOT / "shared"))
import canon  # noqa: E402
import glossary  # noqa: E402
from glossary import _norm  # noqa: E402
from glossary.names import dialog_place  # noqa: E402

TEXTMAP = common.GAME_DIR / "textmap"
TITLE = "eiyuu"
CANON = "ed1"

# 사전 6벌이 먼저 보는 범주 — (저장소, 범주). 앞에서 찾으면 거기서 멈춘다.
_DICT_ORDER = {
    0xD0: [("g", "person"), ("c", "speaker"), ("g", "place"), ("g", "item"), ("c", "ui")],
    0xD1: [("g", "place")],
    0xD2: [("g", "item"), ("c", "ui"), ("c", "battle")],
    0xD3: [("g", "monster"), ("c", "speaker"), ("c", "battle")],
    0xD4: [("g", "item")],
}
_PLACE_ORDER = [("g", "place")]
_NAME_ORDER = [("g", "person")]

_stores = None


def _load():
    global _stores
    if _stores is None:
        g, c = glossary.load(TITLE), canon.load(CANON)
        alias = {**g.get("_aliases", {}), **c.get("_aliases", {})}
        _stores = {
            "g": g["categories"],
            "c": c["categories"],
            "alias": {_norm(a): t for a, t in alias.items()},
        }
    return _stores


def _variants(jp):
    """열쇠 꼴 몇 가지 — 전각 공백·반각 공백 차이는 같은 원문이다."""
    out = [jp, jp.replace("　", " "), jp.replace("　", "").replace(" ", "")]
    return list(dict.fromkeys(out))


def resolve(jp, order):
    """원문 → (표기, 어느 저장소·범주) 또는 None. 원문 글자 → 별칭 순."""
    s = _load()
    for form in _variants(jp):
        for key in (form, s["alias"].get(_norm(form))):
            if not key:
                continue
            for store, cat in order:
                tbl = s[store].get(cat, {})
                v = tbl.get(key)
                if v is None and key != _norm(key):
                    v = tbl.get(_norm(key))
                if v is not None:
                    return v, f"{store}:{cat}"
    return None


def _any_order(first):
    rest = [("g", c) for c in ("person", "place", "item", "monster")] + [("c", "speaker"), ("c", "ui")]
    return list(first) + [r for r in rest if r not in first]


def dict_map(rom=None) -> dict:
    """`dict.json` — 사전·정본에 있는 이름은 표기를 읽어 채운다(없는 것만 JSON 임시 표기). 모양은 그대로."""
    d = json.loads((TEXTMAP / "dict.json").read_text(encoding="utf-8"))
    rom = rom or common.rom_bytes()
    for code, order in _DICT_ORDER.items():
        for i, b in enumerate(text.dict_entries(code, rom)):
            key = f"{code:02X}:{i:02X}"
            jp = text.decode(b).strip()
            hit = resolve(jp, _any_order(order))
            e = d.setdefault(key, {})
            if hit:
                kr = dialog_place(hit[0]) if code == 0xD1 else hit[0]
                e["kr"], e["src"] = kr, hit[1]
            else:
                e["src"] = "local"
    return d


def places_map() -> dict:
    """`places.json` — {원문: 칸 표기}. 사전 place 값은 칸 꼴 그대로(원문 꼴 그대로, 마스터 10-07)."""
    d = json.loads((TEXTMAP / "places.json").read_text(encoding="utf-8"))
    for jp in list(d["names"]):
        hit = resolve(jp, _PLACE_ORDER)
        if hit:
            d["names"][jp] = hit[0]
    return d


def battle_ui() -> dict:
    """`battle_ui.json` — `names`(파티 이름 다섯)만 사전에서 읽는다. 나머지는 이 기종 문장·라벨이라 그대로."""
    d = json.loads((TEXTMAP / "battle_ui.json").read_text(encoding="utf-8"))
    for x in d["names"]:
        hit = resolve(x["jp"], _NAME_ORDER)
        if hit:
            x["kr"] = hit[0]
    return d


def coverage(rom=None) -> dict:
    """어느 표가 몇 개를 사전·정본에서 읽고 몇 개를 JSON 에 남겼나(걷을 때까지 줄이는 숫자)."""
    rom = rom or common.rom_bytes()
    out = {}
    d = dict_map(rom)
    for code in _DICT_ORDER:
        rows = [v for k, v in d.items() if k.startswith(f"{code:02X}:")]
        out[f"D{code - 0xD0}"] = (sum(1 for v in rows if v.get("src") != "local"), len(rows))
    pl = json.loads((TEXTMAP / "places.json").read_text(encoding="utf-8"))["names"]
    out["places"] = (sum(1 for jp in pl if resolve(jp, _PLACE_ORDER)), len(pl))
    bn = json.loads((TEXTMAP / "battle_ui.json").read_text(encoding="utf-8"))["names"]
    out["battle names"] = (sum(1 for x in bn if resolve(x["jp"], _NAME_ORDER)), len(bn))
    return out




def strip() -> dict:
    """사전·정본에 있는 이름의 JSON 표기를 걷는다 — 읽을 수 있게 된 만큼만(독자 사본을 남기지 않는다).
    멱등이다. 사전 쪽이 바뀌면 이미 걷은 건 따라 바뀌고, 안 걷은 건 `local` 로 남아 `coverage()` 가 센다."""
    n = {"dict": 0, "places": 0, "battle names": 0}
    rom = common.rom_bytes()
    d = json.loads((TEXTMAP / "dict.json").read_text(encoding="utf-8"))
    ov = dict_map(rom)
    for k, v in d.items():
        if ov.get(k, {}).get("src") not in (None, "local") and v.get("kr") is not None:
            v["kr"] = None
            v["state"] = "ref"
            n["dict"] += 1
    (TEXTMAP / "dict.json").write_text(
        json.dumps(dict(sorted(d.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    p = json.loads((TEXTMAP / "places.json").read_text(encoding="utf-8"))
    for jp, kr in p["names"].items():
        if kr is not None and resolve(jp, _PLACE_ORDER):
            p["names"][jp] = None
            n["places"] += 1
    (TEXTMAP / "places.json").write_text(
        json.dumps(p, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    b = json.loads((TEXTMAP / "battle_ui.json").read_text(encoding="utf-8"))
    for x in b["names"]:
        if x.get("kr") is not None and resolve(x["jp"], _NAME_ORDER):
            x["kr"] = None
            n["battle names"] += 1
    (TEXTMAP / "battle_ui.json").write_text(
        json.dumps(b, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return n


if __name__ == "__main__":
    if "--strip" in sys.argv:
        print("걷음:", strip())
    for k, (a, n) in coverage().items():
        print(f"{k:14} 사전·정본에서 읽음 {a:3} / {n:3}  (JSON 에 남음 {n - a})")
