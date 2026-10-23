#!/usr/bin/env python3
"""**쪽당 슬롯 한도** — 한 쪽이 쓸 수 있는 칸(17×4=68) + 고정 칸 예산이 글리프 슬롯 수 안인가, 그리고 번역문 쪽이 그 칸 수를 넘지 않는가. 0건 유지.

    python3 tools/check_page_slots.py

## 왜 있나 (2026-10-20)

qa 「기다 . 주시옵소서」「이야기입니하고」「옴든의 부하」 — 한 쪽에서 글자 하나가 다른 글자 그림으로 바뀌었다. 슬롯 150개 중 지금 쪽(68) + 앞 쪽 사본 보호(68)가
고정 칸과 함께 한도를 넘자 옛 할당기가 **지금 쪽 칸의 슬롯을 뺏었다**(직전 대사에 따라 가끔). 고침은 2단계 배정(`hook.V_LM`) — 앞 쪽 보호를 먼저 포기한다.
이 게이트는 그 전제(지금 쪽 + 고정 칸 ≤ 슬롯)를 상수로 못 박는다. 쪽 칸 수는 한 줄 17칸 × 4줄이 창 상한이다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: E402,F401,I001  (common 보다 먼저 — shared/text 와 이름이 겹친다)
import common  # noqa: E402
import hook  # noqa: E402

LINE_CELLS = 17


def _find_slots(d):
    """manifest 어딘가 중첩된 `slots`(글리프 슬롯 수)를 찾는다."""
    if isinstance(d, dict):
        if isinstance(d.get("slots"), int):
            return d["slots"]
        for v in d.values():
            r = _find_slots(v)
            if r:
                return r
    return None


def main() -> int:
    bad = []
    found = [_find_slots(json.loads(m.read_text(encoding="utf-8"))) for m in sorted(common.BUILD_DIR.glob("*/manifest.json"))]
    found = [int(x) for x in found if x]
    if not found:
        print("  쪽당 슬롯 한도 — 안 쟀다(빌드 manifest 없음 — 빌드 뒤에 다시)")
        return 1  # 늘 통과로 보이면 아무도 안 본다 — 못 쟀으면 실패
    slots = min(found)  # 빌드 칸마다 슬롯 수가 다를 수 있다 — 가장 작은 쪽으로 잰다
    bad += hook.slot_budget_problems(int(slots))
    # 번역문 쪽(<E0>·<FF> 사이)의 줄 수 — 4줄을 넘는 쪽은 줄 올림(스크롤)이라 칸 수 상한은 그대로이나 알린다
    segs = json.loads((common.GAME_DIR / "textmap" / "segments.json").read_text(encoding="utf-8"))
    over = 0
    for v in segs.values():
        for pg in re.split(r"<(?:E0|FF)>", v.get("kr", "")):
            if pg.count("\n") + 1 > 4:
                over += 1
    print(f"  쪽당 슬롯 한도 — 슬롯 {slots} ≥ 쪽 칸 {hook.PAGE_CELLS} + 고정 칸 예산 {hook.PIN_BUDGET}: {'위반' if bad else '통과'} · 명시 줄바꿈 5줄↑ 쪽 {over}(참고 — 줄 올림)")
    for b in bad:
        print("  ✗", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
