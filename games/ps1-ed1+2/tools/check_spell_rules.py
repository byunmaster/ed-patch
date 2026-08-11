#!/usr/bin/env python3
"""`dos_spelling_fixes.json` 의 `replace` 중 **한 번도 안 걸리는 규칙**을 센다.

치환은 목록 **순서대로** 걸린다. 그래서 규칙 하나가 죽는 길이 둘 있고 **둘 다 조용하다**:

1. **상류가 이미 고쳤다** — `fix_spacing` 이 `할때`→`할 때` 를 먼저 처리하면
   `처단할때까지는` 규칙은 영영 사냥감을 못 만난다(무해하지만 목록만 부푼다).
2. **겨냥한 표기가 그 시점엔 없다** — 검사기는 교정된 문안(`라누라왕국은`)을 보고 규칙을
   만드는데 `spell_fix` 가 보는 건 아직 `라느라왕국은` 이었다. 실측 5건이 그렇게 죽어 있었다
   (2026-08-10). 지명 정본 교정을 `spell_fix` 앞으로 옮겨 고쳤다.

그래서 **파이프라인과 같은 순서로** 코퍼스를 통과시켜 검산한다.

  python3 tools/check_spell_rules.py        # 요약
  python3 tools/check_spell_rules.py -v     # 죽은 규칙 전부
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R  # noqa: E402
from common import OUT_DIR, ROOT  # noqa: E402

# `parse_kr` 이 `spell_fix` 직전까지 하는 일 — 순서가 곧 판정이라 여기 그대로 옮긴다.
PLACES = (("폰 리그", "온리크"), ("폰리그", "온리크"), ("라느라", "라누라"))


def corpus():
    for p in sorted(glob.glob(os.path.join(OUT_DIR, "dos_kr", "*", "*.json"))):
        doc = json.load(open(p, encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        for e in doc.get("entries", []):
            t = R.fix_spacing(R.resolve_dos_breaks(e["text"]))
            for a, b in PLACES:
                t = t.replace(a, b)
            yield t


def main(verbose=False):
    rep = json.load(open(os.path.join(ROOT, "dos_spelling_fixes.json"), encoding="utf-8"))[
        "replace"
    ]
    hit = [0] * len(rep)
    n = 0
    for t in corpus():
        n += 1
        for i, (a, b) in enumerate(rep):
            if a in t:
                hit[i] += t.count(a)
                t = t.replace(a, b)
    dead = [(a, b) for (a, b), h in zip(rep, hit, strict=True) if not h]
    print(f"문장 {n} · replace 규칙 {len(rep)} · 한 번도 안 걸림 {len(dead)}")
    for a, b in dead[: (None if verbose else 12)]:
        print(f"  {a!r} → {b!r}")
    if not verbose and len(dead) > 12:
        print(f"  … 그 밖 {len(dead) - 12}건 (-v 로 전부)")
    return 0  # 사문(死文)은 대개 무해하다 — 실패시키지 않고 보고만 한다


if __name__ == "__main__":
    sys.exit(main("-v" in sys.argv))
