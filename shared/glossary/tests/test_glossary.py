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


# 🔴 **음차+번역**이라 띄우는 게 맞는 이름 — 여기 있는 것만 공백이 허용된다.
#    새로 추가하려면 **왜 번역인지**를 같이 적는다(`naming.md` 「외래어 이름은 공백을 뗀다」).
SPACED_OK = {
    "レストナキノコ": "`キノコ` 를 음차(`키노코`)하지 않고 **버섯**으로 번역했다 — 고유명+보통명사",
}


def test_katakana_names_are_joined():
    """🔴 **가타카나 한 덩어리는 붙여 쓴다**(유저 확정 2026-08-29 · 2026-09-06 보강).

    가르는 기준은 「원문이 가타카나인가」가 아니라 **「우리가 음차했는가」**다 —
    음차+음차는 붙이고(`배틀슈트`), 음차+번역한 보통명사는 띄운다(`레스토나 버섯`).

    ⚠ **이 규칙을 지키는 장치가 없어서 넷이 샜다**(2026-09-06 실측: `배틀 슈트`·사본·
    `피코 해머`·`타이슨 펀치`). 규칙만 문서에 적고 검사기를 안 만들면 다음에 또 샌다 —
    `オークホーン` 이 08-12 붙임 → 08-27 띄움 → 08-29 붙임으로 두 번 뒤집힌 것과 같은 자리다.
    """
    import re

    kata = re.compile(r"^[ァ-ヴーｦ-ﾟ・]+$")
    bad = [
        (cat, jp, kr)
        for cat, jp, kr in G.all_names()
        if kata.match(jp) and " " in kr and jp not in SPACED_OK
    ]
    assert not bad, (
        "가타카나 한 덩어리인데 우리 표기에 공백이 있다 — 붙이거나 `SPACED_OK` 에 근거와 함께 올린다:\n  "
        + "\n  ".join(f"{c} {j} → {k!r}" for c, j, k in bad)
    )


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
