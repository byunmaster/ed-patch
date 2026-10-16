#!/usr/bin/env python3
"""정본(script/scnNNN.json)에 든 씬 번역 전체를 다시 검증한다 — `scene_apply.validate` 와 같은 검사(일본어 잔존 · 글리프 · 조판).

  python3 tools/scene_check.py [씬…]      # 씬을 안 주면 전부
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import scene_apply as A


def main() -> int:
    a = [int(x) for x in sys.argv[1:]]
    bad = 0
    for p in sorted(A.SCRIPT.glob("scn*.json")):
        n = int(p.stem[3:])
        if a and n not in a:
            continue
        msgs = {k: v["t"] for k, v in json.loads(p.read_text("utf-8"))["messages"].items() if "t" in v and not v.get("raw")}
        for e in A.validate(n, msgs):
            bad += 1
            print(f"scn{n:03d} ✗ {e}")
    print(f"위반 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
