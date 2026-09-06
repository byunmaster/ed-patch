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
import battle
import common
import font
import sysbuild
import translate

CANON = common.GAME_DIR / "script" / "glyph_order.json"


def used() -> set[str]:
    return (
        translate.all_glyph_chars()
        | sysbuild.all_glyph_chars()
        | battle.glyph_chars()
        | set(font.JOSA_CHARS)
    )


def main(check: bool) -> int:
    canon = json.loads(CANON.read_text())["order"] if CANON.exists() else []
    add = sorted(used() - set(canon))
    if not add:
        print(f"글리프 정본 {len(canon)}자 — 덧붙일 것 없음")
        return 0
    if check:
        print(f"🔴 정본에 없는 글자 {len(add)}자: {''.join(add)}")
        return 1
    order = canon + add
    if len(order) > font.MAX_GLYPHS:
        raise SystemExit(f"음절 {len(order)}자 — 상한 {font.MAX_GLYPHS}")
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
    print(f"글리프 정본 {len(canon)} → {len(order)}자 (덧붙임 {len(add)}: {''.join(add)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--check" in sys.argv))
