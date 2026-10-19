#!/usr/bin/env python3
"""전투 묶음 표 감사 — 「ok 인데 분모를 못 채운」 그룹을 가른다.

    python3 tools/battle_table_check.py <sweep/battle-…> [--turns 15]

🔴 왜(2026-10-20): 그룹 63(카자즘, 보스 시작 대사가 입력 대기)이 **턴 0** 인데 표 상태가 `ok` 라 manifest 「98 정상」에 묻혔다. 하네스가 이제 `short` 를 직접 달지만(`ss_battle_sweep`),
옛 표(status 만 ok)도 같은 기준으로 다시 가른다: ED2 는 `turns < --turns` 또는 몬스터 이름 빔, ED1 은 captures 0 또는 몬스터 이름 빔.
출력: 그룹 수 · ok · short(그룹 목록) · 조우 안 걸림(그룹 목록) — manifest 분모에 그대로 옮긴다.
"""

import glob
import json
import os
import sys


def main():
    folder = sys.argv[1]
    turns = int(sys.argv[sys.argv.index("--turns") + 1]) if "--turns" in sys.argv else 15
    rows = []
    for f in sorted(glob.glob(os.path.join(folder, "table_*.json"))):
        rows += json.load(open(f, encoding="utf-8"))
    ok, short, miss = [], [], []
    for r in rows:
        if r["status"] == "조우 안 걸림":
            miss.append(r["group"])
        elif r["status"] == "short":
            short.append((r["group"], r.get("short_why", "")))
        elif "turns" in r:  # ED2 — 옛 표
            (short if r["turns"] < turns or not r.get("monsters") else ok).append((r["group"], f"턴 {r['turns']}/{turns}") if r["turns"] < turns or not r.get("monsters") else r["group"])
        else:  # ED1
            (short if r.get("captures", 0) == 0 or not r.get("monsters") else ok).append((r["group"], "캡처 0·이름 빔") if r.get("captures", 0) == 0 or not r.get("monsters") else r["group"])
    print(f"{folder}: 그룹 {len(rows)} — ok {len(ok)} · short {len(short)} {short} · 조우 안 걸림 {len(miss)} {miss}")


if __name__ == "__main__":
    main()
