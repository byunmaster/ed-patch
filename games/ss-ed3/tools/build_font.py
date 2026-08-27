"""`KANJI12.FON` 에 한글 글리프를 굽는다 — 크기 불변, 안 쓰는 슬롯만 덮는다.

    python3 games/ss-ed3/tools/build_font.py            # work/derived/KANJI12.FON
    python3 games/ss-ed3/tools/build_font.py --preview 가한글

원본 잉크가 **0~10행**(실측: 1,638/1,833 글리프가 0행에서 시작, 1,589 가 10행에서 끝)이라
Galmuri11 을 `dy=-3` 으로 얹으면 베이스라인이 그대로 맞는다.

🔴 **크기를 안 바꾼다.** 파일 하나를 통째로 교체하지만 바이트 수가 같아야 ISO 배치가 안
   흔들린다(`write_at` 이 그걸 단언한다).
⚠ **덮는 자리는 `hangul_map.json` 정본만** — 「지금 계산한 빈 슬롯」이 아니다. 소재가 늘면
   빈 슬롯이 밀리는데, 정본을 읽으면 이미 넣은 문안이 안 깨진다.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import common as C
import font as F
import hangul_map as H

from shared import fonts

OUT = os.path.join(C.OUT_DIR, "KANJI12.FON")
DY = -3  # 원본 잉크 0~10행에 맞춘 Galmuri11 보정
DX = 1  # 🔴 **왼쪽으로 한 칸 붙어 있던 걸 띄운다.**
#   Galmuri11 은 12 칸을 왼쪽부터 채워 **2,350 자 전부 왼쪽 여백이 0** 이었다(실측
#   2026-08-27). 원본 한자는 왼쪽에 한 칸을 비워 두므로, 창 안쪽 경계에 글자가 닿아
#   **잘린 것처럼 보인다**(유저가 스탯 창에서 짚었다). 오른쪽 여백은 1 칸이 46% ·
#   2 칸이 54% 라 **한 칸 밀어도 잘리지 않는다.**
#   ⚠ 슬롯 배정(`hangul_map.json`)은 안 건드리므로 이미 넣은 문안이 안 깨진다.


def shift_right(g, width, rows, stride, dx=DX):
    """글리프 비트를 오른쪽으로 `dx` 칸 민다 — 폭은 그대로다."""
    bits = "".join(f"{b:08b}" for b in g)
    out = []
    for r in range(rows):
        row = bits[r * width : (r + 1) * width]
        out.append("0" * dx + row[: width - dx])
    s = "".join(out)
    s += "0" * (stride * 8 - len(s))
    return bytes(int(s[i : i + 8], 2) for i in range(0, stride * 8, 8))


def build(disc=1):
    """`(새 폰트 bytes, 못 찾은 글자)` — 원본과 크기가 같다."""
    base, _ = F.load(disc)
    table = H.load()
    glyphs, missing = fonts.convert_chars(
        list(table), dy=DY, rows=F.ROWS, packer=fonts.pack18, width=F.CELL
    )
    out = bytearray(base)
    for ch, idx in table.items():
        g = shift_right(glyphs[ch], F.CELL, F.ROWS, F.STRIDE)
        assert len(g) == F.STRIDE, (ch, len(g))
        out[idx * F.STRIDE : (idx + 1) * F.STRIDE] = g
    assert len(out) == len(base), (len(out), len(base))
    return bytes(out), missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", type=int, default=1, choices=C.DISCS)
    ap.add_argument("--preview", help="이 글자들을 원본 폰트 격자로 그려 본다")
    a = ap.parse_args()

    data, missing = build(a.disc)
    if a.preview:
        table = H.load()
        rows = [F.unpack(data, table[ch]) for ch in a.preview]
        for r in range(F.ROWS):
            print("  " + "   ".join("".join("█" if v else "·" for v in b[r]) for b in rows))
        return
    os.makedirs(C.OUT_DIR, exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(data)
    print(f"한글 {len(H.load()):,}자 주입 · 크기 {len(data):,}B (불변) → {OUT}")
    if missing:
        print(f"⚠ 글리프가 없는 글자 {len(missing)}: {''.join(missing[:20])}")
        raise SystemExit(1)
    print("✅ 빠진 글자 없음")


if __name__ == "__main__":
    main()
