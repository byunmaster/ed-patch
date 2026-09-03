"""PS1 TIM 그림 — 읽기/쓰기의 유일한 통로.

타이틀 로고·버튼·창틀처럼 **글자가 그림으로 박힌 자리**를 다루려면 먼저 TIM 을 열어야 한다.
규격은 공개돼 있다(psx-spx):

```
00  u32 0x00000010          매직
04  u32 flags               하위 3비트 = bpp 모드(0=4bpp 1=8bpp 2=16bpp 3=24bpp), 8비트 = CLUT 있음
[CLUT 블록]  u32 크기 · u16 x,y · u16 w,h · u16[w*h]   16비트 색 ×(팔레트 수)
[픽셀 블록]  u32 크기 · u16 x,y · u16 w,h · u16[w*h]   ⚠ w 는 **16비트 워드 수**다
```

🔴 **w 가 픽셀 수가 아니다.** 4bpp 면 실제 가로는 `w*4`, 8bpp 면 `w*2` 다. 이걸 헷갈리면
   그림이 가로로 접혀 나오는데 「압축이 덜 풀렸나」로 오진하기 쉽다.

⚠ 색은 15비트 BGR + STP 비트다(`b5 g5 r5 a1`). 우리가 다시 쓸 때 **STP 를 보존**한다 —
  그게 투명·반투명을 정하므로, 0 으로 뭉개면 배경이 까맣게 찍힌다.

⚠ **원본 그림은 커밋하지 않는다.** 미리보기 PNG 는 `work/review/` 로만 나간다.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MAGIC = 0x00000010
BPP = {0: 4, 1: 8, 2: 16, 3: 24}


class TimError(Exception):
    pass


def parse(data, off=0):
    """{bpp, clut, pal_w, pal_h, x, y, w, h, pix, end} — 실패하면 TimError."""
    if off + 8 > len(data):
        raise TimError("너무 짧다")
    magic, flags = struct.unpack_from("<II", data, off)
    if magic != MAGIC:
        raise TimError(f"매직이 아니다 0x{magic:08X}")
    mode = flags & 7
    if mode not in BPP:
        raise TimError(f"모르는 bpp 모드 {mode}")
    p = off + 8
    clut = None
    pal_w = pal_h = 0
    if flags & 8:
        (blk,) = struct.unpack_from("<I", data, p)
        cx, cy, pal_w, pal_h = struct.unpack_from("<4H", data, p + 4)
        if blk != pal_w * pal_h * 2 + 12 or not (0 < pal_w <= 256 and 0 < pal_h <= 256):
            raise TimError(f"팔레트 블록이 안 맞는다 blk={blk} {pal_w}x{pal_h}")
        clut = data[p + 12 : p + blk]
        p += blk
    (blk,) = struct.unpack_from("<I", data, p)
    x, y, w, h = struct.unpack_from("<4H", data, p + 4)
    # 🔴 **블록 크기와 w·h 가 맞아야 한다.** 이 검산이 없으면 매직만 우연히 맞는 자리가
    #    65792×32896 같은 값으로 통과한다(실측: `.TI3` 멤버 여럿이 그렇게 걸렸다).
    if blk != w * h * 2 + 12 or not (0 < w <= 1024 and 0 < h <= 1024):
        raise TimError(f"픽셀 블록 크기가 안 맞는다 blk={blk} w={w} h={h}")
    pix = data[p + 12 : p + blk]
    end = p + blk
    if end > len(data):
        raise TimError("픽셀 블록이 잘렸다")
    return {
        "bpp": BPP[mode],
        "clut": clut,
        "pal_w": pal_w,
        "pal_h": pal_h,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "pix": pix,
        "start": off,
        "end": end,
    }


def width(t):
    """실제 가로 픽셀 — `w` 는 16비트 워드 수다(🔴 위 머리말)."""
    return t["w"] * {4: 4, 8: 2, 16: 1, 24: 2 / 3}[t["bpp"]]


def rgba(c):
    """15비트 BGR+STP → (r, g, b, a). STP 규약은 psx-spx 를 따른다."""
    r = (c & 0x1F) << 3
    g = ((c >> 5) & 0x1F) << 3
    b = ((c >> 10) & 0x1F) << 3
    stp = (c >> 15) & 1
    a = 0 if (c == 0 and not stp) else 255
    return (r | r >> 5, g | g >> 5, b | b >> 5, a)


def best_palette(t):
    """가장 볼 만한 팔레트 번호 — **색이 제일 다양한 것**.

    ⚠ 4bpp·8bpp 그림은 팔레트를 여러 벌 들고 있고 **0번이 비어 있는 경우가 흔하다**
      (실측: 0번으로 그렸더니 새하얀 판이 나왔다). 「0번이 기본」이라고 두면 그림을 못 본다.
    """
    if t["clut"] is None or t["bpp"] not in (4, 8):
        return 0
    n = 16 if t["bpp"] == 4 else 256
    best, score = 0, -1
    for p in range(max(1, t["pal_h"])):
        base = p * n * 2
        chunk = t["clut"][base : base + n * 2]
        if len(chunk) < 4:
            break
        cols = {chunk[i : i + 2] for i in range(0, len(chunk), 2)}
        if len(cols) > score:
            best, score = p, len(cols)
    return best


def to_image(t, palette=None):
    """PIL Image (RGBA). 팔레트를 안 주면 **가장 색이 다양한 벌**을 고른다."""
    if palette is None:
        palette = best_palette(t)
    from PIL import Image

    w, h = int(width(t)), t["h"]
    img = Image.new("RGBA", (w, h))
    px = img.load()
    if t["bpp"] in (4, 8):
        if t["clut"] is None:
            raise TimError("팔레트가 없는 색인 그림")
        n = 16 if t["bpp"] == 4 else 256
        base = palette * n * 2
        pal = [
            rgba(struct.unpack_from("<H", t["clut"], base + i * 2)[0])
            for i in range(min(n, (len(t["clut"]) - base) // 2))
        ]
        for yy in range(h):
            row = t["pix"][yy * t["w"] * 2 : (yy + 1) * t["w"] * 2]
            for xx in range(w):
                if t["bpp"] == 4:
                    b = row[xx >> 1] if (xx >> 1) < len(row) else 0
                    idx = (b & 0xF) if xx % 2 == 0 else (b >> 4)
                else:
                    idx = row[xx] if xx < len(row) else 0
                px[xx, yy] = pal[idx] if idx < len(pal) else (0, 0, 0, 0)
    else:
        for yy in range(h):
            for xx in range(w):
                o = (yy * t["w"] + xx) * 2
                if o + 2 > len(t["pix"]):
                    break
                px[xx, yy] = rgba(struct.unpack_from("<H", t["pix"], o)[0])
    return img


def find_all(data):
    """[(오프셋, 정보)] — 블롭 안의 TIM 을 전부. 매직으로 훑고 **규격으로 거른다**."""
    out = []
    i = 0
    while True:
        i = data.find(b"\x10\x00\x00\x00", i)
        if i < 0:
            return out
        try:
            t = parse(data, i)
        except (TimError, struct.error):
            i += 4
            continue
        if t["h"] and t["w"] and t["end"] - i > 32:
            out.append((i, t))
            i = t["end"]
        else:
            i += 4
