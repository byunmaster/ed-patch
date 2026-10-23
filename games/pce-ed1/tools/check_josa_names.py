#!/usr/bin/env python3
"""정본 고유명사 뒤 조사(이/가·은/는·과/와·을/를·으로/로) 받침 대조 — 우리 문안 전체(씬·시스템·전투·자막)를 훑는다(10-18).

  python3 tools/check_josa_names.py [--list]

기존 `check_josa` 는 주입 토큰 뒤만 본다. 이 검사는 **명사 목록 기반**이다 — 정본(`canon.all_names('ed1')`)의 표기가 어절 머리에 서고 바로 뒤에
조사가 붙은 자리를 찾아, 이름의 마지막 글자 받침과 조사가 맞는지 본다(「슬러그이」✗ → 「슬러그가」). 이름이 어절 머리일 때만 본다(관형사형·합성어 오탐을 줄인다).
조사 훅 토큰(`이/가` 병기)·글자 뒤에 더 이어지는 경우(「이야기」)는 안 친다. 최소 이름 길이 2.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon
import common

PAIRS = {"이": True, "가": False, "은": True, "는": False, "과": True, "와": False, "을": True, "를": False}  # 값 = 받침 있는 말 뒤 꼴
HANG = re.compile("[가-힣]")


def has_batchim(ch: str) -> bool:
    return (ord(ch) - 0xAC00) % 28 != 0


def name_list() -> list[str]:
    out = {kr for _c, _jp, kr in canon.all_names("ed1") if len(kr) >= 2 and HANG.fullmatch(kr[-1]) and re.fullmatch(r"[가-힣]+", kr)}
    return sorted(out, key=lambda s: -len(s))


def texts():
    for p in sorted((common.GAME_DIR / "script").rglob("*.json")):
        if p.name in ("glyph_order.json", "coverage_baseline.json", "broken_fragments.json"):
            continue
        yield from _walk(json.loads(p.read_text("utf-8")), p.name)


def _walk(o, where):
    if isinstance(o, str):
        yield where, o
    elif isinstance(o, dict):
        for k, v in o.items():
            if k.startswith("_"):
                continue
            yield from _walk(v, where)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v, where)


def violations(text: str, names: list[str]) -> list[tuple[str, str]]:
    bad = []
    rx = re.compile("(?<![가-힣])(" + "|".join(map(re.escape, names)) + ")([이가은는과와을를])(?![가-힣/]|\\()")
    for m in rx.finditer(text):
        name, j = m.group(1), m.group(2)
        # 받침 일치: 이름 끝이 받침 있으면 이·은·과·을, 없으면 가·는·와·를
        if PAIRS[j] != has_batchim(name[-1]):
            bad.append((name, j))
    return bad


def main() -> int:
    names = name_list()
    seen = total = 0
    bad = []
    for where, t in texts():
        if not re.search("[가-힣]", t):
            continue
        seen += 1
        for name, j in violations(t, names):
            bad.append((where, name + j, t[:40]))
    print(f"조사 대조(정본 이름 {len(names)} × 문안 {seen}) — 어긋남 {len(bad)}")
    for w, nj, t in bad[:60]:
        print(f"  ✗ {w}: {nj}  「{t}」")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
