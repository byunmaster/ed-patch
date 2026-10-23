#!/usr/bin/env python3
"""최종 이미지의 ED2MON 오버레이에 「안 채운 임시 버퍼를 strcat」 자리가 남았나(patch_ed2_stale_strcat 의 게이트).

남아 있으면 실패 — 몬스터 행동 문구가 호출 스택 찌꺼기를 달고 나간다(10-20 s94_09 「운이 [깨진 글리프] 떨어졌다」).
이미지가 없거나 패처·문안 소스보다 낡으면 「안 쟀다」로 실패한다.

  python3 tools/check_ed2_stale_strcat.py [--allow-stale]
"""

import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import check_pointer_audit as PA
from common import extract
from ed2_monster_review import MON
from patch_ed2_monster_lines import _live_group_lba
from patch_ed2_stale_strcat import find_sites


def main(argv):
    img = PA.image_path()
    why = PA.stale_reason(img, "--allow-stale" in argv)
    if why:
        print(f"  ❌ 안 쟀다 — {why}")
        return 1
    with contextlib.redirect_stdout(io.StringIO()):
        live = _live_group_lba(img)
    bad = []
    for g in sorted(MON):
        lba, size = live[g]
        buf = bytes(extract(lba, (size + 2047) // 2048 * 2048, path=img))
        bad += [(g, off) for off in find_sites(buf)]
    if bad:
        for g, off in bad:
            print(f"  ❌ ED2MON{g} {0x8014A000 + off:#x} — 안 채운 임시 버퍼를 strcat (호출 스택 찌꺼기가 문구에 붙는다)")
        return 1
    print("  ✅ ED2MON 안 채운 임시 버퍼 strcat 0곳")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
