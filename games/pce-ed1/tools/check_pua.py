#!/usr/bin/env python3
"""우리 문안(`script/**/*.json`)에 사용자 영역 문자(U+E000~U+F8FF)가 섞이면 실패 — PS1 내부 자리표시(붙임 공백 `U+E003` 등)가 이식 때 딸려 들어온 것이다(10-18).

PS1 에서 쓰는 PUA 는 이 게임 글꼴에선 다른 글리프로 구워진다(md 에서 「약초구말이군」 꼴 실측). `glyph_order.json` 은 글리프 표 자체라 제외한다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

PUA = re.compile("[-]")


def scan(root: Path) -> list[tuple[str, str]]:
    out = []
    for p in sorted(root.rglob("*.json")):
        if p.name == "glyph_order.json":
            continue
        for m in PUA.finditer(p.read_text("utf-8")):
            out.append((str(p.relative_to(root)), f"U+{ord(m.group(0)):04X}"))
        # JSON 이스케이프(\\ue003) 꼴도 본다
        for m in re.finditer(r"\\u([eE][0-9a-fA-F]{3}|f[0-8][0-9a-fA-F]{2})", p.read_text("utf-8")):
            out.append((str(p.relative_to(root)), "U+" + m.group(1).upper()))
    return out


def main() -> int:
    hits = scan(common.GAME_DIR / "script")
    print(f"PUA 문자 검사 — 문안 어디에도 U+E000~F8FF 없어야 한다 — 걸림 {len(hits)}")
    for f, c in hits[:20]:
        print(f"  ✗ {f}: {c}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
