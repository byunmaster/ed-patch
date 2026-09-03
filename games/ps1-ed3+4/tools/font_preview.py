"""폰트 후보 미리보기 — **게임 조판 그대로** 그려 눈으로 고른다.

한 줄에 한글과 일본어를 **섞어** 그린다. 베이스라인 어긋남은 이래야 보인다 —
후보를 따로따로 그려 놓으면 각자 제 칸 안에서만 보여서 **밀림이 안 보인다**(실측:
그렇게 그렸다가 잘못된 dy 도 멀쩡해 보였다).

⚠ 이미지를 굽기 전에 이걸 먼저 본다(레포 관용: 그림·조판은 PNG 미리보기로 확인받는다).

    python3 tools/font_preview.py --out work/review/font.png
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
import common  # noqa: E402
import font as F  # noqa: E402
import textenc  # noqa: E402

from shared import fonts  # noqa: E402

CANDIDATES = [
    ("Galmuri11 dy=-3  (원본과 같은 자리 0~10행)", "Galmuri11", -3),
    ("Galmuri11 dy=-4  (한 줄 위 — 아래가 잘린다)", "Galmuri11", -4),
    ("Galmuri11-Condensed dy=-3", "Galmuri11-Condensed", -3),
    ("GalmuriMono11 dy=-3", "GalmuriMono11", -3),
    ("Galmuri11 dy=-2  (첫 빌드 — 한 줄 아래로 밀렸다)", "Galmuri11", -2),
]


def row(text, bdf=None, dy=0, disc="ed3"):
    """원본에 있는 글자는 **게임 글리프**로, 없는 글자(한글)는 BDF 로 그린다."""
    exe, _, _ = F.exe_bytes(disc)
    rev = {v: k for k, v in textenc.charmap(disc).items()}
    f = fonts.galmuri(bdf) if bdf else None
    out = np.zeros((F.ROWS, F.PITCH * len(text)), dtype=np.uint8)
    for i, ch in enumerate(text):
        if ch in rev:
            g = np.asarray(F.read_glyph(exe, rev[ch], disc), dtype=np.uint8)
        elif f is not None:
            g = np.asarray(f.bits(ch, dy=dy, rows=F.ROWS, width=F.DRAW_W), dtype=np.uint8)
        else:
            continue
        out[:, i * F.PITCH : i * F.PITCH + F.DRAW_W] = g[:, : F.DRAW_W]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jp", default="クリスチーナ。明日の準備はできているの？")
    ap.add_argument("--mix", default="크리스티나。明日は준비되었니？라구ドゥル")
    ap.add_argument("--scale", type=int, default=5)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    rows = [("원본 일본어만 (기준선)", row(a.jp))]
    rows += [(label, row(a.mix, bdf, dy)) for label, bdf, dy in CANDIDATES]

    pad = 6
    width = max(r.shape[1] for _, r in rows) + pad * 2
    height = (F.ROWS + pad) * len(rows) + pad
    img = np.zeros((height, width), dtype=np.uint8)
    y = pad
    for _, r in rows:
        img[y : y + F.ROWS, pad : pad + r.shape[1]] = r * 255
        y += F.ROWS + pad
    im = Image.fromarray(img, "L").resize((width * a.scale, height * a.scale), Image.NEAREST)
    out = a.out or os.path.join(common.REVIEW_DIR, "font_preview.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out)
    for i, (label, _) in enumerate(rows):
        print(f"  {i + 1}행 — {label}")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
