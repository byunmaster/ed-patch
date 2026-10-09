"""폰트 시험대 — 후보 × 시험 문장을 한 장에 굽는다. **굽기 전에 이걸 본다.**

원본에 있는 글자는 게임 글리프로, 없는 글자(한글)는 BDF 로 그린다. 그래서 한 줄 안에서
**베이스라인·굵기·자간**이 원본과 어떻게 어울리는지 바로 보인다.

⚠ 창 폭은 **24칸**이다(원본 줄 29,503개 실측: 최장 24, 99.9%가 23 이하).
   시험 문장에 24칸짜리를 꼭 넣는다 — 넘치는지는 여기서 본다.
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
import common
import font as F
import textenc

from shared import fonts

WINDOW_CELLS = 24

FONTS_ = [
    ("Galmuri11", "Galmuri11", -3),
    ("Galmuri11-Bold", "Galmuri11-Bold", -3),
    ("Galmuri11-Condensed", "Galmuri11-Condensed", -3),
    ("GalmuriMono11", "GalmuriMono11", -3),
    ("Galmuri9", "Galmuri9", -2),
]

LINES = [
    ("원본(기준)", "あいうえおかきくけこ、さしすせそ。"),  # 가짜 문장(16칸)
    ("한·일 혼용", "가나다라。あいうえお마바사？ドゥル와 함께"),
    ("겹받침", "앉았다 밟고 읊조리며 꿇었다 흙 뚫고 넓은 값"),
    ("숫자·부호", "０１２３４５６７８９「」…‥・、。？！"),
    ("24칸 가득", "그때가 되면 모든 것이 밝혀질 테니 기다려라"),
]


def draw(text, bdf, dy, disc="ed3"):
    exe, _, _ = F.exe_bytes(disc)
    rev = {v: k for k, v in textenc.charmap(disc).items()}
    f = fonts.galmuri(bdf) if bdf else None
    cells = text[:WINDOW_CELLS]
    out = np.zeros((F.ROWS, F.PITCH * WINDOW_CELLS), dtype=np.uint8)
    for i, ch in enumerate(cells):
        if ch in rev:
            g = np.asarray(F.read_glyph(exe, rev[ch], disc), dtype=np.uint8)[:, : F.DRAW_W]
        elif f is not None:
            g = np.asarray(f.bits(ch, dy=dy, rows=F.ROWS, width=F.HANGUL_W), dtype=np.uint8)
        else:
            continue
        out[:, i * F.PITCH : i * F.PITCH + g.shape[1]] = g
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rows = []
    for fname, bdf, dy in FONTS_:
        rows.append((f"── {fname}", None))
        for label, text in LINES:
            rows.append((f"   {label}", draw(text, bdf, dy)))
    pad = 4
    width = F.PITCH * WINDOW_CELLS + pad * 2
    height = sum(F.ROWS + pad if r is not None else 5 for _, r in rows) + pad
    img = np.zeros((height, width), dtype=np.uint8)
    y = pad
    for _, r in rows:
        if r is None:
            y += 5
            continue
        img[y : y + F.ROWS, pad : pad + r.shape[1]] = r * 255
        y += F.ROWS + pad
    im = Image.fromarray(img, "L").resize((width * a.scale, height * a.scale), Image.NEAREST)
    out = a.out or os.path.join(common.REVIEW_DIR, "font_test.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out)
    for label, _ in rows:
        print(f"  {label}")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
