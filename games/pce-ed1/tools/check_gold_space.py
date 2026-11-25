#!/usr/bin/env python3
"""엔진이 숫자를 끼우는 조각(앞 조각 + 수치 옵코드 `22` + 「Gold…」) 앞뒤 띄어쓰기 — 11-25 마스터 「그럼 {n} Gold」(규칙 1-5).

  python3 tools/check_gold_space.py

수치 옵코드(`22`) 바로 뒤에 오는 조각이 「Gold」로 시작하면 **앞 공백**이 있어야 하고(「452855 Gold」), 그 앞 조각이 한글 낱말로 끝나면 **끝 공백**이 있어야 한다
(「그럼 452855」). 안 지키면 「452855Gold」·「그럼452855」가 붙는다. 1만 이상 「N만」 은 엔진 계산값이 아니라 문안에 든 숫자라 대상이 아니다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import containers
import messages

SCRIPT = Path(__file__).resolve().parent.parent / "script"


def main() -> int:
    seen: set[int] = set()
    bad = []
    n = 0
    for c in containers.scan():
        for b in c["blocks"]:
            sid = b["id"]
            if sid in seen:
                continue
            seen.add(sid)
            p = SCRIPT / f"scn{sid:03d}.json"
            if not p.exists():
                continue
            tr = json.loads(p.read_text("utf-8"))["messages"]
            d = b["data"]
            ms = sorted(messages.parse(d), key=lambda m: m.start)
            for i, m in enumerate(ms):
                if not i or not d[ms[i - 1].end : m.start].endswith(b"\x22"):
                    continue
                t = tr.get(m.key, {}).get("t", "")
                if not t.lstrip().startswith("Gold"):
                    continue
                n += 1
                if not t.startswith(" "):
                    bad.append((sid, m.key, "Gold 앞 공백 없음"))
                pt = tr.get(ms[i - 1].key, {}).get("t", "")
                if re.search(r"[가-힣]$", pt):
                    bad.append((sid, ms[i - 1].key, "숫자 앞 낱말 뒤 공백 없음"))
    print(f"수치 끼움 + Gold 조각 {n} · 띄어쓰기 어긋남 {len(bad)}")
    for sid, k, why in bad:
        print(f"  ❌ scn{sid:03d}:{k} {why}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
