#!/usr/bin/env python3
"""**씬 대사 한 쪽이 엔진 메시지 버퍼(136B)를 넘지 않는가** — 넘으면 `ra` 를 덮어 소프트락.

**왜.** 메시지 표시 함수는 쪽(`%c` 사이 구간)을 호출자 스택 128B 사본에 `strcpy` 한다(길이검사
없음). 하드 한계는 `0xA0-0x18 = 136B`(널 포함)이고 넘기면 `s0`→`fp`→`ra` 를 덮는다(devlog 056).
런타임 템플릿 쪽은 `check_runtime_template_width.check_byte_budget` 이 지키는데 **씬 대사 쪽은
아무도 안 쟀다** — 2026-10-19 전수 캡처에서 135B 쪽(ED1SCN5:340)이 나와서 센다.

`%c` 로 끊은 구간 하나를 쪽으로 본다(원판도 한 블록에 여러 쪽이 든 오프닝 서술을 이 단위로
돌린다 — 구간 최대 JP 95B/KR 83B). 구간 바이트 + 널 1 이 136 초과면 **실패**, 129 이상이면
권장선(128) 초과라 **경고**(자동 개행이 더 끼면 넘을 수 있다).

  python3 tools/check_scene_buf.py        # 전 씬(ED1·ED2)
"""

import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from patch_sys_ui import SCN_FILES

HARD = 136
SOFT = 128


def segments(b):
    """`%c` 로 끊은 구간의 바이트 길이(끝 `%c` 포함)."""
    out, cur, i = [], 0, 0
    while i < len(b):
        if 0x81 <= b[i] <= 0xFC:
            i += 2
            cur += 2
            continue
        if b[i : i + 2] == b"%c":
            out.append(cur + 2)
            cur = 0
            i += 2
            continue
        i += 1
        cur += 1
    if cur:
        out.append(cur)
    return out


def scan():
    over, warn = [], []
    for scn, _l, _z in SCN_FILES:
        with redirect_stdout(io.StringIO()):
            rows = [(eid, c) for _s, eid, _jp, c, _t in R.iter_candidates((scn,))]
        for eid, c in rows:
            for n in segments(c):
                if n + 1 > HARD:
                    over.append((scn, eid, n + 1))
                elif n + 1 > SOFT:
                    warn.append((scn, eid, n + 1))
    return over, warn


def main():
    over, warn = scan()
    for scn, eid, n in warn:
        print(f"  ⚠ {scn} jp{eid} {n}B (권장 {SOFT}B 초과 — 하드 {HARD}B 안)")
    for scn, eid, n in over:
        print(f"  ❌ {scn} jp{eid} {n}B > {HARD}B — strcpy 가 ra 를 덮는다")
    print(f"  씬 대사 쪽 버퍼: 하드 한계({HARD}B) 초과 {len(over)}건 · 권장선 초과 경고 {len(warn)}건")
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())
