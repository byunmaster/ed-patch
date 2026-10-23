#!/usr/bin/env python3
"""**토큰 자리** 전수 — 번역문의 제어·사전 토큰이 원문과 같은 쪽(글 앞/글 뒤)에 있는가. 0건 유지.

    python3 tools/check_token_order.py

## 왜 있나 (2026-10-19)

토큰 계약(`textmap.check_tokens`)은 순서만 본다. `init_from_tm` 이 PS1 문안 뒤에 토큰을 몰아 붙인 초안이 그대로 나가
「물건이옵니다.감사합니다.」(문장 끝 사전 문장) · 「주지.세리오스」(화자표가 글 뒤) · 소니아 「사자로 왔습니다.」가 끝없이 되풀이(CALL_TBL 이 글 뒤)
같은 꼴이 최종 롬에 나갔다(qa 58조각 + 같은 꼴 70여 조각). 규칙·판정은 `tokenorder.py`.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: E402,F401,I001  (common 보다 먼저 — shared/text 와 이름이 겹친다)
import common  # noqa: E402
import tokenorder  # noqa: E402
import units  # noqa: E402

# 명시 예외 — 조각 id: 사유
EXEMPT = {
    "b2ae99d967cb": "원문이 전부 사전 낱말(「{わたし}は{ソニア}」)이라 글 앞/뒤를 가를 글이 없다 — 번역문은 이름을 문장 속에 쓴다",
    "3025b688c633": "원문이 글 한 자(「み」)만 남은 찌꺼기 조각 — 번역문은 호출 하나뿐이다",
}


def scan() -> dict[str, list[str]]:
    rom = common.rom_bytes()
    items, _ = units.extract(rom)
    segs = units.segments(items, text.resolver(rom), units.table_targets(rom))
    tm = json.loads((common.GAME_DIR / "textmap" / "segments.json").read_text(encoding="utf-8"))
    bad = {}
    for s in segs:
        v = tm.get(s["id"])
        if not v or not v.get("kr") or s["id"] in EXEMPT:
            continue
        p = tokenorder.problems(s["jp"], v["kr"], s["tokens"], "tm" in v)
        if p:
            bad[s["id"]] = p
    return bad


def main() -> int:
    bad = scan()
    print(f"토큰 자리 검사: 위반 {len(bad)}조각")
    for k, p in list(bad.items())[:20]:
        print("  ✗", k, p[:4])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
