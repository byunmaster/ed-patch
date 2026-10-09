"""부호·숫자 대역(0x02~0x3E) 연락처 — **눈으로 라벨링**해서 코드표를 고치는 자리.

코드표는 골격 대조로 풀었는데(`solve_charmap.py`) 이 대역은 로제타에 잘 안 걸린다 —
문장 안에서 부호는 자주 안 나오고, 나와도 후보가 여럿이라 표가 갈린다.
실제로 틀린 게 있었다: **`0x00D`·`0x00E` 는 「」가 아니라 ［］** 다(글리프를 그려 보면 바로 보인다).

    python3 tools/symbol_sheet.py --out work/review/symbols.png

그림을 보고 `charmap_ed3.json` 을 손으로 고친다 — **부호는 사람이 보는 게 제일 싸다.**
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common
import font as F
import textenc

LO, HI = 0x02, 0x3F
PER_ROW = 12


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--scale", type=int, default=5)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    common.verify_source(a.disc)
    exe, _, _ = F.exe_bytes(a.disc)
    m = textenc.charmap(a.disc)
    codes = [c for c in range(LO, HI) if np.asarray(F.read_glyph(exe, c, a.disc)).sum()]
    print(f"{a.disc}: 잉크가 있는 부호 글리프 {len(codes)}개 (0x{LO:02X}~0x{HI - 1:02X})")
    cell = F.ROWS + 4
    rows = (len(codes) + PER_ROW - 1) // PER_ROW
    img = np.zeros((rows * cell + 4, PER_ROW * (F.PITCH + 4) + 4), dtype=np.uint8)
    for i, c in enumerate(codes):
        r, q = divmod(i, PER_ROW)
        g = np.asarray(F.read_glyph(exe, c, a.disc), dtype=np.uint8)
        y = 4 + r * cell
        x = 4 + q * (F.PITCH + 4)
        img[y : y + F.ROWS, x : x + F.DRAW_W] = g[:, : F.DRAW_W] * 255
    im = Image.fromarray(img, "L")
    im = im.resize((im.width * a.scale, im.height * a.scale), Image.NEAREST)
    out = a.out or os.path.join(common.REVIEW_DIR, "symbols.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out)
    for r in range((len(codes) + PER_ROW - 1) // PER_ROW):
        chunk = codes[r * PER_ROW : (r + 1) * PER_ROW]
        print("   " + "  ".join(f"{c:03X}:{m.get(c) or '?'}" for c in chunk))
    print(f"→ {out}")


if __name__ == "__main__":
    main()
