"""사실 사전(lore, `ed1.json` ~ `ed4.json`) ↔ 고유명사 정본(glossary) 대조 보고서.

사전에는 JP 가 없으므로 **KR 표기로** 맞춘다. 정본은 고치지 않는다 — 보고만 한다.

  (a) 사전 이름 중 정본에 없는 것
  (b) 정본에 같은 것으로 보이는 다른 표기가 있는 것(자모 단위 근사)
  (c) 건수

비교는 공백을 지운 꼴로 한다 — 정본 place 는 HUD 층이라 붙여 쓰고(`크루즈마을`) 공략은 띄운다.
지명 접미(마을·성·항구 …)만 다른 것은 「접미 차이」로 따로 센다(같은 것으로 본다).

  python3 shared/lore/check_glossary.py ed1           # 사람용 보고(기본 ed1)
  python3 shared/lore/check_glossary.py ed3 --json    # 기계용

ED1·2 는 정본이 대표 표기라 이 대조가 「어긋남 0」이어야 한다. ED3·4 는 공략 표기가 잠정 대표라
참고용이다(정본이 아직 ED1·2 몫뿐이라 대부분 「없음」으로 나온다).
"""

import argparse
import difflib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LORE = ROOT / "shared/lore/ed1.json"  # main() 이 인자로 바꾼다
GLOSSARY = ROOT / "shared/canon/nouns/eiyuu.json"

# 사전 범주 → 정본 범주(주문 이름은 정본 item 에 들어 있다)
CAT = {
    "persons": "person",
    "places": "place",
    "items": "item",
    "monsters": "monster",
    "spells": "item",
    "magic": "item",  # ED3·4 는 주문 범주 이름이 magic 이다
}
SUFFIXES = ("왕국", "공화국", "마을", "항구", "요새", "성", "항")
NEAR = 0.8  # 자모 근사 문턱
WEAK = 0.6  # (a) 에 곁들일 최근접 후보 문턱

# 한글 음절 → 자모(초·중·종)
_L = [chr(c) for c in range(0x1100, 0x1113)]
_V = [chr(c) for c in range(0x1161, 0x1176)]
_T = [""] + [chr(c) for c in range(0x11A8, 0x11C3)]


