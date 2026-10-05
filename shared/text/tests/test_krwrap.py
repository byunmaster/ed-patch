"""krwrap 단위 테스트. 실행: `.venv/bin/python shared/text/tests/test_krwrap.py`
(pytest도 호환: `.venv/bin/python -m pytest shared/text/tests/`)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from text.krwrap import (
    NO_HEAD,
    is_sentence_end,
    split_reason,
    split_sentences,
    text_width,
    wrap,
    wrap_hard,
    wrap_page,
    wrap_pages,
)


def test_basic_greedy():
    # 폭 6전각, 2줄. ⚠ 기대값은 **그리디가 아니라 균형 배분**(`_balance`)의 결과다 —
    # 그리디 `가나다 라마`(5.5)/`바사아`(3)와 비용이 같고(9.25) DP 가 앞쪽 분할을 잡는다.
    # (이 테스트는 `_balance` 도입 후 갱신을 안 해 빨간 채로 방치돼 있었다 — 2026-08-04 정정)
    out = wrap("가나다 라마 바사아", width=6)
    assert out == ["가나다", "라마 바사아"], out


def test_no_midword_break():
    # 어절은 절대 중간에서 안 끊긴다
    out = wrap("에스텔 브라이트가 인사한다", width=5)
    for line in out:
        assert " " not in line or all(
            w in ["에스텔", "브라이트가", "인사한다"] for w in line.split()
        )
    assert "에스텔" in out[0]


def test_strip_after_display():
    # 같은 줄이면 . , 뒤 공백 제거(표시), 하지만 개행은 . 뒤에서 가능
    out = wrap("끝. 다음", width=20, strip_after=".,")
    assert out == ["끝.다음"], out


def test_break_allowed_after_period():
    # 좁으면 . 뒤에서 개행(붙은 토큰 안 생김)
    out = wrap("끝. 다음문장이다", width=4, strip_after=".,")
    assert out[0] == "끝." and out[1].startswith("다음"), out


def test_comma_space_removed_same_line():
    out = wrap("사과, 배, 포도", width=20, strip_after=".,")
    assert out == ["사과,배,포도"], out


def test_bang_question_space_kept():
    # ! ? 뒤 공백은 strip_after에 없으면 유지
    out = wrap("좋아! 가자", width=20, strip_after=".,")
    assert out == ["좋아! 가자"], out


def test_strip_before_punct():
    # 부호 앞 공백 제거: `왕자님 ?`→`왕자님?`, `전해라 !`→`전해라!` (뒤 공백은 유지)
    out = wrap("외출하시옵나이까 왕자님 ?", width=20, strip_before=".,!?", strip_after=".,")
    assert out == ["외출하시옵나이까 왕자님?"], out
    out2 = wrap("본때를 보여주지 ! 어서", width=20, strip_before=".,!?", strip_after=".,")
    assert out2 == ["본때를 보여주지! 어서"], out2


def test_no_head_kinsoku():
    # 닫는 따옴표가 줄 맨 앞에 오지 않게(앞 줄에 붙음)
    out = wrap("그가 말했다 ”라고", width=6, no_head=NO_HEAD)
    for line in out:
        assert line[0] not in NO_HEAD, out


def test_avoid_widow():
    # 마지막 줄이 한 어절(짧은)만 덜렁 남으면 앞 줄에서 하나 내려 회피
    # "가나 다라 마"(폭5.5): 그리디=[가나 다라][마] → 위도우 회피=[가나][다라 마]
    out = wrap("가나 다라 마", width=5.5, avoid_widow=True)
    assert out == ["가나", "다라 마"], out
    # 회피 불가(앞 줄도 한 어절 + 합치면 폭 초과)면 그대로 둔다
    out2 = wrap("가나다라 마바사아 자", width=5, avoid_widow=True)
    assert out2 == ["가나다라", "마바사아", "자"], out2


def test_cell_width_halfwidth():
    # 엔진 슬롯 폭: 공백만 0.5, ASCII 인쇄문자는 전각 승격(인코더)이라 1.0
    assert text_width("AB") == 2.0
    assert text_width("가 나") == 2.5
    assert text_width("왕자님.") == 4.0


def test_wrap_hard_honors_breaks():
    # 원문 줄바꿈(\n)이 폭에 맞으면 그대로 유지
    src = "왕자님, 외출하시옵나이까?\n잘 다녀오십시오."
    out = wrap_hard(src, 14, strip_before=".,!?", strip_after=".,")
    assert out == ["왕자님,외출하시옵나이까?", "잘 다녀오십시오."], out


def test_wrap_hard_reflows_overflow():
    # 폭 넘는 원문 줄만 재줄바꿈, 나머지는 유지
    src = "짧은 줄.\n이것은 폭을 넘기는 아주 긴 한 줄이라 재줄바꿈 되어야 한다"
    out = wrap_hard(src, 10, strip_after=".,")
    assert out[0] == "짧은 줄." and len(out) > 2, out


def test_wrap_hard_merges_fragment():
    # 원문이 어절 중간을 끊어 짧은 조각이 생기면 이웃과 병합
    src = "저희는 슈미님을 섬깁니다. 슈미\n님을 믿으세요."
    out = wrap_hard(src, 14, strip_before=".,!?", strip_after=".,")
    assert all(text_width(ln) > 3 for ln in out), out  # 짧은 조각 없음
    assert "슈미" in "".join(out) and "믿으세요" in out[-1], out


def test_wrap_hard_overflow_cascades_to_next_line():
    # 넘친 줄의 꼬리(문장 미종결)는 다음 원문 줄에 이어 붙는다 — '무엇보다' 고아 방지
    src = "현명한 군주가 되시려면 무엇보다\n독서가 필요하옵나이다."  # 가짜 문장(정발 인용 금지)
    out = wrap_hard(src, 14, strip_before=".,!?")
    # 요지는 `무엇보다`가 홀로 안 남는 것. 줄 배분은 `_balance` 가 고르게 다시 나눈다
    # (이 기대값도 `_balance` 도입 후 갱신 누락이었다 — 2026-08-04 정정).
    assert out == ["현명한 군주가", "되시려면 무엇보다", "독서가 필요하옵나이다."], out
    assert not any(ln == "무엇보다" for ln in out), out


def test_wrap_hard_no_cascade_after_sentence_end():
    # 꼬리가 문장 끝이면 다음 줄로 흘러들지 않는다
    src = "이 줄은 폭을 넘기는 긴 문장으로 끝난다.\n다음 문장이다."
    out = wrap_hard(src, 14, strip_before=".,!?")
    assert out[-1] == "다음 문장이다.", out


def test_pagination():
    pages = wrap_page("가 나 다 라 마 바 사", width=1.5, lines_per_page=3)
    assert all(len(p) <= 3 for p in pages)
    flat = [ln for pg in pages for ln in pg]
    assert flat == ["가", "나", "다", "라", "마", "바", "사"], pages


def test_empty():
    assert wrap("", width=10) == []
    assert wrap("   ", width=10) == []


def test_sentence_end_detection():
    assert is_sentence_end("아무것도 없습니다.")
    assert is_sentence_end("정말인가?!")
    assert is_sentence_end("그럴수가…")
    assert is_sentence_end("「그렇다.」")
    assert not is_sentence_end("창고를 뒤져 봐도")
    assert not is_sentence_end("빼앗겨 버렸는데,")


def test_split_sentences():
    # 공백 기준 + 부호 뒤 공백이 지워진 텍스트(`.`뒤 한글)도 분리
    assert split_sentences("간다. 지금 바로!") == ["간다.", "지금 바로!"]
    assert split_sentences("지하감옥 입니다.왕자님 같은 분께서") == [
        "지하감옥 입니다.",
        "왕자님 같은 분께서",
    ]
    # 소수점·연속 종결부호는 안 나눔
    assert split_sentences("무게는 1.5킬로다.") == ["무게는 1.5킬로다."]
    assert split_sentences("뭐라고?! 정말이냐?") == ["뭐라고?!", "정말이냐?"]


def test_wrap_pages_no_straddle():
    # 짧은 문장 + 3줄짜리 문장: 기계적 3줄 절단이면 두 번째 문장이 창에 걸림 —
    # 문장 packing은 창1=문장1, 창2=문장2로 나눈다
    src = "여기는 낡은 창고입니다.\n창고를 뒤져 봐도 쓸만한 물건은 하나도 남아있지 않습니다."
    pages = wrap_pages(src, 14, 3, strip_before=".,!?", strip_after=".,")
    assert len(pages) == 2, pages
    assert pages[0] == ["여기는 낡은 창고입니다."], pages
    for pg in pages:  # 마지막 아닌 창은 문장 끝으로 끝난다
        assert is_sentence_end(pg[-1]), pages


def test_wrap_pages_oversize_sentence_resplit():
    # {n} 때문에 4줄이 된 두 문장 그룹 → 문장별 재줄바꿈으로 창 걸침 해소
    src = "손님,이곳은 낡은 창고\n입니다.손님 같은 귀하신 분께서 드나들만한 곳이 아닙니다."
    pages = wrap_pages(src, 14, 3, strip_before=".,!?", strip_after=".,")
    for pg in pages[:-1]:
        assert is_sentence_end(pg[-1]), pages


def test_wrap_pages_long_sentence_flows():
    # 창(3줄)을 넘는 외문장은 걸침 불가피 — 창을 채우며 흘러가되 줄 폭은 지킨다
    src = "이것은 창 하나에 도저히 들어갈 수 없을 만큼 길고 긴 문장이라서 여러 창에 걸쳐 흘러가야만 한다."
    pages = wrap_pages(src, 10, 3, strip_after=".,")
    assert len(pages) >= 2, pages
    assert all(len(pg) <= 3 for pg in pages)
    assert all(text_width(ln) <= 10 for pg in pages for ln in pg)


def test_bound_noun_pulled_up():
    # 의존명사는 앞 용언과 붙어야 한다 — `만날` / `수 있을…` 로 갈리면 안 된다
    # (유저 QA 2026-08-04 — 실제 자리도 개행이 `만날 수` 뒤였다)
    # ⚠ 픽스처는 **우리 문장**이다 — 실제 대사를 그대로 적으면 리포에 원작 문안이 남는다.
    pages = wrap_pages("이야, 반갑네. 자네를 다시 만날 수 있을 줄이야...", 14, 6, strip_after="")
    assert pages == [["이야, 반갑네.", "자네를 다시 만날 수", "있을 줄이야..."]], pages


def test_bound_noun_not_pulled_without_adnominal():
    # 앞 줄이 관형형(ㄴ/ㄹ)이 아니면 의존명사가 아니다 — 끌어올리지 않는다
    pages = wrap_pages("가나다라마바사아자차 수요일에 만나자", 12, 6, strip_after="")
    assert pages[0][1].startswith("수요일"), pages


def test_det_orphan_je():
    # 관형사 `제`(=저의)가 줄 끝에 홀로 남으면 수식 대상과 함께 내린다
    pages = wrap_pages(
        "아뇨, 그 상자만은 제 손으로 직접 열어 보겠습니다.", 14, 6, strip_after="", det_orphan=True
    )
    assert all(not pg_ln.endswith(" 제") for pg in pages for pg_ln in pg), pages


def test_속격은_뒤_체언과_한_덩어리다():
    """`용의` / `알을…` 로 갈리면 **무엇의 알인지가 늦게 도착한다**(유저 QA 2026-09-13, `023`).

    실측으로 ps1 문안에 「~의」 어절이 **351종 1,687회**고 거의 전부 속격이다.
    """
    assert split_reason("용의", "알을") == "속격+체언"
    assert split_reason("빛의", "검을") == "속격+체언"
    assert split_reason("길모아의", "무지개를") == "속격+체언"


def test_의로_끝나는_명사_부사는_속격이_아니다():
    """🔴 **꼴로는 못 가른다** — `용의` 와 `거의` 는 글자 구조가 같다.

    그래서 제외 목록으로 판정한다. 코퍼스에 실재하는 비속격은 **`거의` 하나**였고(9회),
    나머지는 **다른 게임 어휘를 위한 예방분**이다 — `shared/` 는 일곱 게임이 쓴다.
    ⚠ 「신의」는 **제외하지 않는다** — 코퍼스 용례가 둘 다 속격이었다(`신의 아이`·`자신의 나라`).
    """
    assert split_reason("거의", "다") is None
    assert split_reason("회의", "중이다") is None
    assert split_reason("신의", "아이일지도") == "속격+체언"


def test_보조용언_목록은_QA_가_증거한_꼴만_넣는다():
    """🔴 **코퍼스 채굴로는 보조용언을 못 고른다**(실측 2026-09-13).

    「활용형 뒤에 오는데 목록에 없는 어절」을 세니 상위에 `왕자님`·`아트라스`·`보물상자`가
    쏟아졌다 — `_is_infinitive` 는 **모음만** 보므로 본용언·명사·고유명사를 못 가른다.
    ⇒ 목록은 닫아 두고 **QA 가 증거한 꼴만** 넣는다. 아래 둘이 그렇게 들어왔다.
    """
    assert split_reason("서", "있던") == "본용언+보조용언"        # 013 「서 있던」
    assert split_reason("묵어", "보자고") == "본용언+보조용언"      # 025 「묵어 보자고」


def test_split_reason_names_the_unit():
    # 판정 정본 — 조판기와 검출기가 같이 쓴다.
    assert split_reason("눈치채지", "못하는") == "-지 못하다/않다"
    assert split_reason("구해", "준") == "본용언+보조용언"
    assert split_reason("좀", "허약하지") == "관형사·부사 고아"
    assert split_reason("미루는", "것이") == "관형형+의존명사"
    # ⚠ 문장 경계는 갈려도 된다(유저 확정 2026-08-10) — 붙여쓸 것이 갈리는 쪽이 더 나쁘다.
    assert split_reason("하옵니다.", "것이") is None


def test_balance_avoids_unit_split():
    # 줄바꿈 지점 선택에서 덩어리 갈림을 피한다 — 어절 하나 옮기기로는 안 되던 자리다.
    out = wrap_pages("그러면, 저희들을 구해 준 이가 자네들인가?", width=14, lines_per_page=3)
    assert not any(
        split_reason(pg[i - 1].split()[-1], pg[i].split()[0])
        for pg in out
        for i in range(1, len(pg))
    ), out


def test_tail_orphan_pull_keeps_units():
    # 마지막 줄 외톨이를 없애려다 **부사 고아를 새로 만들면 안 된다**(전 씬 2건 실측).
    out = wrap_pages("촌장 어서! 병사들은 아직 2층에 있습니다!!", width=14, lines_per_page=3)
    assert out == [["촌장 어서!", "병사들은 아직 2층에", "있습니다!!"]], out


def test_lone_line_merges_down_into_its_sentence():
    # 위도우 방지가 내린 어절이 뒷문장이 붙으면서 **가운데 고아**로 남던 자리
    # (유저 QA 2026-08-31 `으쓱해질` 이 홀로 한 줄). 같은 문장인 뒷줄에 붙인다.
    out = wrap_pages("그러면 나도 어깨가 으쓱해질 게다. 왓핫하.", width=14, lines_per_page=6)
    assert out == [["그러면 나도 어깨가", "으쓱해질 게다. 왓핫하."]], out


def test_lone_line_merges_up_when_down_does_not_fit():
    # 아래로 붙이면 폭을 넘는다(`보물창고에`+`무슨 볼일이시옵니까?` = 15.5) → 위로 올린다.
    out = wrap_pages("어라 왕자님. 보물창고에 무슨 볼일이시옵니까?", width=14, lines_per_page=3)
    assert out == [["어라 왕자님. 보물창고에", "무슨 볼일이시옵니까?"]], out


def test_lone_line_kept_when_sentence_ends():
    # ⚠ 문장 종결로 끝나는 홀로 줄은 **의도한 토막**이다 — 건드리면 안 된다.
    out = wrap_pages("마스쿤을… 마을을… 구해 주시오!", width=14, lines_per_page=3)
    assert out == [["마스쿤을…", "마을을…", "구해 주시오!"]], out


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"  ok  {fn.__name__}")
        except AssertionError as e:
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERR  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
    return passed == len(fns)


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
