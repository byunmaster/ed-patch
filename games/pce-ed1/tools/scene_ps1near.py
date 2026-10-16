#!/usr/bin/env python3
"""내 번역과 가장 비슷한 PS1 문안을 찾아 보여 준다 — 같은 뜻이면 PS1 어휘·호칭·어미를 따르려는 점검용.

  python3 tools/scene_ps1near.py 6 20 [--min 0.3]
한글 바이그램 자카드로 잰다(화자·페이지 표지 `{p}`·`\\f` 는 뺀다). 표시: `[열쇠] 유사도` / 내 문안 / PS1 후보(화자).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

PS1 = common.ROOT / "games" / "ps1-ed1+2" / "script"
SCRIPT = common.GAME_DIR / "script"
DERIVED = common.GAME_DIR / "work" / "derived" / "messages"


def grams(s: str) -> set[str]:
    s = re.sub(r"[^가-힣]", "", s)
    return {s[i : i + 2] for i in range(len(s) - 1)}


def corpus() -> list[tuple[str, str, set]]:
    """PS1 문안 후보 — 항목(한 항목에 창이 여럿 묶인다)을 `{p}` 로 나눈 창 하나 · 이어진 창 2~4개 묶음까지 후보로 둔다."""
    out = []
    for p in sorted(PS1.glob("ED1SCN*.json")):
        for v in json.loads(p.read_text("utf-8")).values():
            if not (isinstance(v, dict) and "t" in v):
                continue
            who = v.get("s") or ""
            wins = v["t"].split("{p}")
            for i in range(len(wins)):
                for j in range(i + 1, min(len(wins), i + 4) + 1):
                    t = "{p}".join(wins[i:j])
                    out.append((who, t, grams(t)))
    return out


_PLACE_RX = None


def space_places(t: str) -> str:
    """PS1 은 「루디아성」처럼 붙이지만 대사 속 지명은 종류 말을 띄운다(docs/naming.md) — 정본 지명(`shared/canon`)의 밑동 + 종류 말을 띄운다."""
    global _PLACE_RX
    if _PLACE_RX is None:
        sys.path.insert(0, str(common.ROOT / "shared"))
        import canon

        pairs = set()
        for c, _jp, kr in canon.all_names("ed1"):
            if c != "place":
                continue
            for suf in ("마을", "성", "항구", "요새", "광산", "섬", "탑"):
                if kr.endswith(suf) and len(kr) > len(suf):
                    pairs.add((kr[: -len(suf)], suf))
        alt = "|".join(sorted((re.escape(b) for b, _ in pairs), key=len, reverse=True))
        _PLACE_RX = re.compile(rf"({alt})(마을|성|항구|요새|광산|섬|탑)(?!문)")
    return _PLACE_RX.sub(r"\1 \2", t)


def norm(t: str) -> str | None:
    """PS1 문안 → 우리 정본 꼴: `{p}`→`\f` · 마침표 연속→전각 `…`(round(n/3), 최소 1) · 병기 조사→조사 토큰. 모르는 `{…}` 가 남으면 None."""
    t = t.replace("{p}", "\f").replace("\ue003", " ")  # \ue003 = PS1 붙임 공백(블록 이음) → 공백 하나
    t = t.replace("\x1a", "")  # PS1 이름 자리표 — PCE 는 게임이 이름을 앞에 붙인다
    t = re.sub(r"\.{2,}", lambda m: "…" * max(1, round(len(m.group()) / 3)), t)
    for a, b in (("을(를)", "을/를"), ("이(가)", "이/가"), ("은(는)", "은/는"), ("과(와)", "과/와"), ("으로(로)", "으로/로")):
        t = t.replace(a, b)
    t = re.sub(r"([.,!?])(?=[가-힣A-Za-z])", r"\1 ", t)  # 부호 뒤 공백(번역 규칙 2-1) — PS1 은 「이옵니다.말」처럼 붙인 곳이 있다
    return None if "{" in t else space_places(t)


def adopt(n: int, keys: list[str], cor) -> None:
    p = SCRIPT / f"scn{n:03d}.json"
    doc = json.loads(p.read_text("utf-8"))
    for k in keys:
        mine = doc["messages"][k]["t"]
        g = grams(mine)
        best = max(cor, key=lambda c: len(g & c[2]) / max(1, len(g | c[2])))
        t = norm(best[1])
        if t is None:
            print(f"  ✗ {k}: PS1 문안에 모르는 자리표")
            continue
        doc["messages"][k]["t"] = t
        print(f"  ← {k}: {t}")
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")


def main() -> int:
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    thr = float(sys.argv[sys.argv.index("--min") + 1]) if "--min" in sys.argv else 0.3
    a = [x for x in a if x != str(thr)]
    cor = corpus()
    if "--auto" in sys.argv:  # python3 tools/scene_ps1near.py 6 11 --auto 0.5 — 유사도 ≥ 기준이고 화자가 맞는 줄을 PS1 문안으로 바꾼다(바꾼 줄을 보여 준다)
        thr = float(sys.argv[sys.argv.index("--auto") + 1])
        import messages as M

        sp = M.load_speakers()
        for x in a:
            if x == str(thr):
                continue
            n = int(x)
            p = SCRIPT / f"scn{n:03d}.json"
            doc = json.loads(p.read_text("utf-8"))
            src = {m["key"]: m for m in json.loads((DERIVED / f"scn{n:03d}.json").read_text("utf-8"))}
            print(f"## scn{n:03d}")
            for k, v in doc["messages"].items():
                t = v.get("t")
                if not t or v.get("raw") or k not in src:
                    continue
                g = grams(t)
                if len(g) < 3:
                    continue
                best = max(cor, key=lambda c: len(g & c[2]) / max(1, len(g | c[2])))
                sim = len(g & best[2]) / max(1, len(g | best[2]))
                who = sp.get(src[k]["speaker"], "") if src[k]["speaker"] else ""
                if sim < thr or (who and best[0] and who != best[0]):
                    continue
                new = norm(best[1])
                if new is None or new == t or not (0.8 * len(t) <= len(new) <= 2.0 * len(t)):
                    continue
                v["t"] = new
                print(f"  [{k}] {sim:.2f}\n    {t.replace(chr(12), '¶')}\n    → {new.replace(chr(12), '¶')}")
            p.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
        return 0
    if "--adopt" in sys.argv:  # python3 tools/scene_ps1near.py 6 --adopt k1,k2 — 그 열쇠의 내 문안을 가장 비슷한 PS1 문안으로 바꾼다
        keys = sys.argv[sys.argv.index("--adopt") + 1].split(",")
        a = [x for x in a if x != sys.argv[sys.argv.index("--adopt") + 1]]
        adopt(int(a[0]), keys, cor)
        return 0
    for n in map(int, a):
        mine = json.loads((SCRIPT / f"scn{n:03d}.json").read_text("utf-8"))["messages"]
        src = {m["key"]: m for m in json.loads((DERIVED / f"scn{n:03d}.json").read_text("utf-8"))}
        print(f"## scn{n:03d}")
        for k, v in mine.items():
            t = v.get("t")
            if not t or v.get("raw"):
                continue
            g = grams(t)
            if len(g) < 3:
                continue
            best = max(cor, key=lambda c: len(g & c[2]) / max(1, len(g | c[2])))
            sim = len(g & best[2]) / max(1, len(g | best[2]))
            if sim >= thr:
                print(f"[{k}] {sim:.2f} {src.get(k, {}).get('speaker') or '-'}\n  내: {t.replace(chr(12), '¶')}\n  PS1({best[0]}): {best[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
