"""
TIM 이미지 인벤토리 — 디스크에서 PS1 TIM 이미지를 스캔·렌더해 '글자 박힌 그래픽' 색출.

폰트 엔진으로 그려지는 대사(reinsert_kr_pilot)와 달리, 타이틀 로고·챕터 카드·메뉴처럼
이미지에 박힌 텍스트(baked text)는 그림 자체를 다시 그려야 한다(graphics-text 트랙).
이 도구는 그 대상을 찾기 위한 1단계 인벤토리.

TIM 포맷: 매직 `10 00 00 00` + flag(u32, 하위3비트=pmode 0:4/1:8/2:16/3:24bpp, bit3=CLUT)
 + (CLUT 블록) + 픽셀 블록(bsize u32, dx dy w h, 데이터). w는 16비트워드 폭.

매직이 흔해 오탐이 많으므로 블록 크기 정합(bsize == 12 + w*h*2)으로 강하게 거른다.
출력: out/tim_scan/contact_NNN.png (오프셋순 컨택트 시트), 육안으로 글자 이미지 선별.
"""

import os
import re
import struct

import numpy as np
from common import ORIG_BIN, OUT_DIR, SECTOR, USER_OFF, USER_SIZE
from PIL import Image, ImageDraw

OUT = os.path.join(OUT_DIR, "tim_scan")
PER_SHEET = 24


def user_stream():
    """디스크 전체의 유저 데이터(섹터당 2048B)를 이어붙인 스트림."""
    with open(ORIG_BIN, "rb") as f:
        f.seek(0, 2)
        nsec = f.tell() // SECTOR
        buf = bytearray()
        for i in range(nsec):
            f.seek(i * SECTOR + USER_OFF)
            buf += f.read(USER_SIZE)
    return bytes(buf)


def u16(a):
    return np.frombuffer(a[: len(a) // 2 * 2], dtype="<u2")


def parse_tim(buf, p):
    """오프셋 p의 TIM 파싱. 실패/오탐이면 None."""
    flag = struct.unpack_from("<I", buf, p + 4)[0]
    pmode, has_clut = flag & 7, (flag >> 3) & 1
    if pmode > 3:
        return None
    q, clut = p + 8, None
    if has_clut:
        bsize = struct.unpack_from("<I", buf, q)[0]
        if not 12 < bsize < 0x100000:
            return None
        cw = struct.unpack_from("<H", buf, q + 8)[0]
        ch = struct.unpack_from("<H", buf, q + 10)[0]
        clut = u16(buf[q + 12 : q + 12 + cw * ch * 2])
        q += bsize
    psize = struct.unpack_from("<I", buf, q)[0]
    if not 12 < psize < 0x200000:
        return None
    w = struct.unpack_from("<H", buf, q + 8)[0]
    h = struct.unpack_from("<H", buf, q + 10)[0]
    if not (0 < w <= 1024 and 0 < h <= 512) or abs(psize - (12 + w * h * 2)) > 4:
        return None
    bpp = {0: 4, 1: 8, 2: 16, 3: 24}[pmode]
    return {
        "off": p,
        "w": w * 16 // bpp,
        "h": h,
        "bpp": bpp,
        "clut": clut,
        "pix": buf[q + 12 : q + 12 + w * h * 2],
    }


def to_rgb(t):
    def c15(v):
        return ((v & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3)

    w, h, raw, clut = t["w"], t["h"], t["pix"], t["clut"]
    out = Image.new("RGB", (w, h))
    px = out.load()
    if t["bpp"] == 4:
        for i in range(min(w * h, len(raw) * 2)):
            b = raw[i // 2]
            idx = (b >> 4) if i % 2 else (b & 0xF)
            px[i % w, i // w] = c15(int(clut[idx]) if clut is not None and idx < len(clut) else 0)
    elif t["bpp"] == 8:
        for i in range(min(w * h, len(raw))):
            idx = raw[i]
            px[i % w, i // w] = c15(int(clut[idx]) if clut is not None and idx < len(clut) else 0)
    elif t["bpp"] == 16:
        arr = u16(raw)
        for i in range(min(w * h, len(arr))):
            px[i % w, i // w] = c15(int(arr[i]))
    return out


def scan(buf, min_w=128, min_h=40, skip_sizes=((128, 192),)):
    """유효 TIM 중 대형(글자 후보). 스프라이트 시트 크기는 제외."""
    out = []
    for m in re.finditer(rb"\x10\x00\x00\x00", buf):
        try:
            t = parse_tim(buf, m.start())
        except struct.error:
            t = None
        if t and t["w"] >= min_w and t["h"] >= min_h and (t["w"], t["h"]) not in skip_sizes:
            out.append(t)
    return out


def contact_sheets(cands):
    os.makedirs(OUT, exist_ok=True)
    cols = 4
    cw, chh = 340, 210
    for s in range(0, len(cands), PER_SHEET):
        sel = cands[s : s + PER_SHEET]
        rows = (len(sel) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cw, rows * chh), (20, 20, 30))
        d = ImageDraw.Draw(sheet)
        for i, t in enumerate(sel):
            img = to_rgb(t)
            if img.width > 320 or img.height > 184:
                img = img.resize((min(t["w"], 320), min(t["h"], 184)))
            x, y = (i % cols) * cw, (i // cols) * chh
            sheet.paste(img, (x + 4, y + 18))
            d.text(
                (x + 4, y + 2),
                f"0x{t['off']:X} {t['w']}x{t['h']} {t['bpp']}bpp",
                fill=(220, 220, 120),
            )
        path = os.path.join(OUT, f"contact_{s // PER_SHEET:03d}.png")
        sheet.save(path)
        print(f"  {path} ({len(sel)}개)")


def main():
    buf = user_stream()
    cands = scan(buf)
    from collections import Counter

    print(f"대형 유효 TIM {len(cands)}개 (스프라이트 128x192 제외)")
    print("크기 분포:", Counter((t["w"], t["h"]) for t in cands).most_common(12))
    contact_sheets(cands)
    print(f"→ {OUT} (컨택트 시트 육안으로 글자 이미지 선별)")


if __name__ == "__main__":
    main()
