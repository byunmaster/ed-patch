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
    # ── ui 라벨 ───────────────────────────────────────────────────────────────
    # ⚠ 이 규칙의 자는 「원문이 가타카나인가」가 아니라 **「우리가 음차했는가」**다.
    #   UI 라벨은 이름이 아니라 **말**이라 대개 음차가 아니라 번역이고, 그러면 띄우는 게
    #   맞다. `オートバトル` 를 「오토배틀」로 음차했다면 붙였을 것이다.
    "オートバトル": "음차가 아니라 **번역**이다(`자동 전투`) — 두 낱말이라 띄운다",
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



# ── UI 라벨 정본 ─────────────────────────────────────────────────────────────
# 트랙마다 제 파일에 두어 **조용히 갈렸던** 자리다(2026-09-08). 같은 `その他` 가
# `그외`(md·새턴) · `그 외`(PS1 ui-canon) · `기타`(PCE) 셋이었고, 화면은 트랙마다
# 멀쩡해서 **여덟을 나란히 놓아야만** 보였다.


def test_ui_category_exists():
    assert "ui" in G.categories()


def test_그외는_기타다():
    """정발 ED1 = 「기타」 · ED2 = 「그외」로 갈렸고 「그외」가 맞춤법이 틀린 쪽이다.

    「그」는 관형사라 「그 외」로 띄어야 맞는데, 한 낱말인 「기타」로 가면 띄어쓰기
    문제 자체가 없어지고 2칸이라 고정 폭 메뉴에도 유리하다(유저 확정 2026-09-08).
    """
    assert G.lookup("その他", "ui") == "기타"


def test_전투설정은_붙여_쓴다():
    """⚠ 맞춤법은 「전투 설정」이 맞다 — **일부러** 붙인 것이다.

    새턴 레코드가 8바이트라 9바이트가 안 들어가고, 정발 ED1 도 붙였다.
    **선의로 되돌리지 않게** 테스트로 못 박는다.
    """
    assert G.lookup("戦闘設定", "ui") == "전투설정"


def test_갈렸던_다섯():
    """유저가 화면으로 판정했다(2026-09-08). 다섯 다 **칸 폭이 같아** 자리가 안 는다.

    ⚠ `強さ`(강함)와 `状態`(상태)는 **다른 말**인데 옛 표기가 둘을 뭉개고 있었다 —
    정발도 「강함」으로 썼다.
    """
    assert G.lookup("捨てる", "ui") == "버린다"   # ↔ 버리기(PCE)
    assert G.lookup("戦う", "ui") == "공격"       # ↔ 싸움(pc98)
    assert G.lookup("守る", "ui") == "방어"       # ↔ 막기(pc98)
    assert G.lookup("使う", "ui") == "사용"       # ↔ 쓰기(pc98)


def test_한_원문이_자리마다_다르면_갈라_담는다():
    """🔴 `強さ` 는 **한 원문에 우리 말 셋**이다 — 평면으로 담으면 셋이 한 말로 뭉개진다.

    파티 메뉴 「상태」 · 전투 커맨드 「강함」(정발 ED2) · 능력치 창 「힘」.
    ⚠ **맨 `強さ` 는 일부러 비워 둔다.** 담으면 `diff_labels` 가 원문으로 짝지어
    **파티 메뉴를 「강함」으로 덮는다** — 그 사고는 이미 났다(능력치 창에 「상태 6」,
    유저 QA 2026-08-14).
    """
    assert G.lookup("強さ", "ui") is None, "맨 `強さ` 가 다시 들어왔다 — 자리로 갈라야 한다"
    assert G.lookup("強さ@파티메뉴", "ui") == "상태"
    assert G.lookup("強さ@전투커맨드", "ui") == "강함"
    assert G.lookup("強さ@능력치", "ui") == "힘"
    # 자리를 안 댄 열쇠는 정본에 없으니 **안 잰다** — 다만 조용히 넘기지 않고 `unmatched` 로 낸다.
    out = G.diff_labels({"強さ": "상태"})
    assert out.diff == []
    assert out.unmatched == ["強さ"], "자리를 안 댄 열쇠가 조용히 사라졌다"


def test_diff_labels_는_다른_것과_못_견준_것을_같이_돌려준다():
    out = G.diff_labels({"その他": "그외", "装備": "장비", "이_게임에만": "무엇"})
    assert out.diff == [("その他", "기타", "그외")]
    # 게임에만 있는 라벨은 갈린 게 아니라 **없는 것**이다 — 다만 조용히 넘기지 않는다
    assert out.unmatched == ["이_게임에만"]


def test_커버리지를_조용히_넘기지_않는다():
    """🔴 종전엔 정본에 없는 열쇠를 **말없이 건너뛰었다.**

    그래서 가나 전용 게임에서 **44 중 6 만 견주고도 「갈린 데 둘뿐」으로 보였다**
    (sfc-ed1 실측 2026-09-08). 초록불이 거짓말을 하지 않으려면 **검사기 자신의
    커버리지**가 보여야 한다.
    """
    out = G.diff_labels({"모르는말1": "가", "모르는말2": "나"})
    assert out.diff == []
    assert len(out.unmatched) == 2, "못 견준 열쇠가 조용히 사라졌다"


def test_장음_부호는_정규화한다():
    """정본은 `リ－ダ－`(전각 하이픈), 게임은 `リーダー`(장음) — 같은 말인데 안 맞았다.

    ⚠ 별칭에 하나씩 올리는 게 아니라 **잴 때 정규화한다.** 별칭은 낱말을 잇는 자리지
    부호를 잇는 자리가 아니다(sfc-ed1 지적 2026-09-08).
    """
    out = G.diff_labels({"リーダー": "리더", "メッセージ": "메시지"})
    assert out.diff == [] and out.unmatched == []


def test_원문이_다르면_별칭이_아니다():
    """🔴 별칭은 **표기 차이**지 **낱말 차이**가 아니다.

    SFC 는 `EPひょうじ` 라고 쓴다 — `経験値表示` 가 아니다. 이어 주면 **원문이 다른데
    표기를 맞추는** 꼴이 된다. 그런 자리는 그 게임이 자기 말로 두고 대장에 적는다.
    """
    assert G.diff_labels({"EPひょうじ": "EP 표시"}).unmatched == ["EPひょうじ"]


def test_가나로_쓴_말만_옮긴다():
    """PS1 의 라틴 `SAVE`/`LOAD` 는 원문이 영문이라 이 표에 안 걸린다 — 갈린 게 아니다."""
    assert G.lookup("セーブ", "ui") == "저장"
    assert G.diff_labels({"SAVE": "SAVE"}).unmatched == ["SAVE"]


def test_가나_별칭이_한자_열쇠에_닿는다():
    """SFC 는 `すてる`·`そのた` 처럼 가나로만 든다 — 별칭이 없으면 통째로 안 재진다."""
    out = G.diff_labels({"すてる": "버리기", "そのた": "기타"})
    assert out.diff == [("すてる", "버린다", "버리기")]
    assert out.unmatched == []


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
