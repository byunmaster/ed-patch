#!/usr/bin/env python3
"""**손 패딩 카드가 화면 가운데에 있는가** — 장 종료·타이틀 막간처럼 공백을 글자로 박아
위치를 정하는 줄을 본다.

**왜.** 이 카드들은 `textmap` 의 `ours` 안에 **선행 공백을 글자로** 넣어 위치를 만들고
조판기(`wrap_page`)를 **안 탄다.** 그래서 조판 지문도 락도 관측 대장도 이 자리를 못 본다 —
줄바꿈이 아니라 공백 개수라서다. 실제로 유저 QA(2026-08-31)에서 ED1 5장 종료 카드가
오른쪽으로 밀린 채 발견됐고, 훑어 보니 **여덟 줄이 최대 세 칸까지** 어긋나 있었다.

⚠ **온점 매달기(`818188c5`) 탓이 아니었다** — `818188c5^` 에도 pad 가 같다. 조판기 폭 상수가
움직여도 이 카드는 안 움직인다. 처음부터 손으로 잘못 넣은 값이었다.

**틀은 30열이다 — 근거는 원문의 패딩이다.** 코드 상수로는 못 정한다(`WRAP=14.0슬롯`=28열도
`FRAME_SLOTS=14.5`=29열도 조판기의 값이지 이 카드의 소비자가 아니다). 그래서 **JP 원문 카드
열 곳의 pad 를 EXE 에서 직접 떠서**(`ED.EXE` 0xBA0C~ · `ED2.EXE` 0x6360~) 좌우가 맞는 가설을
골랐다 — 28열 0곳 · 29열 0곳 · **30열 7곳**. `完`(2열)도 열한 곳 중 아홉이 pad 14 = 14/14 다.
(안 맞는 셋은 원문 자체가 어긋난 것이다 — 원문도 손 패딩이라 완벽하진 않다.)

⚠ **두 번 틀리고서 얻은 값이다.** ① 처음엔 화면을 눈대중해 30열로 맞게 짚었는데, ② 유저가
「살짝 오른쪽」이라 하자 근거 없이 29열로 내렸다가 이번엔 「왼쪽」이 됐다. 반 칸(1열) 차이는
스크린샷으로 못 가른다 — **관측자의 인상이 아니라 원문의 수치로 정해야 하는 값**이었다.

**규칙** — 선행 공백이 둘 이상인 줄은 좌우 여백 차가 **1열 이하**여야 한다. 폭이 홀수면
정중앙이 반 칸이라 어쩔 수 없이 1열 기우는데(ED1 5장이 유일하다), 그때는 **왼쪽으로**
기울인다(내림). 공백 하나짜리는 들여쓰기지 중앙정렬이 아니라 뺀다.

  python3 tools/check_card_centering.py       # 요약
  python3 tools/check_card_centering.py -v    # 자리마다
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reinsert_kr_pilot import cell_w

TEXTMAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "textmap")
FRAME = 30  # 열. JP 원문 카드의 패딩에서 나온 값이다 — 위 독스트링.
MIN_PAD = 2  # 공백 하나는 들여쓰기다


def cols(s):
    """전각 2열·반각 1열로 센 화면 폭."""
    return int(sum(cell_w(c) * 2 for c in s))


def scan(verbose=False):
    bad = []
    for fn in sorted(os.listdir(TEXTMAP)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(TEXTMAP, fn), encoding="utf-8") as f:
            doc = json.load(f)
        for e in doc.get("entries", []):
            ours = e.get("ours")
            if not ours:
                continue
            for ln in ours.replace("%c", "").split("\n"):
                body = ln.lstrip(" ")
                pad = len(ln) - len(body)
                if pad < MIN_PAD or not body.strip():
                    continue
                right = FRAME - pad - cols(body)
                if right < 0 or abs(pad - right) <= 1:
                    continue
                bad.append((fn[:-5], e["k"], pad, right, body))
    print(f"  {'✅' if not bad else '⚠'} 손 패딩 카드 중앙정렬 어긋남 {len(bad)}곳 (틀 {FRAME}열)")
    if verbose:
        for cls, k, pad, right, body in bad:
            print(f"      {cls} {k}: 왼{pad} 오{right}  |{body}|")
    return len(bad)


if __name__ == "__main__":
    sys.exit(1 if scan(verbose="-v" in sys.argv) else 0)
