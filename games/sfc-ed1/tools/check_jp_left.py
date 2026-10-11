#!/usr/bin/env python3
"""화면에 일본어가 남은 자리를 센다(PS1 `check_jp_left` 에 해당) — 분모를 같이 찍는다.

- **칸**(사전 · HUD/슬롯 지명 · 메뉴 라벨)은 미번역이 하나라도 있으면 실패 — 고정 폭 칸이라 지금 다 채울 수 있다.
- **문장**(대사·전투·시스템)은 미번역 수를 **알리기만** 한다 — 아직 번역 중인 대사가 「할 일」이지 「실패」가 아니다.
  늘 빨간불이면 아무도 안 본다(루트 CLAUDE.md). 대신 분모를 찍어 「0 이라 통과」 가짜 초록을 막는다.

  python3 tools/check_jp_left.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import names_corpus  # noqa: E402


def data_fragments() -> set[str]:
    """화면에 안 나온다는 근거가 있는 데이터 파편 id(textmap/data_fragments.json) — 경고로만 센다."""
    p = common.GAME_DIR / "textmap" / "data_fragments.json"
    return set(json.loads(p.read_text(encoding="utf-8"))["ids"]) if p.exists() else set()


def main() -> int:
    tot: dict[str, int] = {}
    left: dict[str, list[str]] = {}
    warn: list[str] = []  # 근거 있는 데이터 파편(경고 — 통과)
    dead = data_fragments()
    for where, jp, kr, _kind in names_corpus.screen_pairs():
        area = where.split(":")[0]
        tot[area] = tot.get(area, 0) + 1
        if not kr:
            if area == "seg" and where.split(":")[1].split("@")[0] in dead:
                warn.append(where)
                continue
            left.setdefault(area, []).append(f"{where} {jp[:14]!r}")
    bad = 0
    for area in sorted(tot):
        n = len(left.get(area, []))
        w = len(warn) if area == "seg" else 0
        slot = area != "seg"
        # 🔴 근거 있는 데이터 파편(textmap/data_fragments.json)은 「경고」로 따로 센다 — 검사에는 걸리지만 통과(마스터 10-11).
        #    목록 밖 잔존은 종전처럼 일본어 잔존으로 센다(문장은 번역 중이라 알리기만 · 칸은 실패)
        print(
            f"  {area:6s} 번역 {tot[area] - n - w:,}/{tot[area]:,} · 일본어 잔존 {n}"
            + (f" · ⚠ 경고(화면에 안 나오는 데이터 파편) {w}" if w else "")
            + (" ⛔" if slot and n else "")
        )
        if slot and n:
            bad += n
            for s in left[area][:10]:
                print("     ", s)
    print(f"화면 일본어(칸): {bad}건" + (" — 실패" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
