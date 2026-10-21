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
            ("d1", "ヘイシガヤッテキタ", "병졸이 왔다", "dialog"),  # 대사 속 보통명사 — 안 잰다
            ("p1", "カウ", "삽니다", "slot"),  # 판정 대기 — 실패 아님
        ]
        return canon.audit(pairs, "fake")

    r = _with_fake(run)
    assert [h.where for h in r.mismatches] == ["m1"]
    assert "d1" not in [h.where for h in r.hits]
    assert "p1" in [h.where for h in r.pending]


def test_one_entry_holds_proper_nouns_too():
    """🔴 게임은 정본 하나만 본다(마스터 10-08) — 고유명사도 `canon` 에서 나온다. ED1·ED2 는 한 벌을 같이 쓴다."""
    assert (
        canon.lookup("ルディア", "place", "ed1")
        == canon.lookup("ルディア", "place", "ed2")
        == "루디아"
    )
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
                [
                    ("a", "12ポイントサガッタ。", "12 포인트 내려갔다.", "dialog"),
                    ("b", "ゼンブポイントサガッタ。", "전부 내려갔다.", "dialog"),
                ],
                "fake2",
            )
        finally:
            canon._CACHE.pop("fake2", None)

    r = run()
    assert [h.where for h in r.hits] == ["a"]


def test_slot_form_phrase_is_accepted():
    """정본 문구의 칸 꼴(`원문@자리`)도 정답 — 칸이 모자란 기종이 마스터 확인 값을 쓴다(10-08)."""
    fake = {
        "categories": {
            "battle": {
                "ヤクソウヲテニイレタ。": "약초를 손에 넣었다.",
                "ヤクソウヲテニイレタ。@md칸": "약초 얻었다.",
            }
        }
    }
    canon._CACHE["fake3"] = fake
    try:
        r = canon.audit([("a", "ヤクソウヲテニイレタ。", "약초 얻었다.", "dialog")], "fake3")
    finally:
        canon._CACHE.pop("fake3", None)
    assert [h.where for h in r.hits] == ["a"] and not r.mismatches


def test_name_slot_is_name_shaped():
    """이름 자리는 이름처럼 생긴 것만 — 앞 대사 한 문장을 통째로 삼켜 다른 줄에 걸리면 오탐이다(ss 실측 10-09)."""
    fake = {"categories": {"battle": {"{name}⏎コノカベハヤブレン。": "{name}⏎이 벽은 못 깬다."}}}
    canon._CACHE["fake4"] = fake
    try:
        r = canon.audit(
            [
                ("a", "ダレカ⏎コノカベハヤブレン。", "누군가⏎이 벽은 못 깬다.", "dialog"),
                (
                    "b",
                    "ナガイセリフダ。ソシテ⏎コノカベハヤブレン。",
                    "긴 대사다. 그리고⏎이 벽은 단단하다.",
                    "dialog",
                ),
            ],
            "fake4",
        )
    finally:
        canon._CACHE.pop("fake4", None)
    assert [h.where for h in r.hits] == ["a"] and not r.mismatches


def test_chapter_card_inside_block_is_measured():
    """블록 속 장 카드 「第N章 제목」 도 잰다 — 제목은 정본 값, 번호는 전각(번역 규칙 1-4, 10-10·10-11)."""
    fake = {"categories": {"chapter": {"タビダチ": "여행"}}}
    canon._CACHE["fake5"] = fake
    try:
        r = canon.audit(
            [
                ("ok", "第１章  タビダチ\n\n完", "제１장  여행\n\n끝", "dialog"),
                ("half", "第１章  タビダチ\n\n完", "제1장  여행\n\n끝", "dialog"),
                ("title", "第２章  タビダチ\n\n完", "제２장  여행길\n\n끝", "dialog"),
                ("other", "第３章  ナゾ\n\n完", "제３장  수수께끼\n\n끝", "dialog"),
            ],
            "fake5",
        )
    finally:
        canon._CACHE.pop("fake5", None)
    assert sorted(h.where for h in r.hits) == ["half", "ok", "title"]
    assert sorted(h.where for h in r.mismatches) == ["half", "title"]


def test_number_slot_accepts_format_code():
    """수 자리(`{n}`)는 서식 코드 `%d` 도 받는다 — 새턴 원문은 숫자 대신 `%d` 를 들고 있다(ss-ed1+2 실측 10-11)."""
    fake = {"categories": {"system": {"{n}ポイントフヤセマス。": "{n}포인트 늘릴 수 있습니다."}}}
    canon._CACHE["fake6"] = fake
    try:
        r = canon.audit(
            [("a", "%dポイントフヤセマス。", "%d포인트 늘릴 수 있습니다.", "dialog")], "fake6"
        )
    finally:
        canon._CACHE.pop("fake6", None)
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


def test_prefix_josa_folds_both_ways():
    """앞 병기 「(이)라고」 — 병기 그대로도, 받침대로 접은 꼴(「이라고」·「라고」)도 정본이다(ss-ed1+2 qa g072, 10-19)."""
    import re

    pat = canon._kr_pattern("{name}(이)라고 불렀다.")
    for ok in ("가나(이)라고 불렀다.", "가난이라고 불렀다.", "가나라고 불렀다."):
        assert re.fullmatch(pat, ok), ok
    assert not re.fullmatch(pat, "가나이고 불렀다.")


