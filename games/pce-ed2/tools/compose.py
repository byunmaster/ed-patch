"""지명 조합 — **정본 어간 + 정본 접미**로 만들어지는 꼴만 조합한다(docs/naming.md 「지명 칸」, 마스터 10-07·10-08).

접미 번역은 정본 place 범주에 **이미 쓰인 꼴**에서 읽는다(`の町` → `마을` · `の港` → `항구` · `城` → `성` …) — 이 모듈엔 표가 없다.
원문이 접미를 가졌으면 접미 있는 꼴, 이름뿐이면 이름만(원문 꼴을 따른다 — 접미를 더하거나 빼지 않는다). 칸은 붙여 쓴다.
`A～B` 구간 라벨은 정본 battle 의 `{name}～{name}` → `{name}-{name}` · `{name}～城` → `{name}-성` 꼴을 따른다.
어간이 정본에 없거나 접미 예가 없는 것은 조합하지 않고 None 을 돌려준다(관리자 후보).
"""

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon

_suffix_cache: dict[str, str] | None = None


def suffixes() -> dict[str, str]:
    """{JP 접미: KR 접미} — 정본 place·ui 에서 어간 값 뒤에 붙은 꼴을 읽는다(가장 많은 값). `の` 를 뗀 꼴도 같은 접미로 본다."""
    global _suffix_cache
    if _suffix_cache is None:
        place = canon.table("place", "ed2")
        allv = {**place, **canon.table("ui", "ed2")}
        cnt: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for k, v in allv.items():
            for n in range(1, 5):
                if len(k) <= n:
                    continue
                stem_kr = place.get(k[:-n])
                if stem_kr and v.startswith(stem_kr) and v != stem_kr:
                    cnt[k[-n:]][v[len(stem_kr) :]] += 1
        out = {s: c.most_common(1)[0][0] for s, c in cnt.items()}
        for s, v in list(out.items()):
            if s.startswith("の") and len(s) > 1:
                out.setdefault(s[1:], v)  # 「アムダ村」 — の 없는 접미
        _suffix_cache = out
    return _suffix_cache


def stem(jp: str) -> str | None:
    for cat in ("place", "ui"):
        r = canon.lookup(jp, cat, "ed2")
        if r:
            return r
    return None


def place(jp: str) -> str | None:
    """원문 지명 → 정본 어간 + 정본 접미 조합(없으면 None)."""
    if "～" in jp:
        a, _, b = jp.partition("～")
        left = stem(a) if a else None
        if left and b == "城":
            return f"{left}-{suffixes().get('城', '성')}"
        r = stem(b) if b else None
        if left and r:
            return f"{left}-{r}"
        return None
    sfx = suffixes()
    for s in sorted(sfx, key=len, reverse=True):
        if jp.endswith(s) and len(jp) > len(s):
            st = stem(jp[: -len(s)])
            if st:
                return st + sfx[s]
    return None
