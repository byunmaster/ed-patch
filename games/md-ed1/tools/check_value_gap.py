"""값 이음 줄의 **값 앞뒤 공백**이 정본과 같은가 — 정본 검사(`check_canon`)는 공백을 느슨하게(`\\s*`) 재서 「민첩성이 1내려갔다」(꼬리 조각이 공백 없이
시작)를 못 잡는다(md-ed1 10-22). 어댑터(`names_corpus`)가 내는 값 이음 줄(머리 `06` 자리 = `{n}` + 참조 없는 꼬리)만 따로, **값 바로 앞·뒤 글자가
공백인지** 정본 값과 맞댄다.

정본 값 `V = 앞{n}뒤` 와 우리 이은 줄 `L = 앞'{n}뒤'` 가 공백을 뺀 글자로는 같은데(같은 문구) 공백 유무가 다르면 어긋남.
공백까지 맞는 정본 값이 하나라도 있으면 통과(정본에 「{n}포인트」(붙임)·「{n} 내려갔다」(띄움)이 따로 있다).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import canon
import names_corpus

CATS = ("system", "battle")


def _flat(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _edges(text: str) -> tuple[str, str, bool, bool] | None:
    """`{n}` 첫 자리의 (앞 글, 뒤 글, 앞이 공백으로 끝나나, 뒤가 공백으로 시작하나)."""
    if "{n}" not in text:
        return None
    a, b = text.split("{n}", 1)
    return a, b, a[-1:].isspace(), b[:1].isspace()


def canon_values() -> list[str]:
    data = canon.load("ed1")["categories"]
    out = []
    for c in CATS:
        out += [v for v in data.get(c, {}).values() if isinstance(v, str) and "{n}" in v]
    return out


def check(pairs) -> tuple[int, list[str]]:
    vals = [(_edges(v), v) for v in canon_values()]
    errs, n = [], 0
    for where, _jp, ours, _kind in pairs:
        if not ours or "{n}" not in ours:
            continue
        e = _edges(ours)
        n += 1
        full, after_only, before_only = [], [], []
        for ce, v in vals:
            # 값 뒤쪽 문구가 같은(공백 무시) 정본 / 값 앞쪽 문구가 같은 정본 — 앞은 이름 자리(`{name}`) 때문에 정본 쪽이 줄 끝에서 겹치는지만 본다
            tail_same = _flat(ce[1]) != "" and _flat(e[1]) == _flat(ce[1])
            head_same = _flat(ce[0]) != "" and _flat(e[0]).endswith(_flat(ce[0]))
            if tail_same and head_same:
                full.append((ce, v))
            elif tail_same:
                after_only.append((ce, v))
            elif head_same:
                before_only.append((ce, v))
        if full:  # 문구가 앞뒤 다 겹치는 정본이 있으면 그 중 하나와 공백까지 같아야 한다
            if not any(ce[2] == e[2] and ce[3] == e[3] for ce, _v in full):
                errs.append(_msg(where, full[0][1], ours))
            continue
        for group, idx in ((after_only, 3), (before_only, 2)):
            if group and not any(ce[idx] == e[idx] for ce, _v in group):
                errs.append(_msg(where, group[0][1], ours))
    return n, errs


def _msg(where: str, v: str, ours: str) -> str:
    i = ours.index("{n}")
    return f"{where}: 값 앞뒤 공백이 정본 「{v}」 와 다르다 — 「…{ours[max(0, i - 6) : i + 12]}…」"


def main() -> int:
    n, errs = check(
        [p for p in names_corpus.pairs() if str(p[0]).startswith(("battlej:", "sysmsgj:"))]
    )
    print(f"  값 이음 공백 검사 [md-ed1] — 이은 줄 {n} · 어긋남 {len(errs)}")
    for e in errs[:30]:
        print("   ✗", e)
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
