#!/usr/bin/env python3
"""고유명사 뒤 조사 전수 — 정본 고유명사 전 목록 × 이/가 · 은/는 · 과/와 · 을/를 · 으로/로 를 뒤 받침과 대조한다. 0건 유지.

    python3 tools/check_josa_names.py

## 왜 있나 (2026-10-18)

이름을 정본으로 바꾸면서 조사를 안 고친 줄(「슬러그이」 — md-ed2)이 나왔다. 기존 조사 검사(`check_josa`)는 관형사형 오탐 때문에 이/가·은/는·과/와
축을 많이 비켜 간다. 여기는 **명사 목록 기반**이다 — 정본(`shared/canon/nouns`)의 모든 한글 표기와 사전(`dict.json`)이 푸는 이름을 뒤에서
찾아, 바로 뒤에 붙은 조사가 마지막 글자의 받침과 맞는지 본다. 사전 토큰(`{Dx:yy}`)은 토큰이 푸는 이름으로 센다. 조사 자리표시자(`{은/는}`)와
다음 글자가 이어지는 낱말(이름 + 「이옵니다」 처럼 조사가 아니라 어미)은 안 본다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: E402,F401,I001  (common 보다 먼저 — shared/text 와 이름이 겹친다)
import common  # noqa: E402
import namesrc  # noqa: E402

PAIRS = {  # 조사 → (받침 뒤, 모음 뒤)
    "이": ("이", "가"), "가": ("이", "가"), "은": ("은", "는"), "는": ("은", "는"),
    "과": ("과", "와"), "와": ("과", "와"), "을": ("을", "를"), "를": ("을", "를"),
}  # fmt: skip
TOKEN = re.compile(r"\{D[0-9A-F]:[0-9A-F]{2}\}|\{D[0-9A-F]\}")


def has_final(ch: str) -> bool | None:
    """한글 음절이 받침을 가지는가(숫자·영문 등은 None — 판단 안 함)."""
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 != 0
    return None


def names() -> set[str]:
    out: set[str] = set()
    root = common.ROOT / "shared" / "canon" / "nouns"
    for f in root.glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        for cat in data.get("categories", {}).values():
            for v in cat.values():
                if isinstance(v, str) and re.fullmatch(r"[가-힣]{2,}", v):
                    out.add(v)
    return out


def expand(s: str, dk: dict[str, str]) -> str:
    return TOKEN.sub(lambda m: dk.get(m.group(0).strip("{}"), "") or "\x00", s)


def wrong(s: str, nm: set[str]) -> list[str]:
    """한 문안에서 이름 바로 뒤 조사가 받침과 어긋난 자리 목록."""
    out = []
    for m in re.finditer(r"([가-힣]+)(이|가|은|는|과|와|을|를)(?![가-힣])", s):
        word, j = m.group(1), m.group(2)
        # 이름이 단어 끝에 붙은 경우만(이름 앞 접두 글자는 허용)
        hit = next((n for n in nm if word.endswith(n)), None)
        if not hit:
            continue
        f = has_final(hit[-1])
        if f is None:
            continue
        want = PAIRS[j][0 if f else 1]
        if want != j:
            out.append(f"{hit}{j}→{hit}{want}")
    return out


def scan() -> list[tuple[str, str]]:
    rom = common.rom_bytes()
    dm = namesrc.dict_map(rom)
    dk = {k: (v.get("kr") or "") for k, v in dm.items()}
    nm = names() | {v for v in dk.values() if re.fullmatch(r"[가-힣]{2,}", v)}
    tm = json.loads((common.GAME_DIR / "textmap" / "segments.json").read_text(encoding="utf-8"))
    bad = []
    for k, v in tm.items():
        kr = v.get("kr")
        if not kr:
            continue
        s = re.sub(r"<[^>]*>|\{[^{}]*/[^{}]*\}", " ", expand(kr, dk))
        for w in wrong(s, nm):
            bad.append((k, w))
    return bad


def main() -> int:
    bad = scan()
    print(f"이름 뒤 조사 전수: 본 문안 {len(json.loads((common.GAME_DIR / 'textmap' / 'segments.json').read_text(encoding='utf-8')))}조각 · 어긋남 {len(bad)}")
    for k, w in bad[:40]:
        print("  ✗", k, w)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
