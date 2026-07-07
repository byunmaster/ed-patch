"""
폰트 탐색 v2: JIS 배열 일관성 검증.
JIS X 0208에서 히라가나는 ぁあぃいぅう… 순서 — あ가 어딘가 있으면
2글리프 뒤 い, 4글리프 뒤 う가 있어야 한다. 세 글자가 동시에 맞는
지점만 보고해 오검출을 제거한다. 16x16(32B)과 12x12(24B, 행당 2B) 모두 시도.
"""

import os
import re

import numpy as np
from common import extract
from PIL import Image, ImageDraw, ImageFont

FONT = r"C:\Windows\Fonts\msgothic.ttc"
POPCNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint16)


def ref_bitmap(ch, px, dy):
    img = Image.new("1", (16, px), 0)
    d = ImageDraw.Draw(img)
    d.text((0, dy), ch, fill=1, font=ImageFont.truetype(FONT, px))
    return np.packbits(np.array(img, dtype=np.uint8), axis=1).reshape(-1)  # px*2 bytes


def sim_at(arr, off, ref):
    if off < 0 or off + len(ref) > len(arr):
        return 0.0
    x = POPCNT[arr[off : off + len(ref)] ^ ref].sum()
    return 1 - x / (len(ref) * 8)


def scan_file(name, data, results):
    arr = np.frombuffer(data, dtype=np.uint8)
    for px, gsize in ((16, 32), (12, 24)):
        for dy in (-2, -1, 0):
            ra = ref_bitmap("あ", px, dy)
            ri = ref_bitmap("い", px, dy)
            ru = ref_bitmap("う", px, dy)
            n = len(arr) - gsize
            if n <= 0:
                continue
            simA = np.zeros(n + 1, dtype=np.uint16)
            for j in range(gsize):
                simA += POPCNT[arr[j : j + n + 1] ^ ra[j]]
            match = 1 - simA / (gsize * 8)
            for off in np.nonzero(match >= 0.75)[0]:
                si = sim_at(arr, int(off) + 2 * gsize, ri)
                su = sim_at(arr, int(off) + 4 * gsize, ru)
                if si >= 0.75 and su >= 0.75:
                    results.append((float(match[off] + si + su) / 3, name, int(off), px, dy))


def main():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "iso_files.txt")
    results = []
    with open(path, encoding="utf-8") as f:
        next(f)
        for line in f:
            m = re.match(r"\s*(\d+)\s+(\d+)\s+([\d,]+)\s+(\S+)", line)
            if not m:
                continue
            lba, _, size, name = m.groups()
            if name.startswith("/XA/") or "DUMMY" in name or "DMY" in name:
                continue
            scan_file(name, extract(int(lba), int(size.replace(",", ""))), results)
    results.sort(reverse=True)
    if results:
        print("あ+い+う JIS 배열 일치 지점:")
        for avg, name, off, px, dy in results[:15]:
            print(f"  평균 {avg * 100:.0f}%  {name} +0x{off:X}  ({px}px, dy={dy})")
    else:
        print("일치 없음 — 무압축 JIS계열 1bpp 폰트(16/12px) 아님. 압축·4bpp·커스텀 배열 가능성.")


if __name__ == "__main__":
    main()
