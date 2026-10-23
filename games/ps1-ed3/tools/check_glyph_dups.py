"""구운 롬의 글꼴에서 **서로 비트맵이 같은 글리프 쌍**을 센다 — 같은 쌍이 있으면 실패(허용 목록 제외).

  python3 tools/check_glyph_dups.py <굽은 이미지.bin>

왜: ss-ed1+2 에서 행 맞춤(dy)이 쉼표 꼬리 행을 잘라 쉼표가 마침표와 같은 그림이 됐고, 문안의 쉼표 수천 곳이 전부 마침표로
그려졌다(10-20). 원본 글꼴 파일만 보면 안 보인다 — **롬에서 읽어** 대조한다.
"""

import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import font

# 원판 글꼴에 이미 같은 그림인 쌍(전각 Ｉ·ｌ — 우리가 안 건드린 칸)
ALLOWED = {(46, 59)}


def dup_groups(exe, disc="ed3"):
    groups = collections.defaultdict(list)
    for c in range(font.glyph_count(exe, disc)):
        g = np.asarray(font.read_glyph(exe, c, disc), dtype=np.uint8)
        if g.any():
            groups[g.tobytes()].append(c)
    return [v for v in groups.values() if len(v) > 1]


def main(argv):
    binp = argv[1]
    tree = common.iso_tree(binp)[0]
    key = font.FONTS["ed3"]["exe"]
    lba, size = tree.get(key) or tree[key.lstrip("/")]
    exe = common.read_lba("ed3", lba, size, path=binp)
    bad = [g for g in dup_groups(exe) if tuple(g) not in ALLOWED]
    print(f"   구운 글리프 같은 비트맵 쌍 {len(bad)}개(허용 {len(ALLOWED)} 제외)")
    for g in bad:
        print("   🔴", g)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
