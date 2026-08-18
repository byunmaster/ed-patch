#!/usr/bin/env python3
"""고유명사 정본의 회귀 — **표기가 흔들리면 자체 번역의 기준점이 사라진다.**"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "shared"))

import glossary as G  # noqa: E402


def test_categories_are_kept_apart():
    """⚠ 같은 JP 가 범주에 따라 다른 것을 가리킨다 — 평탄하게 합치면 구별이 사라진다.

    실측: `カース` 는 아이템이면 「커스」, 몬스터면 「카스」다(2026-08-18).
    """
    assert G.lookup("カース", "item") != G.lookup("カース", "monster")
    assert set(G.categories()) >= {"item", "monster", "person", "place"}


def test_no_empty_or_japanese_left_in_readings():
    """우리 표기 자리에 일본어가 남아 있으면 화면에 그대로 나간다."""
    import re

    for cat, jp, kr in G.all_names():
        assert kr and kr.strip(), f"{cat}:{jp} 표기가 비었다"
        assert not re.search(r"[ぁ-んァ-ヶ一-龯]", kr), f"{cat}:{jp} → {kr!r} 에 일본어가 남았다"


def test_lookup_without_category_finds_something():
    assert G.lookup("ルディア") == "루디아"
    assert G.lookup("없는이름") is None


def test_table_keeps_canon_order():
    """도구가 순서에 기대는 자리가 있다(슬롯 배열) — 정본 순서를 지킨다."""
    t = list(G.table("place"))
    raw = list(G.load()["categories"]["place"])
    assert t == raw


# ⚠ 새 테스트는 이 줄 위에.
if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for f in fns:
        try:
            f()
        except Exception as e:
            bad += 1
            print(f"  FAIL {f.__name__}: {e}")
    print(f"{len(fns) - bad}/{len(fns)} passed")
    sys.exit(1 if bad else 0)
