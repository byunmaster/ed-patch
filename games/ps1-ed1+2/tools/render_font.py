"""
폰트 비트맵 정적 탐색: ISO 파일을 1bpp/2bpp/4bpp 글리프 그리드로 렌더링해
PNG로 저장한다. 사람이(또는 Claude가) 눈으로 글리프를 찾는 용도.

사용: python render_font.py <LBA> <size> <label> [--bpp 1] [--cell 16] [--start 0] [--len N]
예:   python render_font.py 2577 335872 startdat
"""

import argparse
import os

from common import OUT_DIR, extract
from PIL import Image


def render(data, bpp, cell, cols):
    """data를 cell×cell 글리프의 그리드로 렌더. 글리프당 바이트 = cell*cell*bpp/8"""
    gbytes = cell * cell * bpp // 8
    n = len(data) // gbytes
    rows = (n + cols - 1) // cols
    img = Image.new("L", (cols * cell, rows * cell), 0)
    px = img.load()
    for g in range(n):
        gx, gy = (g % cols) * cell, (g // cols) * cell
        chunk = data[g * gbytes : (g + 1) * gbytes]
        for i in range(cell * cell):
            if bpp == 1:
                v = (chunk[i // 8] >> (7 - i % 8)) & 1
                val = v * 255
            elif bpp == 2:
                v = (chunk[i // 4] >> (6 - (i % 4) * 2)) & 3
                val = v * 85
            else:  # 4bpp — PS1 텍스처는 리틀 니블 우선
                b = chunk[i // 2]
                v = (b & 0x0F) if i % 2 == 0 else (b >> 4)
                val = v * 17
            px[gx + i % cell, gy + i // cell] = val
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lba", type=lambda x: int(x, 0))
    ap.add_argument("size", type=lambda x: int(x, 0))
    ap.add_argument("label")
    ap.add_argument("--bpp", type=int, default=1, choices=(1, 2, 4))
    ap.add_argument("--cell", type=int, default=16)
    ap.add_argument("--start", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--len", dest="length", type=lambda x: int(x, 0), default=None)
    ap.add_argument("--cols", type=int, default=64)
    a = ap.parse_args()

    data = extract(a.lba, a.size)[a.start :]
    if a.length:
        data = data[: a.length]
    img = render(data, a.bpp, a.cell, a.cols)
    out = os.path.join(OUT_DIR, f"font_{a.label}_{a.bpp}bpp_{a.cell}px.png")
    img.save(out)
    print(f"{out}  ({img.width}x{img.height}, 글리프당 {a.cell * a.cell * a.bpp // 8}B)")


if __name__ == "__main__":
    main()
