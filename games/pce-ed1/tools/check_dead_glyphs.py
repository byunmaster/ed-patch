#!/usr/bin/env python3
"""쓰이지 않는 글리프 게이트(11-22 마스터 「!? 이건 합자야?」) — 정본 순서(`script/glyph_order.json`)에 있는데 **어느 문안·시스템 문구·전투 문구·이름·엔진 고정 표에서도 안 쓰이는** 글자가 있으면 실패한다.
죽은 글리프는 뱅크 한 칸(18B)과 상주 자리(816)를 먹는다 — 합자 ‼ ⁉ 는 11-06 에 `font.ligate` 가 원문 그대로 돌려주게 된 뒤로 대사에 안 나오는데 계속 구워지고 있었다.

「쓰임」 = ① 본문·이름(`translate.all_glyph_chars`) ② 시스템(`sysbuild`) ③ 전투(`battle`) ④ 엔진 고정 표가 글자를 번호로 직접 집는 곳 — 단계 숫자·숫자 표(`DIGIT_CHARS`)·조사 토큰(`JOSA_CHARS`)·
`HALF_NARROW`·`NARROW_PUNCT`·`build.py` 의 「제」「종」「들」·주문 끝 글자 허용 목록(`sysbuild.spell_gate_chars`). 예외(`ALLOW`)는 이유를 적는다.

    python3 tools/check_dead_glyphs.py
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "shared"))
import battle  # noqa: E402
import font  # noqa: E402
import hook  # noqa: E402
import sysbuild  # noqa: E402
import translate  # noqa: E402

# 쓰임이 문안에서 안 보이지만 정본 순서에 있는 글자 — 이유 필수. 새로 늘리지 않는다(없애는 쪽이 맞다).
ALLOW = {
    **{c: "ASCII 영문·부호 — 반각 영숫자 표(`hook.half_tables`) 대상이라 번호를 흔들면 뒤 글리프 코드가 밀린다. 쓰임 미확인(원판 `Eiyuu Densetsu` 표기 예약 추정) — 확인되면 이 항목을 지우고 정본에서 뺀다" for c in "-enstuy"},
}


def used() -> set[str]:
    ok = lambda s: {font.FULLWIDTH_BIOS.get(c, c) for c in s}  # noqa: E731
    u = ok(translate.all_glyph_chars()) | ok(sysbuild.all_glyph_chars()) | ok(battle.glyph_chars()) | ok(translate.name_chars())
    u |= set(font.JOSA_CHARS) | set(font.DIGIT_CHARS) | set(font.NARROW_PUNCT) | set(getattr(hook, "HALF_NARROW", ""))
    u |= set("제종들") | set(sysbuild.spell_gate_chars())
    return u


def main() -> int:
    order = font._order_canon()
    u = used()
    dead = [c for c in order if c not in u and c not in ALLOW]
    stale = [c for c in ALLOW if c in u]
    print(f"쓰이지 않는 글리프 검사 — 정본 순서 {len(order)}자 · 죽은 글리프 {len(dead)} · 예외 {len(ALLOW)}자(쓰임 미확인)" + (f" · 예외인데 쓰이는 {''.join(stale)}(예외에서 뺀다)" if stale else ""))
    if dead:
        print("  ✘ 쓰이지 않는 글리프:", "".join(dead), "— 정본 순서에서 새 글자로 바꿔 넣거나(코드 자리 유지) 쓰임을 등록해라")
    return 1 if dead or stale else 0


if __name__ == "__main__":
    sys.exit(main())
