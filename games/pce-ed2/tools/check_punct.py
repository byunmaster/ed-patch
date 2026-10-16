"""번역 규칙 부호 검사 — 우리 문안(대사 tsv · 오프닝 대본)에서 규칙을 어긴 꼴을 센다(0 이어야 통과).

 · 2-12 「물음표·느낌표 + …」(`?…` `!…` `!?…`) — 「…」 가 앞에 와야 한다(`…?` `…!` `…!?`)
 · 2-11 문장 맨 앞 「… 」 뒤 공백 — 붙인다(`…그런 것처럼`)
"""

import glob
import json
import re
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
BAD_ORDER = re.compile(r"[?!？！]+…")
BAD_LEAD = re.compile(r"(?:^|\t|¶|(?<=[.!?]) |\| |/ )…+ (?=[가-힣A-Za-z0-9「“'(])")


def texts():
    for f in sorted(glob.glob(str(GAME / "data" / "dialogue_ko" / "*.tsv"))):
        for n, line in enumerate(Path(f).read_text(encoding="utf-8").splitlines(), 1):
            cols = line.split("\t")
            if len(cols) >= 2:
                yield f"{Path(f).name}:{n}", cols[-1]
    d = json.loads((GAME / "data" / "opening_sub.json").read_text(encoding="utf-8"))
    for i, s in enumerate(d["subs"]):
        yield f"opening_sub[{i}]", s["text"].replace("\n", " ")


def main() -> int:
    bad = []
    for where, t in texts():
        if BAD_ORDER.search(t):
            bad.append((where, "2-12 부호+…", t))
        if BAD_LEAD.search(t):
            bad.append((where, "2-11 문장 앞 … 뒤 공백", t))
    for w, k, t in bad[:20]:
        print(f"  ✗ {w} {k}: {t[:60]}")
    print(f"  부호 검사 [pce-ed2] — 어긋남 {len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
