"""이름 표를 정본(`shared/canon` — 고유명사 `nouns/` + 공통 문안)에서 읽는다 — 게임 폴더에 이름 표(JP→KR)를 안 둔다.

    python3 tools/dict_names.py        # 표별 출처 집계(사전 / 정본 / 예외 / 못 채움)

사전 적용 2단계(마스터 2026-10-08). 표의 **JP 는 원본 롬에서 읽고**(`tables.records`), 우리 표기는
사전(고유명사) → 정본(UI 라벨) 순으로 찾는다. **이름 표는 게임 폴더에 없다**(마스터 2026-10-08 「자기사전 금지」) — 라벨 칸의 배치(공백 수·태그)만 `textmap/ui_layout.json`
에 있고(한글 없음, 정본 열쇠로 가리킨다), 정본·사전에 아직 없는 값은 `PENDING`(관리자 후보 대기)에서 읽는다.

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

from shared import canon

# 표 → 사전 범주(앞이 우선). 둘 이상 범주에 같은 JP 가 있으면(카스/커스) 앞 범주만 쓴다.
DICT_TABLES = {
    "item": ("item",),
    "spell": ("spell", "item"),
    "place_a": ("place",),
    "place_b": ("place",),
}
# 표 → 정본 범주 (UI 라벨 — 사전에 없을 때, 그리고 상점·예/아니오는 처음부터 정본)
CANON_TABLES = {"item": "ui", "spell": "ui", "shop": "ui", "yesno": "ui"}
CANON_FIRST = {"shop", "yesno"}

_DASH = canon._DASH
LAYOUT_JSON = common.GAME_DIR / "textmap" / "ui_layout.json"


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).replace(" ", "").translate(_DASH)


_idx: dict | None = None


def _index() -> dict:
    global _idx
    if _idx is None:
        _idx = {}
        for cat, t in canon.nouns("ed1")["categories"].items():
            for k, v in t.items():
                _idx.setdefault(_norm(k), {})[cat] = v
    return _idx


def _alias(jp: str) -> str:
    """같은 원문의 다른 표기 → 정본 열쇠(정본 `_aliases`, 장음 정규화)."""
    a = {_norm(k): v for k, v in canon.aliases("ed1").items()}
    return a.get(_norm(jp), jp)


def from_dict(jp: str, cats: tuple[str, ...]) -> str | None:
    hit = _index().get(_norm(jp)) or _index().get(_norm(_alias(jp)))
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


# ── 임시: 정본·사전에 아직 없는 값 — 관리자에게 후보로 올렸다(마스터 2026-10-08 「자기사전 금지」) ──────────────
# 열쇠 = `<범주>:<원문>`(범주는 정본 `ui`·`chapter` / 사전 `person` / 표 예외 `table`). 관리자가 main 정본에 올리면
# 읽는 쪽이 정본 값을 먼저 쓰므로 **그때 이 줄을 지운다**(`check_own_tables.py` 가 남아 있으면 알린다).
PENDING: dict[str, str] = {}  # 정본·사전에 올릴 후보 대기 — 지금은 비었다(마스터 2026-10-08). 새로 생기면 열쇠 `<범주>:<원문>` 으로 적고 관리자에게 올린다


def _layout() -> dict:
    p = LAYOUT_JSON
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _label(ns: str, key: str) -> str:
    """`=<범주>:<원문>` 토큰의 우리 표기 — 정본(ui·chapter) / 사전(person) 에서 읽는다."""
    v = canon.lookup(key, ns, "ed1")
    if v is None:
        v = canon.lookup(_alias(key), ns, "ed1")
    if v is None:
        v = PENDING.get(f"{ns}:{key}")
    if v is None:
        raise SystemExit(f"라벨 {ns}:{key} 가 정본·사전에 없다 — 관리자에게 후보로 올린다")
    return v


def compose(tpl: list) -> str:
    """칸 템플릿(`textmap/ui_layout.json`) → 우리 표기. 정수 = 공백 수, `=범주:원문` = 정본·사전 값, 나머지 = 그대로."""
    out = []
    for t in tpl:
        if isinstance(t, int):
            out.append(" " * t)
        elif t.startswith("="):
            ns, key = t[1:].split(":", 1)
            out.append(_label(ns, key))
        else:
            out.append(t)
    return "".join(out)


def names(orig: bytes | None = None) -> dict:
    """표 전체 `{범주: {색인: {jp, ours, src}}}` — JP 는 롬, 우리 표기는 사전·정본(칸 배치는 `ui_layout.json`)."""
    orig = orig if orig is not None else common.rom()
    recs = tables.records(orig)
    widths = {t[0]: t[2] for t in tables.TABLES}
    out: dict[str, dict] = {}
    for cat in (*DICT_TABLES, *CANON_TABLES):
        if cat not in recs:
            continue
        tbl = out.setdefault(cat, {})
        for i, (_pos, raw) in enumerate(recs[cat]):
            jp = tables.decode(raw).strip()
            v, src = PENDING.get(f"table:{cat}:{jp}"), "pending"  # 표 예외(사전과 다르게 쓰기로 한 칸)가 먼저
            if v is not None:
                pass
            elif cat in CANON_FIRST:
                v, src = from_canon(jp, CANON_TABLES[cat]), "canon"
            else:
                if cat in DICT_TABLES:
                    v, src = from_dict(jp, DICT_TABLES[cat]), "glossary"
                if v is None and cat in CANON_TABLES:
                    v, src = from_canon(jp, CANON_TABLES[cat]), "canon"
            if v is None:
                tbl[str(i)] = {"jp": jp, "ours": "", "src": ""}
                continue
            if cat in widths:
                v = fit(v, widths[cat], f"{cat}[{i}]")
            tbl[str(i)] = {"jp": jp, "ours": v, "src": src}
    for cat, tpls in _layout().items():
        tbl = out.setdefault(cat, {})
        for i, tpl in tpls.items():
            if cat in recs:
                jp = tables.decode(recs[cat][int(i)][1]).strip()
            else:  # 그래픽 셀 낱말(타이틀) — 원문이 롬 표에 없다: 템플릿의 열쇠가 원문이다
                jp = next(t.split(":", 1)[1] for t in tpl if isinstance(t, str) and t.startswith("="))
            tbl[i] = {"jp": jp, "ours": compose(tpl), "src": "canon"}
    return out


if __name__ == "__main__":
    n = names()
    for cat, t in n.items():
        by: dict[str, int] = {}
        for e in t.values():
            k = e["src"] or ("없음" if not e["ours"] else "예외")
            by[k] = by.get(k, 0) + 1
        print(f"  {cat:12s} {len(t):4d}  {by}")
    print(f"  임시 후보 대기(PENDING) {len(PENDING)}건 — 관리자가 정본에 올리면 지운다")
