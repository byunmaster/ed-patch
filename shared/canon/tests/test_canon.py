#!/usr/bin/env python3
"""공통 문안 정본의 회귀 — 가짜 데이터로 잰다(원문 문장을 테스트에 옮기지 않는다)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "shared"))

import canon
import glossary as G

FAKE = {
    "_pending": {"ui": {"カウ": ["사기", "삽니다"]}},
    "categories": {
        "ui": {"ソノタ": "기타", "カウ": "사기"},
        "speaker": {"ヘイシ": "병사"},
        "system": {"{item}ヲテニイレタ。": "{item}을(를) 얻었다."},
        "battle": {"をモッテイタ。": "을(를) 가지고 있었다."},
    },
}


def _with_fake(fn):
    canon._CACHE["fake"] = FAKE
    try:
        return fn()
    finally:
        canon._CACHE.pop("fake", None)


def test_files_exist_and_split_by_title():
    for t in canon.TITLES:
        assert set(canon.categories(t)) >= {"ui", "speaker", "system", "battle"}, t


def test_glossary_holds_proper_nouns_only():
    """🔴 사전은 고유명사만(마스터 10-08) — ui·화자 호칭은 정본으로 옮겼다."""
    raw = canon.nouns("eiyuu")
    assert "ui" not in raw["categories"]
    assert "_speaker_only" not in raw
    assert "兵士" not in raw["categories"]["person"]


def test_bridge_keeps_old_callers_working():
    """임시 다리 — 2단계 전환 전까지 `glossary.lookup(…, "ui")` 이 정본을 돌려준다."""
    assert G.lookup("その他", "ui") == canon.lookup("その他", "ui", "ed1")
    assert G.lookup("兵士", "person") == canon.lookup("兵士", "speaker", "ed1")


def test_phrase_matches_whole_line_with_folded_josa():
    def run():
        pairs = [
            ("a", "ヤクソウヲテニイレタ。", "약초를 얻었다.", "dialog"),  # 접힌 조사 — 통과
            ("b", "ヤクソウヲテニイレタ。", "약초를 주웠다.", "dialog"),  # 다른 말 — 어긋남
            (
                "c",
                "カレハヤクソウヲテニイレタ。ソシテ…",
                "그는 약초를 얻었다. 그리고…",
                "dialog",
            ),  # 문장 속 — 안 잰다
            (
                "d",
                "スライムをモッテイタ。",
                "슬라임을(를) 가지고 있었다.",
                "dialog",
            ),  # 이름 뒤 조각
        ]
        return canon.audit(pairs, "fake")

    r = _with_fake(run)
    assert [h.where for h in r.hits] == ["a", "b", "d"]
    assert [h.where for h in r.mismatches] == ["b"]


def test_labels_whole_slot_and_speaker_whole_line():
    def run():
        pairs = [
            ("m1", "ソノタ", "그외", "slot"),  # 라벨 어긋남
            ("s1", "ヘイシ", "병사", "slot"),  # 화자 칸 — 일치
            ("d1", "ヘイシガキタ", "병졸이 왔다", "dialog"),  # 대사 속 보통명사 — 안 잰다
            ("p1", "カウ", "삽니다", "slot"),  # 판정 대기 — 실패 아님
        ]
        return canon.audit(pairs, "fake")

    r = _with_fake(run)
    assert [h.where for h in r.mismatches] == ["m1"]
    assert "d1" not in [h.where for h in r.hits]
    assert "p1" in [h.where for h in r.pending]


def test_one_entry_holds_proper_nouns_too():
    """🔴 게임은 정본 하나만 본다(마스터 10-08) — 고유명사도 `canon` 에서 나온다. ED1·ED2 는 한 벌을 같이 쓴다."""
    assert canon.lookup("ルディア", "place", "ed1") == canon.lookup("ルディア", "place", "ed2") == "루디아"
    assert canon.lookup("カース", "item", "ed1") != canon.lookup("カース", "monster", "ed1")
    assert {"person", "place", "item", "monster", "ui", "speaker"} <= set(canon.categories("ed2"))
    assert canon.nouns("ed1") is canon.nouns("ed2")
    assert canon.lookup("セーブ", "ui", "ed3") == "세이브"  # PS1 ED3 원문(마스터 10-08)


def test_old_glossary_entry_is_only_a_bridge():
    """옛 `glossary` 는 데이터를 안 든다 — 같은 파일을 읽는다(한 라운드 다리)."""
    assert G.load("eiyuu") is canon.nouns("eiyuu")
    assert G.lookup("ルディア", "place") == canon.lookup("ルディア", "place", "ed1")


def test_number_slot_takes_digits_only():
    """`{n}` 자리는 숫자만 — 낱말이 수 자리에 들어가 걸리면 오탐이다(md 실측 10-08)."""

    def run():
        fake = {"categories": {"battle": {"{n}ポイントサガッタ。": "{n} 포인트 내려갔다."}}}
        canon._CACHE["fake2"] = fake
        try:
            return canon.audit(
                [("a", "12ポイントサガッタ。", "12 포인트 내려갔다.", "dialog"),
                 ("b", "ゼンブポイントサガッタ。", "전부 내려갔다.", "dialog")],
                "fake2",
            )
        finally:
            canon._CACHE.pop("fake2", None)

    r = run()
    assert [h.where for h in r.hits] == ["a"]


def test_slot_form_phrase_is_accepted():
    """정본 문구의 칸 꼴(`원문@자리`)도 정답 — 칸이 모자란 기종이 마스터 확인 값을 쓴다(10-08)."""
    fake = {"categories": {"battle": {"ヤクソウヲテニイレタ。": "약초를 손에 넣었다.", "ヤクソウヲテニイレタ。@md칸": "약초 얻었다."}}}
    canon._CACHE["fake3"] = fake
    try:
        r = canon.audit([("a", "ヤクソウヲテニイレタ。", "약초 얻었다.", "dialog")], "fake3")
    finally:
        canon._CACHE.pop("fake3", None)
    assert [h.where for h in r.hits] == ["a"] and not r.mismatches


# ⚠ 새 테스트는 이 줄 위에.
if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for f in fns:
        try:
            f()
        except Exception as e:  # noqa: BLE001 — 러너가 실패를 모아 센다
            bad += 1
            print(f"  FAIL {f.__name__}: {e!r}")
    print(f"{len(fns) - bad}/{len(fns)} passed")
    sys.exit(1 if bad else 0)
