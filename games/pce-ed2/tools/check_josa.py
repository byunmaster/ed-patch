"""조사 전수 검사 — 정본 고유명사 전 목록 × 뒤 조사(이/가 · 은/는 · 을/를 · 과/와 · 으로/로)의 받침 대조 (10-18, md-ed2 「슬러그이」 발견).

이름을 정본으로 바꾸면서 조사를 안 고친 줄을 잡는다. 기존 조사 검사는 관형사형(`간`·`온` …) 오탐 때문에 이 축을 못 봤다 — 여기는 **어절 = 정본 명사 + 조사** 일 때만 본다:
어절에서 조사를 뗀 어간(앞 어절과 이어 붙인 여러 낱말 이름 포함)이 정본 명사 목록에 있고 어절 자체는 목록에 없을 때, 어간의 받침과 조사 꼴이 맞아야 한다.
0 이어야 통과. 합성 테스트: `tests/test_check_josa.py`.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon

# 조사 → (받침 있어야 맞음 | 없어야 맞음 | ㄹ 포함 없음 …) 로 판정하는 함수 대신 표로
PAIRS = {"이": "겹", "가": "홑", "은": "겹", "는": "홑", "을": "겹", "를": "홑", "과": "겹", "와": "홑", "으로": "으", "로": "로"}
_PARTICLES = sorted(PAIRS, key=len, reverse=True)
_TRIM = ".,!?…~「」『』()\"'“”‘’"


def batchim(ch: str) -> int | None:
    return (ord(ch) - 0xAC00) % 28 if "가" <= ch <= "힣" else None


def nouns() -> set[str]:
    out: set[str] = set()
    for title in ("eiyuu", "ed2"):
        try:
            for _c, _jp, kr in canon.all_names(title):
                if isinstance(kr, str) and len(kr) >= 2 and "가" <= kr[-1] <= "힣":
                    out.add(kr)
        except Exception:  # noqa: BLE001
            pass
    return out


def wrong(stem: str, p: str) -> bool:
    """어간 뒤에 이 조사가 틀린가."""
    f = batchim(stem[-1])
    if f is None:
        return False
    kind = PAIRS[p]
    if kind == "겹":
        return f == 0
    if kind == "홑":
        return f != 0
    if kind == "으":  # 으로 — 받침 없음·ㄹ 이면 '로' 가 맞다
        return f == 0 or f == 8
    return f not in (0, 8)  # 로 — 받침(ㄹ 제외)이 있으면 '으로'


def scan(text: str, names: set[str]) -> tuple[int, list[str]]:
    """(본 자리 수, 어긋난 어절 목록). 쪽·구간 표지는 어절 경계로 본다."""
    seen = 0
    bad: list[str] = []
    for seg in re.split(r"[¶§\f\n]", text):
        toks = seg.split()
        for i, raw in enumerate(toks):
            t = raw.strip(_TRIM)
            if not t or t in names:
                continue
            for p in _PARTICLES:
                if t.endswith(p) and len(t) > len(p):
                    stem = t[: -len(p)]
                    cands = [stem] + [" ".join(toks[j:i] + [stem]).strip(_TRIM) for j in range(max(0, i - 2), i)]
                    hit = next((c for c in cands if c in names), None)
                    if hit is not None:
                        seen += 1
                        if wrong(hit, p):
                            bad.append(t)
                    break
    return seen, bad


def main() -> int:
    import check_punct

    names = nouns()
    seen = 0
    bad = []
    for where, _kind, t, _d in check_punct.corpus():
        n, b = scan(t, names)
        seen += n
        bad.extend((where, x) for x in b)
    for w, x in bad[:25]:
        print(f"  ✗ {w} 조사: {x}")
    print(f"  조사 전수 검사 [pce-ed2] — 정본 명사 {len(names)} · 본 자리 {seen} · 어긋남 {len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
