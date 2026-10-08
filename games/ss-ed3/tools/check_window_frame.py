#!/usr/bin/env python3
"""**메뉴 라벨이 칸을 넘치는가** — 우리 라벨의 표시 폭이 원문 라벨보다 넓으면 틀·옆 라벨과 겹친다.

    python3 games/ss-ed3/tools/check_window_frame.py        # 게이트
    python3 games/ss-ed3/tools/check_window_frame.py -v     # 전량

시스템 표(`script/system.json`)의 UI 라벨(메뉴·능력치·설정·블랙잭·낱말·지명·인물·장 제목)은 **원문 라벨이 차지하던 칸에 그대로** 들어간다
(`reinsert_sys` 는 바이트만 맞춘다 — 폭은 안 본다). 바이트는 맞아도 **반각이 섞이면 폭이 다르다** — 우리 폭이 원문 폭을 넘으면 칸을 넘친다.
폭은 `typeset.cols`(숫자는 전각으로 그려지니 1칸)로 잰다. ⚠ 줄 안 공백(`\\u3000`)은 칸 맞춤이라 그대로 센다.

받아들인 넘침은 `script/window_frame_accept.json`(키 = 섹션|원문, 값 = 사유). 새로 생기면 실패한다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import typeset as T

SECTIONS = ("menu", "stat", "setting", "blackjack", "word", "place", "person", "chapter", "chapter_line")
ACCEPT = os.path.join(C.GAME_DIR, "script", "window_frame_accept.json")


def cols(s):
    s = s.replace("\x00", "").replace("\x0f", "").replace("\x10", "").replace("\x0e", "").replace("\x07", "")
    return sum(1.0 if ch.isdigit() else T.cols(ch) for ch in s.replace("\r", "\n") if ch != "\n")


def main():
    with open(os.path.join(C.GAME_DIR, "script", "system.json"), encoding="utf-8") as f:
        doc = json.load(f)
    accept = {}
    if os.path.exists(ACCEPT):
        with open(ACCEPT, encoding="utf-8") as f:
            accept = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    n, over = 0, []
    for sec in SECTIONS:
        for jp, kr in doc[sec].items():
            n += 1
            if cols(kr) > cols(jp) + 1e-9:
                over.append((f"{sec}|{jp}", cols(jp), cols(kr), kr))
    new = [o for o in over if o[0] not in accept]
    print(f"UI 라벨 {n} 중 원문보다 넓은 것 {len(over)} (받아들인 {len(over) - len(new)} · 새로 {len(new)})")
    for k, a, b, kr in over if "-v" in sys.argv else new:
        mark = "·" if k in accept else "✗"
        print(f"  {mark} {k.split('|')[0]:<13} 원문 {a:>4} → 우리 {b:>4}  {kr!r}")
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
