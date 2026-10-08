#!/usr/bin/env python3
"""이름 검사의 회귀 — 가짜 사전·가짜 문장으로 잣대만 본다(원문 인용 금지)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from canon.names import audit, find

FAKE = {
    "categories": {
        "item": {"ホムラノケン": "불의 검", "カース": "커스", "笛": "피리"},
        "monster": {"カース": "카스"},
        "place": {"ポルト": "포르토", "ポルト城": "포르토성", "ナギサ島": "나기사섬"},
        "ui": {"強さ@전투커맨드": "강함"},
    },
    "_aliases": {"ほむらのけん": "ホムラノケン"},
    "_pending": {"_doc": "", "place": {"ナギサ島": "세션 제안"}},
}


def test_source_must_match():
    """원문에 사전 이름이 없으면 재지 않는다 — 기종마다 원문이 다르면 사전을 들이밀지 않는다."""
    r = audit([("a", "ニギル島へ行く", "니길섬으로 간다")], data=FAKE)
    assert r.hits == [] and r.translated == 1


def test_old_form_is_caught():
    r = audit([("a", "ホムラノケンに触れた", "불꽃의 검에 닿은")], data=FAKE)
    assert [h.jp for h in r.mismatches] == ["ホムラノケン"]


def test_kana_spelling_reaches_through_alias():
    """같은 말의 다른 표기는 같은 원문이다 — 별칭으로 잇는다(마스터 2026-10-07)."""
    r = audit([("a", "ほむらのけんに触れた", "불꽃의 검에 닿은")], data=FAKE)
    assert len(r.mismatches) == 1
    r = audit([("a", "ほむらのけんに触れた", "불의 검에 닿은")], data=FAKE)
    assert r.hits and not r.mismatches


def test_longest_match_wins():
    """`ポルト城` 안의 `ポルト` 를 따로 세지 않는다."""
    s = "ポルト城とポルト"
    keys = {"ポルト": 0, "ポルト城": 0}
    assert [k for _, k in find(s, keys)] == ["ポルト城", "ポルト"]


def test_spacing_is_ignored_and_either_category_reading_accepted():
    r = audit(
        [
            ("a", "ナギサ島だ", "나기사 섬이다"),
            ("b", "カースだ", "카스다"),
            ("c", "カースだ", "커스다"),
        ],
        data=FAKE,
    )
    assert not r.mismatches
    assert [h.where for h in r.pending] == ["a"]


def test_untranslated_counts_in_denominator_only():
    r = audit([("a", "ポルトへ", None), ("b", "ポルトへ", "포르토로")], data=FAKE)
    assert (r.units, r.translated, len(r.hits)) == (2, 1, 1)


def test_short_and_site_keys_are_counted_as_skipped():
    r = audit([("a", "笛を吹く", "피리를 분다")], data=FAKE)
    assert r.hits == [] and r.skipped_keys == 2


def test_katakana_key_is_not_found_inside_another_word():
    """가타카나 열쇠는 다른 가타카나 낱말 속에서 안 잡는다(pce 실측 — 파티원 이름이 몬스터 이름 속에서)."""
    keys = {"ロー": 0, "ポルト城": 0}
    assert find("キャリオンクローラーだ", keys) == []
    assert find("ｷｬﾘｵﾝｸﾛｰﾗｰだ", {"ﾛｰ": 0}) == []  # 반각(sfc)
    assert [k for _, k in find("ローが来た", keys)] == ["ロー"]
    assert [k for _, k in find("ロー・ポルト城", keys)] == ["ロー", "ポルト城"]


def test_bare_name_without_suffix_is_measured():
    """사전엔 `…Ａ` 꼴만 있어도 문장 속 맨 이름을 잰다."""
    data = {"categories": {"monster": {"ゴブリンＡ": "고블린 A"}}}
    r = audit(
        [("a", "ゴブリンが現れた", "고블린이 나타났다"), ("b", "ゴブリンだ", "도깨비다")], data=data
    )
    assert [h.where for h in r.mismatches] == ["b"]


def test_label_counts_only_between_separators():
    """라벨은 앞뒤가 글자가 아닐 때만 — 문장 속은 아니고, 나열 속은 맞다(md 실측 둘)."""
    data = {"categories": {"ui": {"守る": "방어"}}}
    r = audit(
        [
            ("a", "国を守る", "나라를 지킨다"),
            ("b", "守る", "지키기"),
            ("c", "攻撃・守る・逃げる", "공격・지키기・도망"),
            ("d", "攻撃、守るの２つ", "공격, 지키기 2개"),
        ],
        data=data,
    )
    assert [h.where for h in r.mismatches] == ["b", "c", "d"]


def test_speaker_only_counts_as_whole_line():
    """역할 보통명사는 화자 이름 칸(줄 전체)에서만 — 대사 속 「아이」는 그 NPC 가 아니다."""
    data = {
        "categories": {"person": {"子ども": "아이"}},
        "_speaker_only": {"keys": ["子ども"]},
    }
    r = audit([("a", "子どもが泣く", "애가 운다"), ("b", "子ども", "꼬마")], data=data)
    assert [h.where for h in r.mismatches] == ["b"]


def test_line_break_inside_name_is_ignored():
    data = {"categories": {"monster": {"赤スライム": "붉은슬라임"}}}
    r = audit([("a", "赤\nスライムだ", "붉은\n슬라임이다")], data=data)
    assert r.hits and not r.mismatches


def test_label_followed_by_word_is_not_a_label():
    """대사 속 감탄사·접속사(はいどうぞ·そのため)는 라벨이 아니다 — 조사 한 글자 + 구분자만 받는다."""
    data = {"categories": {"ui": {"はい": "예", "すばやさ": "민첩성"}}}
    r = audit(
        [
            ("a", "はい どうぞ。", "자, 여기."),
            ("b", "防御力、すばやさの４つ", "방어력, 민첩의 4개"),
            ("c", "はい", "네"),
        ],
        data=data,
    )
    assert [h.where for h in r.mismatches] == ["b", "c"]


def test_spaced_key_still_matches():
    data = {"categories": {"person": {"やさしい おばば": "다정한 할멈"}}}
    r = audit([("a", "やさしい おばば", "상냥한 할멈")], data=data)
    assert [h.where for h in r.mismatches] == ["a"]


def test_hiragana_alias_does_not_cross_line_break():
    """가나 별칭은 줄바꿈·전각 공백을 못 넘는다 — `けっして　したごころ` 가 `てした` 로 잡혔다(sfc 10-08)."""
    data = {"categories": {"person": {"手下": "부하"}}, "_aliases": {"てした": "手下"}}
    r = audit(
        [
            ("a", "けっして\nしたごころ", "결코 딴마음"),
            ("b", "けっして\u3000したごころ", "결코 딴마음"),
        ],
        data=data,
    )
    assert r.hits == []


def test_speaker_alias_inside_longer_name_is_not_a_speaker():
    """별칭으로 들어온 화자 호칭도 줄 전체일 때만 — `だいとうぞくゲイル` 속 `とうぞく`(sfc 10-08)."""
    data = {
        "categories": {"speaker": {"盗賊": "도둑"}},
        "_aliases": {"とうぞく": "盗賊"},
        "_speaker_only": {"keys": ["盗賊"]},
    }
    r = audit([("a", "だいとうぞくゲイル", "대도 게일"), ("b", "とうぞく", "도둑")], data=data)
    assert [h.where for h in r.hits] == ["b"]


def test_digit_width_is_ignored():
    data = {"categories": {"place": {"２階": "２층"}}}
    r = audit([("a", "２階へ", "2층으로")], data=data)
    assert r.hits and not r.mismatches


def test_dialog_place_form():
    """대사 꼴(마스터 09-27): 성·섬은 붙이고, 「~의」 뒤와 나머지 종류 말 앞은 띄운다."""
    from canon.names import dialog_place

    assert dialog_place("크루즈마을") == "크루즈 마을"
    assert dialog_place("사피아의호수") == "사피아의 호수"
    assert dialog_place("루디아성") == "루디아성"
    assert dialog_place("해적섬") == "해적섬"
    assert dialog_place("엘아스타") == "엘아스타"
    assert dialog_place("지하통로") == "지하 통로"


def test_dialog_place_spacing_is_checked_only_in_dialog():
    """대사 속 지명은 띄어쓰기까지 — 칸(slot)은 띄어쓰기를 무시한다(마스터 10-07 「대사·비대사를 나눠라」)."""
    data = {"categories": {"place": {"ポルトの村": "포르토마을"}}}
    r = audit(
        [
            ("a", "ポルトの村へ", "포르토 마을로", "dialog"),
            ("b", "ポルトの村へ", "포르토마을로", "dialog"),
            ("c", "ポルトの村", "포르토마을", "slot"),
            ("d", "ポルトの村", "포르토　마을", "slot"),
            ("e", "ポルトの村へ", "포르토\n마을로", "dialog"),
            ("f", "ポルトの村へ", "포르토마을로"),
        ],
        data=data,
    )
    assert [h.where for h in r.mismatches] == ["b"]
    assert r.unlabeled == 1


def test_mayor_title_is_not_a_place():
    """「~の町長」은 직함 — 지명 「~の町」으로 재지 않는다."""
    data = {"categories": {"place": {"ポルトの町": "포르토마을"}}}
    r = audit([("a", "ポルトの町長だ", "포르토의 시장이다", "dialog")], data=data)
    assert r.hits == []


def test_dialog_as_is_keeps_single_word():
    """`_dialog_as_is` 열쇠는 대사에서도 칸 꼴 그대로(천의실 — 마스터 10-07)."""
    data = {
        "categories": {"place": {"テンギシツ": "천의실"}},
        "_dialog_as_is": {"keys": ["テンギシツ"]},
    }
    r = audit([("a", "テンギシツへ", "천의실로", "dialog")], data=data)
    assert r.hits and not r.mismatches


def test_labels_are_not_measured_in_dialog():
    """대사 속 はい 는 대답 — 라벨은 칸에서만 잰다(마스터 10-07)."""
    data = {"categories": {"ui": {"はい": "예"}}}
    r = audit([("a", "はい", "네", "dialog"), ("b", "はい", "네", "slot")], data=data)
    assert [h.where for h in r.mismatches] == ["b"]


def test_numbered_key_followed_by_counter_is_not_a_name():
    data = {"categories": {"item": {"その１": "제１"}}}
    r = audit(
        [("a", "その１本しか", "그 한 가닥밖에", "dialog"), ("b", "その１", "그1", "dialog")],
        data=data,
    )
    assert [h.where for h in r.mismatches] == ["b"]


def test_no_check_keys_are_skipped():
    """일반 낱말에 묻히는 짧은 이름은 사전이 `_no_check` 로 빼 둔다."""
    data = dict(FAKE, _no_check=["ポルト"])
    r = audit([("a", "ポルトへ", "항구로")], data=data)
    assert r.hits == [] and r.skipped_keys == 3


def test_ed3_dictionary_is_sound():
    """ED3 정본 — 우리 표기에 일본어가 남지 않고, 확인 대기 열쇠는 본표에 있다."""
    import re

    from canon import nouns as load

    d = load("ed3")
    for cat, tbl in d["categories"].items():
        for jp, kr in tbl.items():
            assert kr.strip() and not re.search(r"[ぁ-んァ-ヶ一-龯]", kr), f"{cat}:{jp} → {kr!r}"
    for cat, tbl in d["_pending"].items():
        if not cat.startswith("_"):
            assert all(jp in d["categories"][cat] for jp in tbl), cat



def test_slot_form_is_accepted_only_in_slots():
    """`원문@자리` 칸 꼴은 칸(slot)에서만 정답이다 — 대사엔 칸이 없다(마스터 10-08)."""
    data = {"categories": {"item": {"テストの杖": "테스트의 지팡이", "テストの杖@아이템칸": "테스트 지팡이"}}}
    r = audit([("s", "テストの杖", "테스트 지팡이", "slot")], data=data)
    assert not r.mismatches
    r = audit([("d", "テストの杖をもらった", "테스트 지팡이를 받았다", "dialog")], data=data)
    assert len(r.mismatches) == 1

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
