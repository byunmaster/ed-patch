"""맵의 대사 창을 전부 다시 찍는다 — **글자가 처음 나타날 때까지 기다린 뒤 멎으면** 찍는다(노이즈 프레임·덜 그려진 창 방지, 10-20 qa 지적).

  python3 tools/dialog_reshoot.py --maps GT0101,FR5210 --out <폴더> [--cue …] [--state …]

산출: `<out>/<맵>/NNN.png`(창 띠 — 하네스와 같은 번호) · `<out>/index.tsv`(맵·번호·시퀀스·잉크 픽셀·상태). 상태: 정상 · 글자없음 · 창없음(안 멎음/안 열림, 전체 화면을 `NNNx.png` 로 남김).
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dialog_harness as D
import dialog_verify as V
import headless_ps1 as H
from warp_table import table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=D.DEFAULT_CUE)
    ap.add_argument("--state")
    ap.add_argument("--cap", type=int, default=2400)
    a = ap.parse_args()
    ch = {n: c for n, c, _p, _a in table("ed3")}
    emu = H.Emu(a.cue)
    D.boot(emu, a.state, a.cue)
    os.makedirs(a.out, exist_ok=True)
    idx = os.path.join(a.out, "index.tsv")
    if not os.path.exists(idx):
        open(idx, "w", encoding="utf-8").write("맵\t번호\t오프셋\t시퀀스\t잉크\t상태\n")
    cur = 0
    for name in a.maps.split(","):
        d = os.path.join(a.out, name)
        if os.path.exists(os.path.join(d, "done")):
            continue
        cur = D.jump(emu, name, ch[name][0], cur)
        os.makedirs(d, exist_ok=True)
        snap = os.path.join(d, "_s.state")
        emu.save(snap)
        # 🔴 창은 `D.windows` — 포인터 목표가 조각 시작인 대사 창만, 번호 n = 짝 표의 창 번호. 옛 `sequences` 는 데이터 `0F 90 00 20` 같은 가짜를
        #    대사로 찍어 노이즈 창을 냈고 진짜 창을 놓쳤다(FT4300: 창 39 ↔ 옛 32 — 10-20 qa).
        wins = D.windows(emu)
        blk_changed = False
        rows = []
        for k, s, al in wins:
            off = 0
            emu.load(snap)
            emu.run(2)
            base = emu.frame.copy()
            D.inject(emu, s, al)
            b, n = V.wait_text(emu, base, cap=a.cap)
            if b is None or n <= 0:
                Image.fromarray(np.ascontiguousarray(emu.frame)).save(os.path.join(d, f"{k:03d}x.png"))
                rows.append((name, k, off, s.hex(), 0, "글자없음" if n == 0 else "창없음"))
                continue
            Image.fromarray(np.ascontiguousarray(emu.frame[b[0] : b[1]])).save(os.path.join(d, f"{k:03d}.png"))
            rows.append((name, k, off, s.hex(), n, "정상" + ("(블록 바뀜)" if blk_changed else "")))
        os.remove(snap)
        with open(idx, "a", encoding="utf-8") as f:
            for r in rows:
                f.write("\t".join(map(str, r)) + "\n")
        open(os.path.join(d, "done"), "w").close()
        print(name, len(rows), flush=True)


if __name__ == "__main__":
    main()
