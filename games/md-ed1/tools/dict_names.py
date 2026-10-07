"""이름 표를 사전(`shared/glossary`)·정본(`shared/canon`)에서 읽는다 — 게임 폴더에 이름 표(JP→KR)를 안 둔다.

    python3 tools/dict_names.py        # 표별 출처 집계(사전 / 정본 / 예외 / 못 채움)

사전 적용 2단계(마스터 2026-10-08). 표의 **JP 는 원본 롬에서 읽고**(`tables.records`), 우리 표기는
사전(고유명사) → 정본(UI 라벨) 순으로 찾는다. `textmap/names.json` 에는 **사전·정본에 없는 칸**(사전 후보)
과 **사전과 다르게 쓰기로 한 예외**만 남는다 — 거기 있는 칸은 그 값이 이긴다(`src` 에 이유).

- 칸 폭: 사전 값이 칸(아이템 14B)을 넘으면 ① 「의 」를 합성 글자 「의␣」(`halfspace.PUA`, 2B)로 바꾸고
  ② 그래도 넘으면 띄어쓰기를 뗀다(예전 「glossary→7칸(띄어쓰기 제거)」 규칙 그대로).
- 몬스터 이름은 `battle.monsters()` — 같은 사전을 읽는다.
"""

import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import halfspace
import tables

from shared import canon, glossary

# 표 → 사전 범주(앞이 우선). 둘 이상 범주에 같은 JP 가 있으면(카스/커스) 앞 범주만 쓴다.
DICT_TABLES = {
    "item": ("item",),
    "spell": ("item",),
    "place_a": ("place",),
    "place_b": ("place",),
}
# 표 → 정본 범주 (UI 라벨 — 사전에 없을 때, 그리고 상점·예/아니오는 처음부터 정본)
CANON_TABLES = {"item": "ui", "spell": "ui", "shop": "ui", "yesno": "ui"}
CANON_FIRST = {"shop", "yesno"}

_DASH = glossary._DASH


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).replace(" ", "").translate(_DASH)


_idx: dict | None = None


def _index() -> dict:
    global _idx
    if _idx is None:
        _idx = {}
        for cat, t in glossary.load()["categories"].items():
            for k, v in t.items():
                _idx.setdefault(_norm(k), {})[cat] = v
    return _idx


def from_dict(jp: str, cats: tuple[str, ...]) -> str | None:
    hit = _index().get(_norm(jp))
    if not hit:
        return None
    for c in cats:
        if c in hit:
            return hit[c]
    return None


def from_canon(jp: str, cat: str) -> str | None:
    return canon.lookup(jp, cat, "ed1") or canon.lookup(_norm(jp), cat, "ed1")


def _bytes(s: str) -> int:
    """한글·합성 글자 2B, 반각 1B — 칸 폭 셈."""
    return sum(1 if ord(c) < 0x80 else 2 for c in s)


def fit(value: str, width: int, name: str) -> str:
    """사전 값을 폭 `width`B 칸에 맞춘다. 못 맞추면 빌드 실패로 둔다(호출쪽이 알린다)."""
    if _bytes(value) <= width:
        return value
    v = value.replace("의 ", halfspace.PUA, 1) if "의 " in value else value
    if _bytes(v) <= width:
        return v
    v = v.replace(" ", "")
    if _bytes(v) > width:
        raise SystemExit(
            f"{name}: 사전 값 {value!r} 가 칸 {width}B 를 넘는다 — 사전 후보/예외로 올린다"
        )
    return v


def _residual() -> dict:
    p = tables.NAMES_JSON
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def names(orig: bytes | None = None) -> dict:
    """`textmap/names.json` 꼴의 표 전체 — JP 는 롬, 우리 표기는 사전·정본, 예외는 names.json."""
    orig = orig if orig is not None else common.rom()
    res = _residual()
    recs = tables.records(orig)
    widths = {t[0]: t[2] for t in tables.TABLES}
    out = {cat: dict(t) for cat, t in res.items()}
    for cat in (*DICT_TABLES, *CANON_TABLES):
        if cat not in recs:
            continue
        tbl = out.setdefault(cat, {})
        for i, (_pos, raw) in enumerate(recs[cat]):
            ent = tbl.get(str(i), {})
            if ent.get("ours"):
                continue  # 예외·사전 후보 — names.json 값이 이긴다
            jp = tables.decode(raw).strip()
            v, src = None, ""
            if cat in CANON_FIRST:
                v, src = from_canon(jp, CANON_TABLES[cat]), "canon"
            else:
                if cat in DICT_TABLES:
                    v, src = from_dict(jp, DICT_TABLES[cat]), "glossary"
                if v is None and cat in CANON_TABLES:
                    v, src = from_canon(jp, CANON_TABLES[cat]), "canon"
            if v is None:
                tbl[str(i)] = {"jp": jp, "ours": ent.get("ours", ""), "src": ent.get("src", "")}
                continue
            if cat in widths:
                v = fit(v, widths[cat], f"{cat}[{i}]")
            tbl[str(i)] = {"jp": jp, "ours": v, "src": src}
    return out


if __name__ == "__main__":
    n = names()
    res = _residual()
    for cat in (*DICT_TABLES, *CANON_TABLES):
        t = n.get(cat, {})
        by = {}
        for e in t.values():
            by[e["src"] or ("없음" if not e["ours"] else "예외")] = (
                by.get(e["src"] or ("없음" if not e["ours"] else "예외"), 0) + 1
            )
        print(f"  {cat:8s} {len(t):4d}  {by}  (names.json 예외 {len(res.get(cat, {}))})")
