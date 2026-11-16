"""마스터 판정 문안 게이트 — `master_rulings.json` 의 금지·필수 꼴이 script 에 지켜지나.

    python3 games/pce-ed1/tools/check_master_rulings.py

🔴 이유(10-30): ss-ed3 에서 마스터가 08-28 에 뺀 「로그 씨」가 세 번 되살아났다 — 원문만 보는 문안 검수가 판정 기록을 안 봐서다. 같은 검수가 열한 게임 전부를 거쳤다.
판정 문안은 문서에만 있으면 아무도 안 읽는다. 여기서 실패로 걸어야 되돌릴 수 없다(ss-ed3 `check_master_rulings.py` 꼴).
"""

import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SCRIPT = Path(common.GAME_DIR) / "script"
RULINGS = Path(common.GAME_DIR) / "master_rulings.json"


def corpus() -> list[tuple[str, str]]:
    """`[(출처, 문안)]` — 씬 대사 블록(`scnNNN#열쇠`)."""
    out = []
    for f in sorted(glob.glob(str(SCRIPT / "scn*.json"))):
        stem = Path(f).stem
        for k, v in json.load(open(f, encoding="utf-8")).get("messages", {}).items():
            if isinstance(v, dict) and isinstance(v.get("t"), str):
                out.append((f"{stem}#{k}", v["t"]))
    return out


def main() -> int:
    doc = json.load(open(RULINGS, encoding="utf-8"))
    cp = corpus()
    by = dict(cp)
    bad, nf, nr = [], 0, 0
    for r in doc["rulings"]:
        for pat in r.get("forbid", []):
            nf += 1
            for src, v in cp:
                if pat in v:
                    bad.append((r["id"], f"{src} 에 「{pat}」 — {r['판정'][:50]}"))
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
