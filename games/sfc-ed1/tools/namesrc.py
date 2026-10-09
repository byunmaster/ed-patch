"""sfc-ed1 이름 읽기 — 고유명사는 사전(`shared/canon/nouns`)에서, 호칭·라벨은 정본(`shared/canon` ed1)에서 읽는다.

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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001  (common 보다 먼저)
import common

sys.path.insert(0, str(common.ROOT / "shared"))
import canon  # noqa: E402
from canon import _norm  # noqa: E402
from canon.names import dialog_place  # noqa: E402

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
        # 게임이 보는 입구는 `canon` 하나 — 고유명사(`canon.nouns`)·공통 문안(`canon.load`)·별칭(`canon.aliases`, 둘을 합친 것)
        _stores = {
            "g": canon.nouns(CANON)["categories"],
            "c": canon.load(CANON)["categories"],
            "alias": {_norm(a): t for a, t in canon.aliases(CANON).items()},
        }
    return _stores


def _fold(k):
    """폭·공백 접기 — 반각 가타카나(`ｷｬﾘｵﾝ ｸﾛｰﾗｰ`)와 전각(`キャリオンクローラー`)은 같은 원문이다(NFKC, 공백 무시)."""
    import unicodedata

    return unicodedata.normalize("NFKC", _norm(k)).replace(" ", "").replace("\u3000", "")


_folded: dict = {}


def _folded_tbl(store, cat):
    key = (store, cat)
    if key not in _folded:
        _folded[key] = {_fold(k): v for k, v in _load()[store].get(cat, {}).items()}
    return _folded[key]


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
                if v is None:  # 폭·공백 접기(같은 원문)
                    v = _folded_tbl(store, cat).get(_fold(key))
                if v is not None:
                    return v, f"{store}:{cat}"
    return None


def kanji_of(kana):
    """가나 표기 → 별칭이 이어 주는 한자 표기(없으면 그대로)."""
    return _load()["alias"].get(_norm(kana), kana)


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
        hit = resolve(jp, _PLACE_ORDER) or _place_slot(jp)
        if hit:
            d["names"][jp] = hit[0]
    return d


_SLOT_SUFFIX = re.compile(r"^(.+)(の(?:まち|しろ|むら|どうくつ|こうざん|はいこう|みなと|とう))$")


def _place_slot(jp):
    """칸 지명 = 정본 이름 + 접미 규칙 `のまち@지명칸` 등(마스터 10-08 — 따로 올리지 않고 조합한다)."""
    m = _SLOT_SUFFIX.match(jp)
    if not m:
        return None
    stem = resolve(m.group(1), _PLACE_ORDER)
    suf = resolve(f"{m.group(2)}@지명칸", _any_order([]))
    if stem and suf:
        return stem[0] + suf[0], "g+c:지명칸"
    return None


_UI_KEYS = ("title", "speed", "yesno", "flee", "retry", "loose", "a4_labels", "a3_values", "a4_values")


def _ui_hit(jp, site=None):
    """라벨 원문 → 정본 표기(없으면 None). 창마다 말이 갈리는 열쇠는 `원문@자리`."""
    return resolve(f"{jp}@{site}" if site else jp, _any_order([]))


def _row_hit(x):
    """한 줄의 정본 표기 — `canon` 필드(별칭이 아직 없는 자리의 정본 열쇠)가 있으면 그 열쇠로."""
    if x.get("canon"):
        return resolve(x["canon"], _any_order([]))
    return _ui_hit(x["jp"])


def _battle_rows(d):
    for g in d.get("grid", []):
        yield from g["cols"]
    for k in _UI_KEYS:
        yield from d.get(k, [])


def battle_ui() -> dict:
    """`battle_ui.json` — 이름 다섯은 사전에서, 나머지 라벨은 정본에서 읽는다. 정본에 없는 것만 JSON 에 남는다(사전 후보)."""
    d = json.loads((TEXTMAP / "battle_ui.json").read_text(encoding="utf-8"))
    for x in d["names"]:
        hit = resolve(x["jp"], _NAME_ORDER)
        if hit:
            x["kr"] = hit[0]
    for x in _battle_rows(d):
        hit = _row_hit(x)
        if hit:
            x["kr"] = hit[0]
    return d


def menus() -> dict:
    """`menus.json` — 정본에 있는 라벨 표기는 정본에서 읽는다(`canon_site` 가 있으면 `원문@자리` 열쇠)."""
    d = json.loads((TEXTMAP / "menus.json").read_text(encoding="utf-8"))
    for k, v in d.items():
        hit = _ui_hit(k.split("@")[0], v.get("canon_site"))
        if hit:
            v["kr"] = hit[0]
    return d


def _chapter_kr(jp):
    import re

    m = re.match(r"^(第(\d+)章|終章)\s*(.*)$", jp)
    if not m:
        return None
    hit = resolve(m.group(3), [("c", "chapter")])
    if not hit:
        return None
    return (f"제{m.group(2)}장 " if m.group(2) else "종장 ") + hit[0]


def chapters() -> dict:
    """`chapters.json` — 장 제목은 정본 `chapter` 범주(제목 부분)에서 읽고 「제N장」·「종장」 머리만 붙인다."""
    d = json.loads((TEXTMAP / "chapters.json").read_text(encoding="utf-8"))
    for t in d["titles"]:
        kr = _chapter_kr(t["jp"])
        if kr:
            t["kr"] = kr
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
    out["places"] = (sum(1 for jp in pl if resolve(jp, _PLACE_ORDER) or _place_slot(jp)), len(pl))
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
        if kr is not None and (resolve(jp, _PLACE_ORDER) or _place_slot(jp)):
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
    n["battle ui"] = 0
    for x in _battle_rows(b):
        if x.get("kr") is not None and _row_hit(x):
            x["kr"] = None
            n["battle ui"] += 1
    (TEXTMAP / "battle_ui.json").write_text(
        json.dumps(b, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    m = json.loads((TEXTMAP / "menus.json").read_text(encoding="utf-8"))
    n["menus"] = 0
    for k, v in m.items():
        if v.get("kr") is not None and _ui_hit(k.split("@")[0], v.get("canon_site")):
            v["kr"] = None
            n["menus"] += 1
    (TEXTMAP / "menus.json").write_text(
        json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    c = json.loads((TEXTMAP / "chapters.json").read_text(encoding="utf-8"))
    n["chapters"] = 0
    for t in c["titles"]:
        if t.get("kr") is not None and _chapter_kr(t["jp"]):
            t["kr"] = None
            n["chapters"] += 1
    (TEXTMAP / "chapters.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return n


if __name__ == "__main__":
    if "--strip" in sys.argv:
        print("걷음:", strip())
    for k, (a, n) in coverage().items():
        print(f"{k:14} 사전·정본에서 읽음 {a:3} / {n:3}  (JSON 에 남음 {n - a})")
