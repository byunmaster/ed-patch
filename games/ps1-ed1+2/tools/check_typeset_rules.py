#!/usr/bin/env python3
"""**조판 여섯 규칙** 중 화면 모양 넷(①~④)을 **씬 대사 전량**에 대고 센다(2026-09-27, 마스터 — 전 기종 공통 기반).

① 고아 부호 — 부호만 남은 줄(`.`·`!!`·`…` 등)
② 빈 줄 — 창 안의 `\\n\\n`(의도된 장 카드 여백은 따로 센다)
③ 줄 첫 칸 공백 — 개행 뒤 공백 1~2칸으로 시작하는 줄(3칸 이상은 가운데 정렬로 보고 뺀다)
④ 창 폭 초과 — 29열(반각)을 넘는 줄 = 엔진이 런타임에 **글자 단위로** 다시 꺾는다(어절·묶음 절단)

⑤(반각 0.5칸 계산)·⑥(조사 훅)은 장치가 따로 있다 — `krwrap` 폭 계산 · `patch_josa_hook`(selftest).
시스템·전투 조립 문장(런타임 `%s`)은 이름 길이가 런타임이라 여기서 안 센다 —
`check_runtime_template_width`(④ 폭) · `check_battle_grid_wrap`(ED2 ①③) · `check_battle_wrap`(ED1 꼬리) 몫.

  python3 tools/check_typeset_rules.py          # 영역별 요약
  python3 tools/check_typeset_rules.py -v       # 위반 목록
"""

import os
import re
import sys
from itertools import pairwise

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

FRAME = 29
PUNCT_ONLY = re.compile(r"^[\s.,!?…‥·~\"'」』)\]]+$")


def _w(ch):
    return 1 if ch.isascii() else 2


def width(line):
    return sum(_w(c) for c in line)


def windows(rendered):
    """렌더 문자열 → 창 본문들. `%c` 사이가 창이고 이름판(`%c이름%c\\n`)은 떼어 낸다."""
    body = re.sub(r"%c[^%\n]{1,16}%c\n", "", rendered)  # 이름판
    return [w for w in body.split("%c") if w.strip()]


def engine_wrap(line):
    """엔진 런타임 줄넘김 흉내 — 29열을 넘기 전에 꺾는다. [(조각, 자동꺾임 여부)]."""
    out, cur, col = [], "", 0
    for ch in line:
        if col + _w(ch) > FRAME:
            out.append(cur)
            cur, col = "", 0
        cur += ch
        col += _w(ch)
    out.append(cur)
    return out


def _wordish(ch):
    return ch not in " \n" and not PUNCT_ONLY.match(ch)


def check_window(w):
    """[(규칙, 줄)] 위반."""
    out = []
    lines = w.split("\n")
    for i, ln in enumerate(lines):
        if (
            i and PUNCT_ONLY.match(ln) and 0 < len(ln.strip()) <= 2
        ):  # `.`·`!!` — 3자 이상은 말줄임 대사
            out.append(("①", ln))
        if 0 < i < len(lines) - 1 and ln == "" and lines[i - 1] != "":
            out.append(("②", "(빈 줄)"))
        if i and re.match(r"^ {1,2}\S", ln):
            out.append(("③", ln))
        # `%s`(주인공 이름)·`%d` 는 런타임 값 — 최장(세리오스·아트라스 = 8열)으로 친다
        # 조사 병기는 훅이 줄넘김(prewrap)보다 **먼저** 한 글자로 접는다 — 접은 뒤 폭으로 잰다
        vis = re.sub(r"(은|이|을|와)\((는|가|를|과)\)", r"\1", ln.rstrip(" "))
        vis = vis.replace("%s", "세리오스").replace(
            "%d", "9999"
        )  # 최장 이름·4자리 수치(마스터 09-27)
        chunks = engine_wrap(vis)
        # ② 꽉 찬 줄(29열) 바로 뒤의 **명시 개행** — 엔진이 이미 꺾었는데 우리 `\n` 이 한 번 더 꺾어 빈 줄
        #   (`test_frame_full_line_drops_our_newline` 이 막는 부류, pce 에서도 같은 발견 09-27)
        # 창을 닫기 직전의 꼬리 개행(`…。{n}{c}` — 원문 구조)은 뒤에 그릴 글이 없어 빈 줄이 안 보인다 → 뺀다
        if any(x.strip() for x in lines[i + 1 :]) and width(chunks[-1]) == FRAME:
            out.append(("②", f"{chunks[-1]}⏎(29열+개행)"))
        for a, b in pairwise(chunks):
            if b.startswith(" "):
                out.append(("③", f"{a}/{b}"))
            elif a and b and _wordish(a[-1]) and _wordish(b[0]):
                out.append(("④", f"{a}/{b}"))
            elif PUNCT_ONLY.match(b) and len(b.strip()) <= 2:
                out.append(("①", f"{a}/{b}"))
    return out


def scan(scenes=None, verbose=False):
    import reinsert_kr_pilot as R

    counts = {}
    rows = []
    for scn, eid, _jp, cand, _t in R.iter_candidates(scenes):
        area = scn[:3]
        for w in windows(R.render_bytes(cand)):
            for rule, ln in check_window(w):
                counts[(area, rule)] = counts.get((area, rule), 0) + 1
                rows.append((scn, eid, rule, ln))
    if verbose:
        for scn, eid, rule, ln in rows:
            print(f"  {rule} {scn} jp{eid}  {ln!r}")
    for area in ("ED1", "ED2"):
        print(
            f"  {area} 씬 대사: "
            + " · ".join(f"{r} {counts.get((area, r), 0)}" for r in ("①", "②", "③", "④"))
        )
    return rows


if __name__ == "__main__":
    rows = scan(verbose="-v" in sys.argv)
    print(f"  {'✅' if not rows else '❌'} 씬 조판 ①~④: {len(rows)}건")
    sys.exit(1 if rows else 0)
