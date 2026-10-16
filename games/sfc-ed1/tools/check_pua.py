"""번역 정본에 사용자 영역(PUA, U+E000~U+F8FF) 문자가 섞였나 — 섞이면 실패.

PS1 문안을 가져올 때 PS1 내부 자리표시 문자가 PUA 로 딸려 오면 다른 기종 글리프로 구워져 엉뚱한 글자가 화면에 나온다
(md-ed2: 「약초구말이군」 75스트림, 10-18). 번역 정본(`textmap/*.json` 의 모든 문자열 값)을 전수한다. 기준선 0.

  python3 tools/check_pua.py
"""

import json
import re
import sys
from pathlib import Path

PUA = re.compile("[-]")
TEXTMAP = Path(__file__).resolve().parent.parent / "textmap"


def walk(o, path=""):
    """JSON 값 속 문자열을 (경로, 문자열)로 낸다."""
    if isinstance(o, str):
        yield path, o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}/{i}")


def scan(o) -> list[tuple[str, str]]:
    """PUA 가 든 문자열의 (경로, 든 문자들 U+XXXX)."""
    out = []
    for p, s in walk(o):
        f = PUA.findall(s)
        if f:
            out.append((p, " ".join(f"U+{ord(c):04X}" for c in sorted(set(f)))))
    return out


def main() -> int:
    bad = []
    n = 0
    for f in sorted(TEXTMAP.glob("*.json")):
        n += 1
        bad += [(f"{f.name}{p}", u) for p, u in scan(json.loads(f.read_text(encoding="utf-8")))]
    print(f"PUA 검사: textmap {n}파일 · PUA 든 문자열 {len(bad)}")
    for p, u in bad[:10]:
        print(f"  ❌ {p}: {u}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
