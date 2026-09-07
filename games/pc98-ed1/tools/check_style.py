#!/usr/bin/env python3
"""문안 표기 꼴 검사기 — **한 문안 안에서 갈리는 것**만 본다.

`rpg-translate` §4-② 「일본식 부호 → 한국식」과 같은 축인데, 판정 대신 **일관성**을 본다.
어느 꼴이 옳은지는 게임마다 갈려도, **한 게임 안에서 두 꼴이 섞이는 건 무조건 결함**이다.

실측(2026-09-06, PS1 사전에서 씨앗을 받은 뒤):

  · 같은 「2층」이 어떤 줄은 전각 `２층`, 어떤 줄은 반각 `2층` (4:1)
  · 곱은따옴표 `”…”` — 여는 꼴과 닫는 꼴이 같아 인용으로 못 쓴다
  · 일본식 마침표 `。`·쉼표 `、` 가 남아 있나

⚠ 마커(`\\n` `<PAGE>` `<WAIT>`)는 세지 않는다 — 그 계약은 `translate.py apply` 가 본다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import translate

MARK = re.compile(r"\\n|<PAGE>|<WAIT>")
AXES = {
    "전각 숫자": re.compile(r"[０-９]"),
    "곱은따옴표": re.compile(r"[“”„‟]"),
    "일본식 마침표·쉼표": re.compile(r"[。、]"),
    "일본식 물결·중점": re.compile(r"[～・]"),
}


def main() -> int:
    script = json.loads(translate.SCRIPT.read_text(encoding="utf-8"))
    bad = {}
    for k, v in script.items():
        t = MARK.sub(" ", v["t"])
        for name, rx in AXES.items():
            hit = rx.findall(t)
            if hit:
                bad.setdefault(name, []).append((k, "".join(sorted(set(hit))), t))
    half = sum(1 for v in script.values() if re.search(r"[0-9]", MARK.sub(" ", v["t"])))
    print(f"문안 {len(script):,}줄 · 반각 숫자를 쓴 줄 {half:,}")
    if not bad:
        print("  ✅ 섞인 꼴 없음")
        return 0
    for name, rows in bad.items():
        print(f"  🔴 {name} {len(rows)}줄 — {''.join(sorted({r[1] for r in rows}))}")
        for k, _h, t in rows[:4]:
            print(f"     [{k[:8]}] {t[:52]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
