"""1bpp 글리프를 터미널에 그려 눈으로 확인한다 — 탐색기가 찾은 자리는 **반드시 본다**.

상관 점수는 후보를 좁힐 뿐 판정이 아니다(체크리스트 5).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import textenc


def render(buf, off, stride, width, rows=None):
    rows = rows or (stride * 8 // width)
    rowbytes = (width + 7) // 8
    out = []
    for r in range(rows):
        b = buf[off + r * rowbytes : off + (r + 1) * rowbytes]
        bits = "".join(f"{x:08b}" for x in b)[:width]
        out.append(bits.replace("0", "·").replace("1", "█"))
    return out


def packed_render(buf, off, stride, width, rows):
    """행이 바이트 경계에 안 맞는 밀착 패킹(예: 12×12 = 18B)."""
    bits = "".join(f"{x:08b}" for x in buf[off : off + stride])
    return [
        bits[r * width : (r + 1) * width].replace("0", "·").replace("1", "█") for r in range(rows)
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--off", type=lambda x: int(x, 0), required=True, help="글리프 0 의 오프셋")
    ap.add_argument("--stride", type=int, default=30)
    ap.add_argument("--width", type=int, default=16)
    ap.add_argument("--rows", type=int, default=0)
    ap.add_argument("--packed", action="store_true")
    ap.add_argument(
        "--chars", default="亜一口日本", help="이 글자들을 JIS 순차 색인으로 찾아 그린다"
    )
    ap.add_argument("--index", type=int, nargs="*", help="색인을 직접 준다")
    a = ap.parse_args()
    buf = open(a.path, "rb").read()
    order = textenc.jis_order()
    idx = {ch: i for i, ch in enumerate(order)}
    base_i = idx.get("亜", 0)
    targets = []
    if a.index:
        targets = [(str(i), i) for i in a.index]
    else:
        for ch in a.chars:
            if ch in idx:
                targets.append((ch, idx[ch] - base_i))
    rows = a.rows or (a.stride * 8 // a.width)
    for label, i in targets:
        o = a.off + i * a.stride
        if o < 0 or o + a.stride > len(buf):
            print(f"{label}: 범위 밖")
            continue
        art = (
            packed_render(buf, o, a.stride, a.width, rows)
            if a.packed
            else render(buf, o, a.stride, a.width, rows)
        )
        print(f"{label}  @0x{o:X}")
        for line in art:
            print("   " + line)


if __name__ == "__main__":
    main()
