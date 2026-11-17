"""타이틀 「계속해서 시작」 로드 창의 창 열기·글 그리기 호출을 잡는다(시험 전용, 제품 롬 불변 — RAM 덫).

   sh scripts/capture.sh python3 tools/wt_load.py <cue> <card.mcr> <출력폴더> [○ 횟수(기본 6)] [덫 거는 시점(기본 5)]
창 열기 `0x80015B20(x, y, 열, 행)` · 글 그리기 `0x80017334(창, 문자열…)` 를 로그로 적는다. 원판·한글판에 같은 입력을 먹여 창 좌표를 견준다.
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import headless_ps1 as H
import wintrace as WT


def main():
    cue, card, out = sys.argv[1:4]
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    at = int(sys.argv[5]) if len(sys.argv) > 5 else 5
    os.makedirs(out, exist_ok=True)
    shutil.copy(card, out + "/card.mcr")
    e = H.Emu(cue, card=out + "/card.mcr")
    e.run(600)
    for i in range(n):
        if i == at:
            WT.install(e)
        e.press("circle", 8, 60)
        e.run(120)
    e.shot(out + "/load.png")
    import struct

    n = struct.unpack("<I", e.peek(WT.LOG, 4))[0]
    cur = [
        struct.unpack("<2H", e.peek(WT.LOG + 128 * k + 80, 4)) for k in range(1, n + 1)
    ]  # 그릴 때 창의 커서 (열 0x26, 행 0x28)
    for k, ev in enumerate(WT.drain(e)):
        tag, a0, a1, a2, a3, ra, x, y, c, r, codes, _hex = ev
        print(
            tag,
            f"ra={ra:08x}",
            "a=",
            a0,
            a1,
            a2,
            a3,
            "win",
            x,
            y,
            c,
            r,
            "cur(열,행)",
            cur[k],
            "codes",
            [hex(v) for v in (codes or [])],
            flush=True,
        )


if __name__ == "__main__":
    main()
