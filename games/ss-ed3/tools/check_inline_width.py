#!/usr/bin/env python3
"""**인라인 아이템 코드(`<01><번호>`)에 이름이 꽂힌 뒤의 줄 폭** — 조판기는 코드를 폭 0 으로 읽는다.

    python3 games/ss-ed3/tools/check_inline_width.py

게임은 코드 자리에 PARAM 아이템 이름(1~8자)을 꽂아 같은 줄에 이어 쓴다. 이름 폭을 모른 채 짠 줄은 17칸을 넘으면
엔진이 **글자 한복판에서** 접는다(10-23 실측 9블록: 「나이/프」·「받/았습니다」). 병기 조사 `을(를)` 은 빌드 때 하나로 줄어
한 글자로 센다. 이름이 사전에 없으면 전각 8자로 가정한다(최악).
넘친 줄은 **어절 경계에 개행**(공백 → 개행, 길이 보존)으로 푼다. 개행이 쪽 줄 수를 한도(3줄)보다 늘리지 않는지도 본다.
"""

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import inline_josa as J
import typeset as T

RX = re.compile(r"<01><([0-9A-Fa-f]{2})>")
JOSA = re.compile(r"(을|이|은|과|으)\((를|가|는|와|로)\)")


def main():
    names = J.item_names()
    n, bad = 0, []
    for f in sorted(glob.glob(os.path.join(C.GAME_DIR, "script", "MAP*.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        for k, t in d.items():
            if not isinstance(t, str) or "<01>" not in t:
                continue
            n += 1
            full = JOSA.sub(r"\1", RX.sub(lambda m: names.get(int(m.group(1), 16), "가" * 8), t))
            for ln in T.lines(full):
                if len(T.fold(ln)) > 1:
                    bad.append(f"{os.path.basename(f)[:6]}#{k}  {'|'.join(T.fold(ln))}")
            #   쪽마다 접힌 줄 수가 창 줄 한도(3, 화자 줄 포함)를 넘으면 위로 밀려 읽기 전에 사라진다 — 개행이 줄을 늘릴 수 있다
            for pg, rows in T.overflows(full):
                bad.append(f"{os.path.basename(f)[:6]}#{k}  {pg + 1}쪽이 {rows}줄(한도 {T.WIN_ROWS})")
    print(f"  인라인 아이템 코드 {n}블록 · 이름을 꽂으면 17칸을 넘어 접히는 줄 {len(bad)}")
    for b in bad:
        print("   ✗", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
