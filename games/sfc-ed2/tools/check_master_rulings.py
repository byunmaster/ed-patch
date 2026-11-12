"""마스터 판정 문안 게이트 — `master_rulings.json` 의 금지·필수 꼴이 문안 지도(`textmap/`)에 지켜지나.

    python3 games/sfc-ed2/tools/check_master_rulings.py

🔴 이유(10-30): 검수·재조판·에이전트는 원문만 보고 판정 기록을 안 읽어 마스터 판정을 되돌린다(ss-ed3 「로그 씨」가 세 번 되살아났다). 이 게임에서도 오프닝 란도 「정리해 버리고 있잖아!」가
10-23 style 권고로 「결론 내 버리면 어떡해!」가 됐다. 판정 문안은 문서에만 있으면 아무도 안 읽는다 — 여기서 실패로 걸어야 되돌릴 수 없다.
블록 = `<textmap 파일 이름>/<키>`(`segments/$D70325` 등). 문안의 제어 태그는 그대로 두고 비교한다.
"""

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

TEXTMAP = common.GAME_DIR / "textmap" if hasattr(common, "GAME_DIR") else Path(__file__).resolve().parents[1] / "textmap"
RULINGS = TEXTMAP.parent / "master_rulings.json"


def _strs(o, p=""):
    if isinstance(o, str):
        yield p, o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from _strs(v, f"{p}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _strs(v, f"{p}/{i}")


def corpus() -> list[tuple[str, str]]:
    """`[(블록, 문안)]` — textmap 의 `kr` 필드(해시 `h` 는 뺀다). 블록 = `파일/키`."""
    out = []
    for f in sorted(glob.glob(str(TEXTMAP / "*.json"))):
        name = Path(f).stem
        for p, s in _strs(json.load(open(f, encoding="utf-8"))):
            if p.endswith("/h"):
                continue
            out.append((name + (p[: -len("/kr")] if p.endswith("/kr") else p), s))
    return out


def main() -> int:
    doc = json.load(open(RULINGS, encoding="utf-8"))
    cp = corpus()
    by = dict(cp)
    bad, nf, nr = [], 0, 0
    for r in doc["rulings"]:
        ex = set(r.get("except_blocks", []))
        for pat in r.get("forbid", []):
            nf += 1
            bad += [(r["id"], f"{b} 에 「{pat}」 — {r['판정'][:50]}") for b, v in cp if pat in v and b not in ex]
        for pat in r.get("forbid_re", []):
            nf += 1
            bad += [(r["id"], f"{b} 에 /{pat}/ — {r['판정'][:50]}") for b, v in cp if re.search(pat, v) and b not in ex]
        for q in r.get("require", []):
            nr += 1
            v = by.get(q["block"])
            if v is None or q["has"] not in v:
                bad.append((r["id"], f"{q['block']} 에 「{q['has']}」 가 없다 — {r['판정'][:50]}"))
    print(f"  마스터 판정 문안 — 판정 {len(doc['rulings'])} · 금지 {nf} · 필수 {nr} · 위반 {len(bad)}")
    for i, m in bad[:20]:
        print(f"    ✗ [{i}] {m}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
