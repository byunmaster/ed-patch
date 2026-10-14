#!/usr/bin/env python3
"""씬 번역 작업표 — 한 씬의 메시지(열쇠 · 화자 · 조각 여부 · 원문 · 지금 번역)를 번역자가 읽는 꼴로 낸다.

  python3 tools/scene_sheet.py 19 20 21     # 작업표(표준 출력) — 원문이라 커밋 금지(저작권)
  python3 tools/scene_sheet.py --todo       # 씬별 미번역 줄 수 · 원문 글자 수
  python3 tools/scene_sheet.py -n 19 20     # 미번역 줄만(빈 줄 제외)

`PS1=` 는 PS1 사전(`line_dict`)에 **같은 열쇠**(화자+원문이 같음)가 있을 때의 PS1 문안이다 — 원문이 같으면 이 문안을 쓴다.
`(조각)` = 화자 전환·옵코드에서 끊긴 메시지(앞부분만 번역 단위). 화자가 없으면 서술이거나 앞 창 화자 이어받음이다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import messages as M

DERIVED = common.GAME_DIR / "work" / "derived" / "messages"
LINE_DICT = common.ROOT / "games" / "ps1-ed1+2" / "line_dict.json"


def scenes() -> list[int]:
    return sorted(int(p.stem[3:]) for p in DERIVED.glob("scn*.json"))


def load(n: int) -> list[dict]:
    return json.loads((DERIVED / f"scn{n:03d}.json").read_text("utf-8"))


def ps1() -> dict:
    return json.loads(LINE_DICT.read_text("utf-8"))["lines"]


def todo() -> None:
    d = ps1()
    tl = tc = th = 0
    for n in scenes():
        ours = M.load_translations(n)
        left = [m for m in load(n) if m["key"] not in ours and m["jp"].strip()]
        if left:
            hit = sum(m["key"] in d for m in left)
            c = sum(len(m["jp"]) for m in left)
            tl, tc, th = tl + len(left), tc + c, th + hit
            print(f"scn{n:03d}  미번역 {len(left):3d}줄  {c:5d}자  PS1 같은 열쇠 {hit}")
    print(f"합계 {tl}줄 {tc}자 · PS1 같은 열쇠 {th}")


def sheet(n: int, new_only: bool = False) -> None:
    sp = M.load_speakers()
    ours = M.load_translations(n)
    d = ps1()
    print(f"## scn{n:03d}")
    for i, m in enumerate(load(n)):
        who = m["speaker"]
        label = f"{who}→{sp.get(who, '??')}" if who else (f"공용문구 {m['common']}" if m["common"] is not None else "-")
        flag = " (조각)" if m["complex"] else ""
        if new_only and (m["key"] in ours or not m["jp"].strip("\n\u3000 ")):
            continue
        print(f"[{i}] {m['key']} | {label}{flag}")
        print("  JP: " + m["jp"].replace("\f", "¶").replace("\n", "⏎"))
        have = ours.get(m["key"], {}).get("t")
        if have is not None:
            print("  KO: " + have.replace("\f", "¶"))
        elif m["key"] in d:
            print("  PS1=" + d[m["key"]]["t"].replace("{p}", "¶"))


def main() -> int:
    a = sys.argv[1:]
    if not a or a == ["--todo"]:
        todo()
        return 0
    new_only = "-n" in a
    for x in a:
        if x != "-n":
            sheet(int(x), new_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
