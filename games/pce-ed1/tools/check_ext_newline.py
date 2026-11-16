"""메시지 앞에 **원문 스크립트의 줄바꿈 `01`**(메시지 밖 바이트)이 있는 화자 없는 창의 첫 쪽 줄 수 — 우리 조판이 원판 최대를 넘으면 실패.

마스터 10-30: 해설 창 첫 줄이 비어 보였다(씬 0 「세리오스는 라이아스 일행을…」). 그 `01` 은 원판 바이트 그대로라 원판도 같은 자리가 빈다. 문제는 4줄 쪽 허용(10-29) 뒤 「빈 줄 + 4줄」이
창(4행)을 넘는 것 — 원판 짝 표로 센 첫 쪽 최대 줄 수(원문 줄바꿈·13칸 줄넘김 모델)를 한도로 둔다. 원판에 4줄이 있으면 4줄 우리 쪽은 근거가 있다(2026-10-30 실측: 원판 4줄 19개).

    python3 games/pce-ed1/tools/check_ext_newline.py
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import containers
import font
import messages as M
import typeset


def orig_first_page(m: M.Message) -> int:
    lines = 0
    for t in m.tokens:
        if isinstance(t, str):
            lines += max(1, math.ceil(len(t) / 13))
        elif t[1] in (5, 3) and lines:
            return lines
    return lines


def check() -> list[str]:
    seen: set[tuple[int, int]] = set()
    rows = []  # (sid, key, 원판 첫 쪽, 우리 첫 쪽)
    for c in containers.scan():
        for b in c["blocks"]:
            sid = b["id"]
            trs = M.load_translations(sid)
            if not trs:
                continue
            typeset.set_scene(sid)
            for m in M.parse(b["data"]):
                k = (sid, m.start)
                if k in seen or m.speaker or m.common is not None or not m.start:
                    continue
                if b["data"][m.start - 1] != 0x01 or (m.tokens and m.tokens[0] == ("op", 1)):
                    continue
                seen.add(k)
                tr = trs.get(m.key)
                if not tr or tr.get("raw"):
                    continue
                pg = typeset.pages(font.expand_packed(tr["t"].lstrip(" ")), speaker=False, four=True)
                if pg:
                    rows.append((sid, m.key, orig_first_page(m), len(pg[0])))
    limit = max(r[2] for r in rows)
    print(f"원문 `01` 앞선 화자 없는 창 {len(rows)}개 · 원판 첫 쪽 최대 {limit}줄 · 우리 첫 쪽 최대 {max(r[3] for r in rows)}줄")
    return [f"scn{s:03d} {k}: 우리 첫 쪽 {o}줄 > 원판 최대 {limit}줄" for s, k, _, o in rows if o > limit]


if __name__ == "__main__":
    e = check()
    for x in e:
        print("✗", x)
    sys.exit(1 if e else 0)
