"""선택지 창 열 실측(시험 전용, 제품 롬 불변 — 캡처에 「디버그 이동」 표기).

AT01005 로 이동한 뒤 RAM 의 `3B a 열 줄` 연산 열 바이트를 N 으로 바꾸고 ○ 로 진행해 창이 뜬 화면을 찍는다.
   sh scripts/capture.sh python3 tools/choice_probe.py <cue> <card.mcr> <맵> <출력폴더> <N,N,..>
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import debug_warp as W
import dialog_harness as D


def find_ops(e, rows_want=(2, 3)):
    ram = e.peek(0x80000000, 0x200000)
    out = []
    i = 0
    while True:
        i = ram.find(b"\x3b", i + 1)
        if i < 0:
            break
        cols, rows = ram[i + 2], ram[i + 3]
        if 1 <= cols <= 24 and rows in rows_want and ram[i + 5] == 0x0F:
            out.append((0x80000000 + i, cols, rows))
    return out


def main():
    cue, card, name, out, ns = sys.argv[1:6]
    os.makedirs(out, exist_ok=True)
    base = out + "/base.state"
    e = D.make_state(cue, card, base)
    W.warp(e, name, 0, b"\0\0\0", settle=120)
    here = out + "/warped.state"
    e.save(here)
    ops = find_ops(e)
    print("ops", [(hex(a), c, r) for a, c, r in ops], flush=True)
    open(out + "/INDEX.txt", "w").write(f"디버그 이동 — {name} 선택지 열 실측(제품 롬 아님) ops={ops}\n")
    for n in [int(x) for x in ns.split(",")]:
        e.load(here)
        e.run(1)
        for a, c, r in ops:
            if n:  # N=0 이면 굽힌 값 그대로(맞춤 열 미리보기)
                e.poke(a + 2, bytes([n]))
        downs = {int(x) for x in os.environ.get("DOWNS", "").split(",") if x}  # 이 번호의 ○ 앞에 ↓ 를 한 번 눌러 둘째 항목을 고른다
        for j in range(int(os.environ.get("PRESSES", "30"))):
            if j in downs:
                e.press("down", 4, 10)
            e.press("circle", 6, 50)
            e.shot(f"{out}/{name}_cols{n:02d}_{j:02d}.png")


if __name__ == "__main__":
    main()
