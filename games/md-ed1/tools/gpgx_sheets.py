"""`gpgx_battle.py` 가 낸 PNG 에서 메시지 창만 잘라 한 장에 모은다(검수용 — 24칸씩, 칸마다 블록·스트림 꼬리표).

사용: `python3 gpgx_sheets.py <PNG 폴더> <출력 폴더> [--per 24]`
"""

import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw

CELL_W, CELL_H, LAB = 320, 56, 11


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--per", type=int, default=24)
    a = ap.parse_args()
    files = sorted(Path(a.src).glob("b[0-9][0-9][0-9]_*.png"))
    out = Path(a.dst)
    out.mkdir(parents=True, exist_ok=True)
    for n in range(0, len(files), a.per):
        chunk = files[n : n + a.per]
        cols = 2
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (CELL_W * cols, (CELL_H + LAB) * rows), (24, 24, 24))
        d = ImageDraw.Draw(sheet)
        for i, f in enumerate(chunk):
            m = re.match(r"b(\d+)_([0-9a-f]+)_(r\d+)", f.stem)
            tag = f"b{int(m.group(1))} 0x{m.group(2)} {m.group(3)}" if m else f.stem
            im = Image.open(f).convert("RGB")
            crop = im.crop((0, 168, 320, 224))
            x, y = (i % cols) * CELL_W, (i // cols) * (CELL_H + LAB)
            d.text((x + 2, y), tag, fill=(255, 255, 0))
            sheet.paste(crop, (x, y + LAB))
        sheet.save(out / f"sheet_{n // a.per:03d}.png")
    print(len(files), "→", (len(files) + a.per - 1) // a.per, "장")


if __name__ == "__main__":
    main()
