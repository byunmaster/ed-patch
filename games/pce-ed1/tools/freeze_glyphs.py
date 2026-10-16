"""글리프 배정 정본에 **새 글자를 뒤에 덧붙인다** — 앞 코드는 안 흔든다.

🔴 왜 정본이 필요한가: 게임이 파티원 이름을 **우리 글리프 코드 그대로 BRAM(세이브)에 적는다**
(실측 2026-09-06). 배정 순서가 바뀌면 이전 세이브의 이름이 다른 글자로 읽힌다
(「세리오스」 → 「서린온을」). 그래서 순서는 커밋되는 정본이고, 새 글자는 **덧붙이기만** 한다.

    python3 games/pce-ed1/tools/freeze_glyphs.py          # 새 글자를 덧붙인다
    python3 games/pce-ed1/tools/freeze_glyphs.py --check  # 덧붙일 게 있나만 본다(0/1)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import font
import glyphdyn
import translate

CANON = common.GAME_DIR / "script" / "glyph_order.json"


def main(check: bool) -> int:
    """🔴 상주 정본에는 **늘 상주해야 하는 글자**(`glyphdyn.forced_chars`)가 다 들어 있어야 한다 — 빠지면 실패다.
    대사 본문에서만 쓰는 드문 글자는 블록별 동적 칸(`font.DYN_SLOTS`)이 실으므로 정본에 없어도 된다. 상주 칸이 남으면
    본문 글자를 **쓰는 씬 수 많은 순**으로 채운다(동적 몫을 줄인다)."""
    canon = json.loads(CANON.read_text())["order"] if CANON.exists() else []
    have = set(canon)
    add = sorted(glyphdyn.forced_chars() - have)
    if check:
        if add:
            print(f"🔴 상주 정본에 없는 글자 {len(add)}자(이름·UI·시스템·전투·조사·숫자 — 동적으로 못 간다): {''.join(add)}")
            return 1
        dyn = sorted(translate.all_glyph_chars() - have)
        print(
            f"글리프 정본 {len(canon)}자(상주 상한 {font.RESIDENT_MAX}) — 늘 상주할 글자 다 있음 · 블록별 동적 후보 {len(dyn)}자"
        )
        return 0
    order = canon + add
    if len(order) > font.RESIDENT_MAX:
        raise SystemExit(f"상주 글자 {len(order)}자 — 상한 {font.RESIDENT_MAX}")
    fill = [ch for ch in glyphdyn.fill_candidates(set(order))][: font.RESIDENT_MAX - len(order)]
    order += fill
    if order == canon:
        print(f"글리프 정본 {len(canon)}자 — 덧붙일 것 없음")
        return 0
    CANON.write_text(
        json.dumps(
            {
                "_doc": (
                    "글리프 배정 순서 정본. 🔴 코드가 세이브(BRAM)에 남으므로 **순서를 바꾸지 "
                    "않는다** — 새 글자는 뒤에 덧붙인다(freeze_glyphs.py). 앞을 흔들면 "
                    "이전 세이브의 이름이 다른 글자로 읽힌다."
                ),
                "order": order,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n"
    )
    print(f"글리프 정본 {len(canon)} → {len(order)}자 (덧붙임 {len(order) - len(canon)}: {''.join(add + fill)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--check" in sys.argv))
