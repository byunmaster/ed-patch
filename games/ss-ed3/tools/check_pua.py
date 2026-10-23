"""문안에 사용자 영역(PUA, U+E000~U+F8FF) 문자가 섞이면 실패 (게이트).

    python3 games/ss-ed3/tools/check_pua.py

다른 기종 문안을 가져올 때 원 기종의 내부 자리표시 문자가 딸려 들어오면 다른 글리프로 구워진다(md-ed2 10-18 실측 75스트림).
대상: `script/**/*.json`(대사·읽을거리·음성 자막) · `credits_map.json` · `narration_manual.json`. 날 글자와 `\\uXXXX` 이스케이프 둘 다 본다.
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

LO, HI = 0xE000, 0xF8FF


def pua_in(s):
    """`s` 안의 PUA 문자 목록."""
    return [c for c in s if LO <= ord(c) <= HI]


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


def scan(paths):
    """`[(파일, 문자열 앞 30자, [PUA…])]` — JSON 을 파싱한 값 기준이라 이스케이프도 잡힌다."""
    bad = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        for s in _strings(doc):
            found = pua_in(s)
            if found:
                bad.append((os.path.relpath(p, C.GAME_DIR), s[:30], found))
    return bad


def targets():
    g = C.GAME_DIR
    ps = glob.glob(os.path.join(g, "script", "**", "*.json"), recursive=True)
    ps += [os.path.join(g, n) for n in ("credits_map.json", "narration_manual.json")]
    return sorted(p for p in ps if os.path.exists(p))


def main():
    ps = targets()
    bad = scan(ps)
    n = sum(len(b[2]) for b in bad)
    print(f"  PUA 문자 {n} 자 / 파일 {len(ps)}")
    for f, head, cs in bad[:20]:
        print(f"    🔴 {f} '{head}' — {' '.join('U+%04X' % ord(c) for c in cs)}")
    if bad:
        print("  🔴 문안에 PUA 가 섞였다 — 다른 글리프로 구워진다. 뜻대로 바꾼다")
        return 1
    print("  ✅ 문안에 PUA 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
