"""알선소 의뢰 게시판 행 수 게이트 — 116건의 요약·본문 줄이 상세 창 폭(16열 192px)을 넘어 글자 단위로 접히지 않는가.

넘으면 엔진이 줄을 두 행으로 접어 보상 줄을 덮거나 다음 쪽으로 밀어낸다(11-06 실측). 낱말을 줄여야만 드는 의뢰는 마스터 판정 전이라
`board_rows_baseline.json` 에 목록으로 둔다 — **목록에 없는 의뢰가 새로 넘치거나 목록 의뢰가 늘면 실패**(래칫), 판정으로 줄면 `--freeze`.
    python3 tools/check_board_rows.py [--freeze] [--list]
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board_text as B
import common

BASELINE = os.path.join(common.ROOT, "board_rows_baseline.json")


VERB_END = ("다", "요", "오", "까", ".", "!", "?")


def summary_form(board):
    """요약 줄(주황)은 명사형으로 끝나야 한다(마스터 11-06) — 동사·서술 종결(다·요·마침표…)이면 위반."""
    bad = []
    for q, a1, a2, _b in board.quests():
        t = board.texts(a1, a2)[0]
        if t.endswith(VERB_END):
            bad.append((q, t))
    return bad


def main():
    board = B.Board()
    form = summary_form(board)
    for q, t in form:
        print(f"  🔴 요약이 명사형이 아님 — 의뢰 {q}: 「{t}」")
    if form:
        return 1
    bad = B.violations(board)
    qs = sorted({q for q, _w in bad})
    total = len(board.quests())
    if "--freeze" in sys.argv:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump({"limit_px": B.LIMIT, "quests": qs}, f, indent=1)
            f.write("\n")
        print(f"기준선을 {len(qs)}건으로 박았다")
        return 0
    with open(BASELINE, encoding="utf-8") as f:
        base = set(json.load(f)["quests"])
    new = [q for q in qs if q not in base]
    print(
        f"게시판 의뢰문 줄 폭 — 의뢰 {total}건 중 폭({B.LIMIT}px)을 넘는 것 {len(qs)} · 마스터 판정 대기(기준선) {len(base)}"
        + (f" · 🔴 새로 넘침 {len(new)}" if new else "")
    )
    if "--list" in sys.argv or new:
        for q, w in bad:
            print(f"  {'🔴 ' if q in new else '· '}의뢰 {q}: {w}")
    if len(qs) < len(base) and not new:
        print("  ↓ 줄었다 — `--freeze` 로 기준선을 내린다(래칫)")
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
