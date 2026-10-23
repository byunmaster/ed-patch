#!/usr/bin/env python3
"""문안에 사용자 영역(PUA, U+E000~U+F8FF) 글자가 섞였나 — **다른 기종 문안을 가져오다 원 기종의 자리표시 글자가 딸려 오면 다른 글리프로 구워진다**
(10-18 md-ed2: 75스트림). 우리 문안(`script/`·`ui_*.json` 의 `kr`)에서 센다. 자기가 일부러 쓰는 PUA 는 `ALLOWED` 에 자리째 적는다.

    python3 tools/check_pua.py
"""

import glob
import json
import os
import sys

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 파일(게임 기준) → {키: 허용 문자열}. 「시스템」 반각 합성 글리프(필드 메뉴 4코드 — devlog 10-10)
ALLOWED = {"ui_ed3.json": {"0x0A10F4": "시템"}}


def is_pua(c):
    return "" <= c <= ""


def walk(o, path=()):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "kr" and isinstance(v, str):
                yield path, v
            else:
                yield from walk(v, path + (k,))


def scan(game=GAME, allowed=ALLOWED):
    """반환 (센 문안 수, [(파일, 위치, 문안)]) — 허용 목록과 똑같은 문안만 통과."""
    bad, total = [], 0
    files = glob.glob(os.path.join(game, "script", "**", "*.json"), recursive=True)
    files += glob.glob(os.path.join(game, "ui_*.json"))
    for f in sorted(files):
        rel = os.path.relpath(f, game)
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        for path, kr in walk(data):
            total += 1
            if (
                any(is_pua(c) for c in kr)
                and allowed.get(rel, {}).get(path[-1] if path else "") != kr
            ):
                bad.append((rel, "/".join(path), kr))
    return total, bad


def main():
    total, bad = scan()
    print(f"   PUA 검사 — 문안 {total:,}개 · 사용자 영역 글자 섞임 {len(bad)}")
    for rel, p, kr in bad[:20]:
        print(f"     ❌ {rel} {p}: {kr!r}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
