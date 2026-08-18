"""
참조 글리프 상관 탐색: MS Gothic(JIS 비트맵 계열)의 16x16 글리프를 기준으로
ISO 내 모든 데이터 파일에서 1bpp 폰트 비트맵과 유사한 바이트열을 찾는다.
게임 폰트가 JIS ROM 계열이면 높은 유사도로 걸린다. (압축돼 있으면 안 걸림 → 런타임 확인)
"""

import os
import re

import numpy as np
from common import OUT_DIR, extract
from PIL import Image, ImageDraw, ImageFont

REF_CHARS = ["あ", "王", "永"]
FONT = r"C:\Windows\Fonts\msgothic.ttc"
POPCNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint16)


def ref_bitmap(ch, dy=0):
    """16x16 1bpp, 행당 2바이트 MSB 우선. dy로 세로 위치 보정."""
    img = Image.new("1", (16, 16), 0)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 16)
    d.text((0, dy), ch, fill=1, font=font)
    bits = np.array(img, dtype=np.uint8)  # (16,16)
    packed = np.packbits(bits, axis=1)  # (16,2)
    return packed.reshape(-1)  # 32B


def scan(data, ref):
    """data에서 ref(32B)와의 해밍 유사도(일치 비트 비율) 최대 지점들."""
    n = len(data) - 32
    if n <= 0:
        return []
    arr = np.frombuffer(data, dtype=np.uint8)
    sim = np.zeros(n + 1, dtype=np.uint16)
    for j in range(32):
        sim += POPCNT[arr[j : j + n + 1] ^ ref[j]]
    match = 256 - sim  # 일치 비트 수 (총 256비트)
    return match


def iso_files():
    """iso_files.txt 재사용 (없으면 scan_sjis.py 먼저 실행)."""
    path = os.path.join(OUT_DIR, "iso_files.txt")
    files = []
    with open(path, encoding="utf-8") as f:
        next(f)
        for line in f:
            m = re.match(r"\s*(\d+)\s+(\d+)\s+([\d,]+)\s+(\S+)", line)
            if m:
                lba, _, size, name = m.groups()
                files.append((name, int(lba), int(size.replace(",", ""))))
    return files


def main():
    refs = {ch: [ref_bitmap(ch, dy) for dy in (-2, -1, 0, 1)] for ch in REF_CHARS}
    best_global = []
    for name, lba, size in iso_files():
        if name.startswith("/XA/") or "DUMMY" in name or "DMY" in name:
            continue
        data = extract(lba, size)
        for ch, variants in refs.items():
            for dy_i, ref in enumerate(variants):
                m = scan(data, ref)
                if len(m) == 0:
                    continue
                top = int(m.max())
                if top >= 210:  # 256비트 중 82% 이상 일치
                    off = int(m.argmax())
                    best_global.append((top, name, off, ch, dy_i - 2))
    best_global.sort(reverse=True)
    print("일치율 상위 (256비트 중 일치 비트 수):")
    for top, name, off, ch, dy in best_global[:20]:
        print(f"  {top:3d}/256 ({top / 2.56:.0f}%)  {name} +0x{off:X}  [{ch}, dy={dy}]")
    if not best_global:
        print("  82% 이상 일치 없음 — 폰트가 압축돼 있거나 다른 형식(4bpp/12px 등)일 가능성")


if __name__ == "__main__":
    main()
