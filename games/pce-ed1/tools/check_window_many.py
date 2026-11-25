#!/usr/bin/env python3
"""창 수 「많음」 래칫 게이트 — 원문 한 창을 우리가 둘 이상으로 가른 메시지(마스터 11-06 「창많음은 실패 축 + 승인 예외 기준선 래칫」).

`fit_one_scan.scan()` 이 풀지 못한 메시지(= 한 창에 안 들어가거나 번역이 쪽을 다시 나눈 것 · 게이트 음성 타이머가 쪽 수를 쥔 것)가
기준선(`script/window_many_baseline.json` — 「씬:열쇠」 → 사유)에 없으면 실패한다. 기준선에 있는데 풀렸으면 알려 준다(`--freeze` 로 내린다).
고치는 길은 문안을 줄이는 것이 아니라 줄바꿈·쪽 위치를 원문 창 경계대로 다시 짜는 것이다(2-17, 마스터 10-31 「문안을 줄이는것보다 개행이 나뉘는게 의미보존」).
마지막 쪽에 한 어절만 남는 것은 따로 막는다(`linebreak_metrics`).

    python3 games/pce-ed1/tools/check_window_many.py [--freeze]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import fit_one_scan as F

BASE = common.GAME_DIR / "script" / "window_many_baseline.json"


def current() -> dict[str, str]:
    _fit, nofit = F.scan()
    return {f"{r['scene']}:{r['key']}": r["why"] for r in nofit}


def main() -> int:
    cur = current()
    if "--freeze" in sys.argv:
        BASE.write_text(json.dumps(dict(sorted(cur.items())), ensure_ascii=False, indent=1) + "\n")
        print(f"창 많음 기준선 갱신 — {len(cur)}건")
        return 0
    base = json.loads(BASE.read_text()) if BASE.exists() else {}
    new = sorted(k for k in cur if k not in base)
    solved = sorted(k for k in base if k not in cur)
    print(f"창 「많음」 — 풀지 못한 {len(cur)}건 (기준선 {len(base)}){' · 풀린 ' + str(len(solved)) + '건은 --freeze 로 내린다' if solved else ''}")
    if new:
        print("❌ 기준선에 없는 새 창 많음:")
        for k in new:
            print(f"    scn{k} — {cur[k]}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
