#!/usr/bin/env python3
"""화면에 일본어가 남은 자리를 센다(PS1 `check_jp_left` 에 해당) — 분모를 같이 찍는다.

- **칸**(사전 · HUD/슬롯 지명 · 메뉴 라벨)은 미번역이 하나라도 있으면 실패 — 고정 폭 칸이라 지금 다 채울 수 있다.
- **문장**(대사·전투·시스템)은 미번역 수를 **알리기만** 한다 — 아직 번역 중인 대사가 「할 일」이지 「실패」가 아니다.
  늘 빨간불이면 아무도 안 본다(루트 CLAUDE.md). 대신 분모를 찍어 「0 이라 통과」 가짜 초록을 막는다.

  python3 tools/check_jp_left.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import names_corpus  # noqa: E402


def main() -> int:
    tot: dict[str, int] = {}
    left: dict[str, list[str]] = {}
    for where, jp, kr, _kind in names_corpus.pairs():
        area = where.split(":")[0]
        tot[area] = tot.get(area, 0) + 1
        if not kr:
            left.setdefault(area, []).append(f"{where} {jp[:14]!r}")
    bad = 0
    for area in sorted(tot):
        n = len(left.get(area, []))
        slot = area != "seg"
        print(f"  {area:6s} 번역 {tot[area] - n:,}/{tot[area]:,} · 일본어 잔존 {n}{' ⛔' if slot and n else ''}")
        if slot and n:
            bad += n
            for s in left[area][:10]:
                print("     ", s)
    print(f"화면 일본어(칸): {bad}건" + (" — 실패" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
