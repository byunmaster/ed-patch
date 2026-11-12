#!/usr/bin/env python3
"""선택지 창 폭 게이트(마스터 11-06 「가장 긴 항목에 맞춰서 가로길이 조절」) — 빌드 이미지의 `3B` 선택지 연산 열이 「가장 긴 항목 px → 맞춤 열」과 같은가.

    python3 tools/check_choice_cols.py --built <빌드 이미지.bin>

규칙은 `choice_cols.py` 머리말. 구운 글은 정본에서(`check_baked_layout.baked_pieces`), 열은 **이미지에서** 읽는다 — 빌드가 열 바이트를 못 썼거나
엉뚱한 자리에 썼으면 여기서 잡힌다(창 폭 ≥ 가장 긴 항목 + 여백 = 위반 0).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_baked_layout as C
import check_image_residue as R
import choice_cols
import common
import scriptmap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--built", required=True)
    a = ap.parse_args()
    baked = C.baked_pieces("ed3")
    iso = common.iso_files("ed3")
    orig = {}
    for path, (lba, size) in sorted(iso.items()):
        if not (path.startswith("/SCE") and path.endswith(".DAT")):
            continue
        data = common.read_lba("ed3", lba, size)
        try:
            ents = common.arc_parse(data)[1]
        except common.ArchiveError:
            continue
        for nm, off, sz in ents:
            orig[(os.path.basename(path), nm)] = data[off : off + sz]
    built = R.members(a.built)
    n = bad = 0
    for (path, nm), bm in sorted(built.items()):
        om = orig.get((path, nm))
        if om is None:
            continue
        key = os.path.basename(path).split(".")[0] + "_" + nm.replace("\\", "/").split("/")[-1].split(".")[0]
        try:
            info = scriptmap.parse(om)
        except Exception:
            continue
        for p, _cols, _r, ids in choice_cols.scan(om, info):
            texts = [baked.get(key, {}).get(i) for i in ids]
            if any(t is None for t in texts):
                continue  # 번역 없는 항목이 있는 창은 원판 열 유지
            n += 1
            px = max(choice_cols.item_px(t) for t in texts)
            want, got = choice_cols.need_cols(px), bm[p + 2] >> 1
            if want != got:
                bad += 1
                print(f"   🔴 {key}@{p}: 열 {got} ≠ 맞춤 {want} (가장 긴 항목 {px}px)")
    if not n:
        print("   🔴 번역된 선택지 창을 하나도 못 찾음 — 게이트가 비어 있다(키 불일치 의심)")
        return 1
    print(f"선택지 창 폭 [ed3] — 번역된 선택지 {n}곳 · 열이 맞춤과 다른 곳 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
