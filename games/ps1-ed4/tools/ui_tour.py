"""EXE 창 UI 순회 촬영(시험 전용, 제품 롬 불변 — 캡처에 「디버그 이동」 아님·세이브 로드 사용).

세이브를 로드해 필드에서 △ 메뉴를 열고 항목마다 ○ 로 들어가 보고 ✕ 로 나오며 한 장씩 찍는다.
   sh scripts/capture.sh python3 tools/ui_tour.py <cue> <card.mcr> <출력폴더>
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness as D  # noqa: F401  (drc 끄기 먼저)
import headless_ps1 as H


def wins(e):
    """열린 창 구조체(0x801EF9C8 + 42B×번호): +2 x · +4 y · +6 열 · +8 줄(창 여는 함수의 인자)."""
    import struct

    out = []
    for i in range(64):
        b = e.peek(0x801EF9C8 + 42 * i, 42)
        x, y, c, r = struct.unpack_from("<hhHH", b, 2)
        if os.environ.get("WINS_ALL") or (
            1 <= c <= 0x30 and 1 <= r <= 0x20 and -200 < x < 400 and -100 < y < 300
        ):
            out.append((i, x, y, c, r))
    return out


def main():
    cue, card, out = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    tmp = "/tmp/claude-0/card_tour.mcr"
    shutil.copy(card, tmp)
    e = H.Emu(cue, card=tmp)
    e.run(600)
    for _ in range(11):
        e.press("circle", 8, 60)
        e.run(120)
    e.run(200)
    e.shot(f"{out}/00_field.png")
    e.press("triangle", 8, 40)
    e.run(40)
    e.shot(f"{out}/01_menu.png")
    base = f"{out}/menu.state"
    e.save(base)
    for i in range(5):
        e.load(base)
        e.run(1)
        for _ in range(i):
            e.press("down", 8, 20)
        for k in range(4):  # 항목 안으로 ○ 를 거듭 눌러 한 단계씩
            e.press("circle", 8, 40)
            e.run(30)
            e.shot(f"{out}/m{i}_{k}.png")
            print(f"m{i}_{k}", wins(e), flush=True)
            for _ in range(2):  # 장비·마법 창에서 한 번 더 내려 가며
                e.press("down", 8, 15)
            e.shot(f"{out}/m{i}_{k}_dn.png")


if __name__ == "__main__":
    main()