def jamo(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch) - 0xAC00
        if 0 <= o < 11172:
            out += [_L[o // 588], _V[(o % 588) // 28], _T[o % 28]]
        else:
            out.append(ch)
    return "".join(out)


def norm(s: str) -> str:
    return "".join(s.split())


def base(s: str) -> str:
    s = norm(s)
    for suf in SUFFIXES:
        if s.endswith(suf) and len(s) > len(suf) + 1:
            return s[: -len(suf)]
    return s


def load_glossary():
    g = json.loads(GLOSSARY.read_text(encoding="utf-8"))["categories"]
    vals = {}  # norm(value) -> [(cat, jp, value)]
    for cat, table in g.items():
        for jp, kr in table.items():
            vals.setdefault(norm(kr), []).append((cat, jp, kr))
    return vals


def lore_names(lore):
    """(범주, id, 이름, 출처종류) — 출처종류 = primary | alt"""
    for cat in CAT:
        for r in lore.get(cat) or []:
            yield cat, r["id"], r["name"], "primary"
            for a in r.get("aliases", []):
                yield cat, r["id"], a, "alias"
            for a in r.get("alt", []):
                if a.get("field") == "name":
                    yield cat, r["id"], a["value"], "alt"


def classify(name, cat, gl, gl_base, gl_jamo):
    n = norm(name)
    if n in gl:
        hits = gl[n]
        same = [h for h in hits if h[0] == CAT[cat]]
        return ("exact", same or hits)
    b = base(name)
    if b in gl_base:
        return ("suffix", gl_base[b])
    # 접미를 뗀 꼴로도 잰다 — `라느라왕국` 과 `라누라` 는 통째로는 멀다
    js = {jamo(n), jamo(b)}
    best = []
    for gn, gj in gl_jamo.items():
        gjs = {gj, jamo(base(gn))}
        r = max(difflib.SequenceMatcher(None, a, c).ratio() for a in js for c in gjs)
        best.append((r, gn))
    best.sort(reverse=True)
    near = [(round(r, 2), gl[gn]) for r, gn in best[:3] if r >= NEAR]
    if near:
        return ("near", near)
    # 문턱 밑이라도 가장 가까운 하나는 보여 준다(판정은 사람 몫) — 「없다」가 결론이 아니라 물음이다
    weak = [(round(r, 2), gl[gn]) for r, gn in best[:1] if r >= WEAK]
    return ("absent", weak)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game", nargs="?", default="ed1", help="ed1 ~ ed4")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    global LORE
    LORE = ROOT / f"shared/lore/{args.game}.json"

    lore = json.loads(LORE.read_text(encoding="utf-8"))
    gl = load_glossary()
    gl_base = {}
    for n, hits in gl.items():
        gl_base.setdefault(base(n), []).extend(hits)
    gl_jamo = {n: jamo(n) for n in gl}

    rows = []
    for cat, rid, name, kind in lore_names(lore):
        status, hits = classify(name, cat, gl, gl_base, gl_jamo)
        rows.append(
            {"cat": cat, "id": rid, "name": name, "kind": kind, "status": status, "hits": hits}
        )

    # 레코드 단위: 대표 표기가 정본에 없는데 이형(alt)이 정본과 맞는 것 = 정본이 비정발 표기를 쓰고 있을 가능성
    by_id = {}
    for r in rows:
        by_id.setdefault((r["cat"], r["id"]), []).append(r)
    alt_wins = []
    for rs in by_id.values():
        prim = next(r for r in rs if r["kind"] == "primary")
        if prim["status"] in ("exact", "suffix"):
            continue
        for r in rs:
            if r["kind"] != "primary" and r["status"] in ("exact", "suffix"):
                alt_wins.append((prim, r))

    prim = [r for r in rows if r["kind"] == "primary"]
    counts = {
        "lore_primary": len(prim),
        "lore_all_names": len(rows),
        **{
            f"primary_{s}": sum(r["status"] == s for r in prim)
            for s in ("exact", "suffix", "near", "absent")
        },
        "alt_matches_glossary_while_primary_not": len(alt_wins),
    }
    per_cat = {}
    for r in prim:
        per_cat.setdefault(r["cat"], {}).setdefault(r["status"], 0)
        per_cat[r["cat"]][r["status"]] += 1

    if args.json:
        print(
            json.dumps(
                {
                    "counts": counts,
                    "per_category": per_cat,
                    "rows": rows,
                    "alt_wins": [(p["name"], a["name"]) for p, a in alt_wins],
                },
                ensure_ascii=False,
                indent=1,
            )
        )
        return

    def fmt_hits(hits):
        return ", ".join(f"{h[2]}[{h[0]}:{h[1]}]" for h in hits[:3])

    print("== (c) 건수")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    for c, d in per_cat.items():
        print(f"  {c}: {d}")

    print("\n== (b) 정본에 다른 표기로 있는 것 — 대표 표기 기준, 자모 근사")
    for r in prim:
        if r["status"] == "near":
            near = "; ".join(f"{h[1][0][2]}({h[0]})" for h in r["hits"])
            print(f"  [{r['cat']}] {r['name']}  ≈  {near}")

    print("\n== (b') 대표 표기는 정본에 없고 이형이 정본과 맞는 것")
    for p, a in alt_wins:
        print(
            f"  [{p['cat']}] {p['name']}  →  정본은 이형 「{a['name']}」({a['kind']}) = {fmt_hits(a['hits'])}"
        )

    print("\n== (a) 정본에 없는 것 — 대표 표기")
    for r in prim:
        if r["status"] == "absent":
            hint = ""
            if r["hits"]:
                score, hits = r["hits"][0]
                hint = f"   (최근접 {hits[0][2]}[{hits[0][0]}:{hits[0][1]}] {score})"
            print(f"  [{r['cat']}] {r['name']} ({r['id']}){hint}")

    print("\n== 참고: 접미만 다른 것(같은 것으로 본다)")
    for r in prim:
        if r["status"] == "suffix":
            print(f"  [{r['cat']}] {r['name']}  ~  {fmt_hits(r['hits'])}")


if __name__ == "__main__":
    main()