def test_trailing_period_difference_is_same_source():
    """원문 줄 끝 부호가 열쇠와 달라도 같은 원문 — 끝 「。」 하나 차이로 정본 검사가 줄을 놓쳤다(md-ed2 10-21)."""
    fake = {"categories": {"battle": {"はトオボエヲシテイル": "은(는) 길게 울부짖는다."}}}
    canon._CACHE["fake_end"] = fake
    try:
        r = canon.audit(
            [
                ("a", "イヌはトオボエヲシテイル。", "개는 멀리서 울부짖는다.", "dialog"),
                ("b", "イヌはトオボエヲシテイル", "개는 길게 울부짖는다.", "dialog"),
            ],
            "fake_end",
        )
    finally:
        canon._CACHE.pop("fake_end", None)
    assert [h.where for h in r.hits] == ["a", "b"]
    assert [h.where for h in r.mismatches] == ["a"]


def test_keys_differing_only_by_end_mark_stay_apart():
    """끝 부호만 다른 열쇠가 둘이면 값이 다르다 — 부호 있는 열쇠는 부호까지 맞아야 잡는다(pce-ed1 10-21)."""
    fake = {
        "categories": {
            "battle": {
                "{name}トモ{name}ガヤッテキタ!!": "{name}과(와) {name}들이 왔다!!",
                "{name}トモ{name}ガヤッテキタ": "{name}과(와) {name}이(가) 왔다.",
            }
        }
    }
    canon._CACHE["fake_end2"] = fake
    try:
        r = canon.audit(
            [
                ("a", "ネコトモイヌガヤッテキタ!!", "고양이와 개들이 왔다!!", "dialog"),
                ("b", "ネコトモイヌガヤッテキタ。", "고양이와 개가 왔다.", "dialog"),
                ("c", "ネコトモイヌガヤッテキタ！", "고양이와 개가 왔다!", "dialog"),
            ],
            "fake_end2",
        )
    finally:
        canon._CACHE.pop("fake_end2", None)
    assert sorted(h.where for h in r.hits) == ["a", "b", "c"]
    assert not r.mismatches


def test_clause_fragment_key_does_not_take_full_sentence():
    """값이 관형절 조각이면(문장 끝 부호 없음) 끝 부호 접힘을 안 한다 — 완결문은 다른 열쇠 몫(md-ed1 10-21)."""
    fake = {
        "categories": {
            "battle": {
                "{name}ニサワッタ": "{name}에 닿은",
                "ニサワッタ。": "을(를) 만졌다.",
            }
        }
    }
    canon._CACHE["fake_frag"] = fake
    try:
        r = canon.audit(
            [("a", "ネコはイヌニサワッタ。", "고양이는 개를 만졌다.", "dialog")], "fake_frag"
        )
    finally:
        canon._CACHE.pop("fake_frag", None)
    assert not r.mismatches, [(h.where, h.jp) for h in r.mismatches]


def test_punctuated_key_needs_punctuated_line():
    """부호로 끝나는 열쇠는 부호 없는 머리 조각 줄에 안 건다(ps1-ed1+2 10-21)."""
    fake = {"categories": {"battle": {"にサワッタ。": "을(를) 만졌다."}}}
    canon._CACHE["fake_head"] = fake
    try:
        r = canon.audit(
            [
                ("a", "ホノオにサワッタ", "불꽃에 닿은 ", "dialog"),
                ("b", "ネコはイヌにサワッタ．", "고양이는 개를 만졌다.", "dialog"),
            ],
            "fake_head",
        )
    finally:
        canon._CACHE.pop("fake_head", None)
    assert [h.where for h in r.hits] == ["b"] and not r.mismatches


def test_end_mark_family_must_match():
    """마침 열쇠는 느낌표 줄에 안 건다 — 「は助けを呼んだ！」가 「を呼んだ。」에 걸렸다(pce-ed1 10-21)."""
    fake = {"categories": {"battle": {"をヨンダ。": "을(를) 불렀다."}}}
    canon._CACHE["fake_fam"] = fake
    try:
        r = canon.audit(
            [
                ("a", "ネコはタスケをヨンダ！", "고양이는 도움을 청했다!", "dialog"),
                ("b", "ネコはイヌをヨンダ.", "고양이는 개를 불렀다.", "dialog"),
            ],
            "fake_fam",
        )
    finally:
        canon._CACHE.pop("fake_fam", None)
    assert [h.where for h in r.hits] == ["b"] and not r.mismatches


def test_unpunctuated_tail_is_measured_head_is_not():
    """원문이 끝 부호를 생략한 완결 꼬리는 재고, 머리 조각은 건너뛴다 — 우리 줄 끝으로 가른다(sfc-ed2 10-21)."""
    fake = {"categories": {"battle": {"をツカッタ。": "을(를) 사용했다."}}}
    canon._CACHE["fake_tail"] = fake
    try:
        r = canon.audit(
            [
                ("tail", "ネコはクスリをツカッタ", "고양이는 약을 사용했다.", "dialog"),
                ("head", "ネコはクスリをツカッタ", "고양이가 약을 사용한 ", "dialog"),
            ],
            "fake_tail",
        )
    finally:
        canon._CACHE.pop("fake_tail", None)
    assert [h.where for h in r.hits] == ["tail"] and not r.mismatches


def test_landing_marker_is_not_text():
    """도착점 표지 `<@>`(md-ed2)는 비교에서 뺀다 — 표지가 든 줄이 정본 출현에서 빠졌다(10-21)."""
    fake = {"categories": {"battle": {"をツカッタ。": "을(를) 사용했다."}}}
    canon._CACHE["fake_mark"] = fake
    try:
        r = canon.audit(
            [("a", "ネコはクスリをツカッタ。", "고양이는 약을<@> 사용했다.", "dialog")], "fake_mark"
        )
    finally:
        canon._CACHE.pop("fake_mark", None)
    assert [h.where for h in r.hits] == ["a"] and not r.mismatches
