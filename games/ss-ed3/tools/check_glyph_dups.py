"""구운 글리프끼리 비트맵이 같으면 실패 (게이트) — 쉼표가 마침표로 보이는 부류.

    python3 games/ss-ed3/tools/check_glyph_dups.py

ss-ed1+2 에서 글꼴을 구울 때 행 맞춤으로 쉼표 꼬리 행이 잘려 쉼표 3,983곳이 마침표로 그려졌다(10-20).
여기서는 **구운 이미지에서** 글꼴을 읽어(원본 글꼴 파일이 아니다) 둘을 본다:
  · `ASCII.FON` 의 반각 글리프(0x21~0x7E) — 비트맵이 같은 쌍. 원판부터 같은 `I`·`l`·`|` 만 허용한다.
  · `KANJI12.FON` 의 전각 부호(、。，．・：；？！…ー～「」『』（）‘’“”) — 서로 같은 쌍.
⚠ 원판 KANJI12 에는 안 쓰는 기호·라틴·그리스 글리프끼리 같은 쌍이 19 개 있다(문안에 안 나온다) — 부호 목록만 본다.
이미지가 없으면 건너뛴다.
"""

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import common as C
import font as F

ASCII_OK = [{"I", "l", "|"}]  # 원판부터 같은 꼴
FULL = "、。，．・：；？！…ー～「」『』（）‘’“”"


def dup_groups(glyphs):
    """`{이름: 비트맵 bytes}` → 같은 비트맵끼리 묶은 이름 목록(둘 이상인 것만). 빈 글리프는 뺀다."""
    inv = collections.defaultdict(list)
    for name, b in glyphs.items():
        if any(b):
            inv[b].append(name)
    return [v for v in inv.values() if len(v) > 1]


def check_image(img):
    """`[(범주, 같은 쌍 묶음)]` — 허용 목록 밖의 것만."""
    with C.Disc(img, user_off=C.USER_OFF) as d:
        asc, fon = d.read(F.FON_ASCII), d.read(F.FON_KANJI)
    bad = []
    half = {chr(c): asc[c * F.ASCII_STRIDE : (c + 1) * F.ASCII_STRIDE] for c in range(0x21, 0x7F)}
    bad += [("반각", g) for g in dup_groups(half) if set(g) not in ASCII_OK]
    full = {}
    for ch in FULL:
        i = F.jis_index(ch)
        if i is not None:
            full[ch] = fon[i * F.STRIDE : (i + 1) * F.STRIDE]
    bad += [("전각", g) for g in dup_groups(full)]
    return bad, len(half) + len(full)


def main():
    fails = 0
    for disc in (1, 2):
        img = build.out_paths(disc)[0]
        if not os.path.exists(img):
            print(f"  ⏭ disc{disc} 이미지 없음 — 건너뛴다")
            continue
        bad, n = check_image(img)
        print(f"  disc{disc} 부호 글리프 {n}개 · 같은 비트맵 쌍 {len(bad)}")
        for kind, g in bad:
            print(f"    🔴 {kind}: {' = '.join(g)}")
        fails += len(bad)
    if fails:
        print("🔴 구운 글리프끼리 비트맵이 같다 — 글꼴 굽기(행 맞춤·잘림)를 본다")
        sys.exit(1)
    print("  ✅ 구운 부호 글리프에 같은 비트맵 쌍 없음")


if __name__ == "__main__":
    main()
