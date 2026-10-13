#!/usr/bin/env python3
"""**말줄임 표기 게이트** — 공통 번역 규칙 2-11 · 2-12 (마스터 10-13).

  2-11  앞말 뒤 `…` 다음에 말이 이어지면 반각 공백(`그대도… 잊었다`) — 붙은 곳을 잡는다.
        문장 맨 앞 `…` 는 뒤를 붙인다(`…그런`) — 띄운 곳을 잡는다.
        예외(음절 끊기 · 의성어 되풀이)는 문맥 판단이라 기계로 안 가른다 — 붙은 꼴은
        「앞 조각이 한 글자」일 때만 허용한다(`세…리…오…스…`).
  2-12  `?`·`!` 와 `…` 가 겹치면 `…` 가 앞(`…!?`) — `!?…` 를 잡는다.

  python3 tools/check_ellipsis.py       # 위반이 있으면 종료 코드 1
"""

import glob
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

BAD = {
    "2-12 ?!… 순서": re.compile(r"[?!？！]+…"),
    "2-11 문장 앞 … 뒤 공백": re.compile(r"(?:^|\n|\}|%c|[.!?] )… (?=\S)"),
    # 앞 조각이 두 글자 이상인 낱말 뒤에 붙인 …: 음절 끊기(앞 조각 한 글자)만 예외
    "2-11 말줄임 뒤 공백 없음": re.compile(r"(?<=[가-힣A-Za-z0-9]{2})…(?=[가-힣A-Za-z0-9「『(])"),
}


# 한 낱말을 음절 단위로 끊어 말하는 자리(규칙 2-11 예외) — 기계로 못 가르니 자리를 적는다.
# 늘릴 땐 정말 한 낱말의 조각인지 본다(`사고였…던` = 사고였던).
SPLIT_WORD_OK = {
    ("ED2SCN12.json", "/308/t"),
    ("ED2SCN12.json", "/311/t"),
    ("ED2SCN12.json", "/331/t"),
}


def strings(x, path=""):
    if isinstance(x, str):
        yield path, x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield from strings(v, path + "/" + k)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from strings(v, path + "/%d" % i)


def main():
    bad = []
    for f in sorted(glob.glob(os.path.join(ROOT, "script", "*.json")) + glob.glob(os.path.join(ROOT, "textmap", "*.json"))):
        for p, s in strings(json.load(open(f, encoding="utf-8"))):
            if p.endswith("/note") or "…" not in s or (os.path.basename(f), p) in SPLIT_WORD_OK:
                continue
            for name, pat in BAD.items():
                for m in pat.finditer(s):
                    bad.append((name, os.path.basename(f), p, s[max(0, m.start() - 8) : m.end() + 8]))
    for b in bad:
        print("  ❌ %s  %s %s  %r" % b)
    print("말줄임 표기(2-11·2-12): 위반 %d" % len(bad) if bad else "✅ 말줄임 표기(2-11·2-12) 위반 0")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
