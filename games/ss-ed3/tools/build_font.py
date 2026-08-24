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


def build(disc=1):
    """`(새 폰트 bytes, 못 찾은 글자)` — 원본과 크기가 같다."""
    base, _ = F.load(disc)
    table = H.load()
    glyphs, missing = fonts.convert_chars(
        list(table), dy=DY, rows=F.ROWS, packer=fonts.pack18, width=F.CELL
    )
    out = bytearray(base)
    for ch, idx in table.items():
        g = glyphs[ch]
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
