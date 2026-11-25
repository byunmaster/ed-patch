#!/usr/bin/env python3
"""공백 든 고유명사(`script/tie_names.json`)가 줄 끝에서 갈리면 실패 — 마스터 11-25 「울프 빌」(5장 랄프 「…울프 / 빌에도」).

  python3 tools/check_tie_names.py

방법: 번역 정본 문안 전부를 조판기(`typeset.pages`, 화자 곁·아님 둘)에 태워 줄 쌍(윗줄 끝 · 아랫줄 머리)이 이름 한가운데(공백 자리)에서 갈린 곳을 센다.
이름이 한 줄보다 길어 어쩔 수 없는 경우는 없다(가장 긴 이름이 13칸 안).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import typeset

SCRIPT = Path(__file__).resolve().parent.parent / "script"


def main() -> int:
    names = json.loads((SCRIPT / "tie_names.json").read_text("utf-8"))["names"]
    splits = []
    for n in names:
        parts = n.split(" ")
        for i in range(1, len(parts)):
            splits.append((" ".join(parts[:i]), " ".join(parts[i:]), n))
    bad = []
    n_txt = 0
    for f in sorted(SCRIPT.glob("scn*.json")):
        for k, v in json.loads(f.read_text("utf-8")).get("messages", {}).items():
            t = v.get("t") if isinstance(v, dict) else None
            if not t or not any(n in t for n in names):
                continue
            n_txt += 1
            for sp in (False, True):
                for pg in typeset.pages(t, speaker=sp):
                    if not isinstance(pg, list):
                        continue
                    for a, b in zip(pg, pg[1:]):
                        for left, right, n in splits:
                            if a.rstrip().endswith(left) and b.lstrip().startswith(right):
                                bad.append((f.stem, k, n, a.strip(), b.strip()))
    print(f"공백 든 고유명사 {len(names)} · 이름이 든 문안 {n_txt} · 줄 끝에서 갈린 곳 {len(bad)}")
    for r in bad[:30]:
        print("  ❌", *r)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
