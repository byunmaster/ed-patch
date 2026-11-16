"""입력 스크립트 재생 — 세이브를 불러온 뒤 같은 입력을 **한글 롬과 원판에 똑같이** 먹여 같은 화면 짝을 찍는다(결정적 재생).

    python3 tools/replay.py <cue> <카드.mcr> <슬롯 내림 횟수> <스크립트> <출력 폴더>

스크립트(한 줄에 하나, `#` 주석): `p <버튼> <누른 프레임> <뗀 뒤 프레임>` · `r <프레임>`(그냥 진행) · `s <이름>`(캡처 → `<출력>/<이름>.png`)
버튼 = up down left right circle cross square triangle start select. 불러오기 전주(타이틀 → 이어서 시작 → 페이지 → 슬롯 → 확인)는 고정이다 —
`슬롯 내림 횟수` 0 = 슬롯 1, 1 = 슬롯 2.
🔴 헤드리스 libretro 하네스(`games/ps1-ed3/tools/headless_ps1.py`)를 쓴다 — 촬영 칸 규칙: `sh scripts/capture.sh [--fix] python3 …`.
같은 스크립트를 원판 cue 에도 돌리면 같은 순간의 일본어 화면이 나온다(문안 길이만 다를 뿐 진행은 같다 — 실측으로 확인할 것).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "ps1-ed3", "tools"))
import headless_ps1 as H  # noqa: E402


def boot(cue, card, slot_downs):
    e = H.Emu(cue, card=card)
    for _ in range(14):
        e.press("circle", 8, 82)
    e.run(300)
    e.press("down", 8, 30)
    e.press("circle", 8, 60)
    for k in range(2, 14):
        e.run(60)
        if k == 3:
            e.press("circle", 8, 30)
        if k == 5:
            for _ in range(slot_downs):
                e.press("down", 8, 20)
            e.press("circle", 8, 30)
        if k in (7, 9):
            e.press("circle", 8, 30)
    for _ in range(3):
        e.press("circle", 8, 30)
        e.run(200)
    return e


def play(e, script, out):
    os.makedirs(out, exist_ok=True)
    for ln in open(script, encoding="utf-8"):
        ln = ln.split("#")[0].split()
        if not ln:
            continue
        if ln[0] == "p":
            e.press(ln[1], int(ln[2]), int(ln[3]))
        elif ln[0] == "r":
            e.run(int(ln[1]))
        elif ln[0] == "s":
            e.shot(os.path.join(out, ln[1] + ".png"))
        else:
            raise SystemExit(f"읽을 수 없는 줄: {ln}")


if __name__ == "__main__":
    cue, card, downs, script, out = sys.argv[1:6]
    play(boot(cue, card, int(downs)), script, out)
