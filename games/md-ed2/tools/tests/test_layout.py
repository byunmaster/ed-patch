"""layout.py (규칙 2-16) — 지표 정의와 절째 내리기."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import layout


def test_bkind():
    assert layout.bkind("있습니다.") == 3
    assert layout.bkind("왕자님,") == 2
    assert layout.bkind("오,") == 0  # 두 음절 이하 쉼표는 경계 아님
    assert layout.bkind("그리고") == 0  # 문장 머리 접속어
    assert layout.bkind("버려서", "주세요") == 0 or layout.bkind("버려서", "주세요") == 1


def test_hand_newlines():
    assert layout.hand_newlines("이야기할\n수 있는") == 1
    assert layout.hand_newlines("끝났다.\n다음") == 0


def test_clause_pushdown():
    pg = ["젊은 병사들이 에메를", "복구하러 가 있어서 성", "안 경비가 허술해져 있습니다."]
    assert layout.clause_violations(pg)
    assert layout.fix_clauses(pg)[1:] == ["복구하러 가 있어서", "성 안 경비가 허술해져 있습니다."]


def test_wrap_keeps_width_and_pages():
    t = "젊은 병사들이 에메를 복구하러 가 있어서 성 안 경비가 허술해져 있습니다."
    pages = layout.wrap_pages(t, width=17.5, lines_per_page=3)
    assert all(layout.tw(ln) <= 17.5 for pg in pages for ln in pg)
    assert "".join(ln for pg in pages for ln in pg).replace(" ", "") == t.replace(" ", "")


def test_balance_last_window():
    pages = [["가나다 라마바", "사아자 차카타,", "파하 거너더 러머"], ["버머."]]
    out = layout.balance_pages(pages)
    assert [len(p) for p in out] == [2, 2]
    assert layout._squash(out) == layout._squash(pages)
    # 문장 끝이던 쪽 경계는 3+1 이어도 문장 중간으로 옮기지 않는다
    keep = [["가나다 라마바", "사아자 차카타,", "파하 거너더 러머."], ["버머."]]
    assert layout.balance_pages(keep) == keep


def test_short_sentence_one_line():
    # 한 줄에 드는 문장이 두 줄에 걸치면(2-10) 새 줄에서 시작해 한 줄에 둔다 — 글·줄 수는 그대로
    pg = ["네, 여기", "있습니다. 감사합니다."]
    assert layout.short_sentences(pg) == [(0, 0, 1, 0)]
    assert layout.fix_sentences(pg) == ["네, 여기 있습니다.", "감사합니다."]
    # 앞 문장 꼬리가 줄 머리에 있으면 그 줄에 남기고 문장만 새 줄로
    pg = ["들었다. 한시라도 빨리 황제를", "찾아내라. 우리도 곧 쫓겠다."]
    assert layout.fix_sentences(pg) == ["들었다.", "한시라도 빨리 황제를 찾아내라.", "우리도 곧 쫓겠다."]
    # 한 줄 폭을 넘는 문장은 그대로, 변수 자리가 낀 문장도 그대로
    long = ["가나다 라마바 사아자 차카타 파하", "거너더 러머버."]
    assert layout.short_sentences(long) == [] and layout.fix_sentences(long) == long
    var = ["§ 네, 여기", "있습니다."]
    assert layout.short_sentences(var) == []
    # 쪽 수·줄 수 제한: 3줄 쪽이 4줄이 되는 고침은 안 한다
    full = ["네, 여기", "있습니다. 감사합니다. 안녕히", "가세요 어서 가십시오 잘 가요."]
    assert len(layout.fix_sentences(full)) <= layout.LINES
