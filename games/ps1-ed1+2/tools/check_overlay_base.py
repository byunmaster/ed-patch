#!/usr/bin/env python3
"""SCN 오버레이의 RAM 로드 주소를 **추정하지 않고 도출**해 정본 표와 대조한다.

재삽입은 블록을 옮기고 그것을 가리키는 `lui+addiu/ori` 를 다시 쓴다. 그 계산이 전부
`OVERLAY_RAM_BASE` 에 물려 있어서, 값이 틀리면 **모든 포인터가 같은 크기만큼 어긋난다** —
증상은 오타가 아니라 소프트락이다(구조 계약, `docs/reference/our-findings.md`).

**도출 방법.** 오버레이 안의 `lui+addiu/ori` 가 만드는 주소는 대사 블록 시작을 가리킬 때가
압도적으로 많다. 참조 주소마다 `base = addr − 블록오프셋` 후보를 세어 **최빈값**을 취하면
base 가 나온다. 알려진 값을 확인하는 게 아니라 데이터가 답을 낸다 — ED1 은 이 방법이
`0x8016A000` 을 정확히 재현하고(적중 92~97%), 그래서 ED2 의 답도 믿을 수 있다.

⚠ **ED2 는 ED1 과 다르다**(2026-08-11 도출): `0x80165000`. 13씬이 만장일치다. ED1 값으로
ED2 를 재삽입하면 20,480바이트씩 어긋난다. 처음엔 `OVERLAY_RAM_BASE` 하나로 두 게임을
덮고 있었다 — ED2 를 체인에 올리기 전에 잡아서 다행이었다.

⚠ 2위 후보가 `base − 0x40` 언저리로 나오는 건 정상이다(구조체 선두를 가리키는 참조).
씬10~13 은 적중률이 낮은데(31~63%) 작은 씬이라 오버레이 밖(ED.EXE 등)을 가리키는 참조가
섞여서다 — **최빈값은 그래도 흔들리지 않는다.**

  python3 tools/check_overlay_base.py          # 전 씬 도출 → 정본 대조
"""

import collections
import json
import os
import sys

import common
from common import MIPS_ADDIU, MIPS_ORI, OUT_DIR, iter_lui_pairs
from extract_scn import SCN_FILES

# 정본은 **쓰는 쪽**에 둔다 — 값을 검사기에 따로 적으면 둘이 어긋나도 아무도 모른다(DRY).
from reinsert_kr_pilot import OVERLAY_BASE

MIN_SHARE = 0.25  # 최빈값이 이보다 낮으면 도출 실패로 본다(참조가 너무 적은 씬)


def derive(name, lba, size):
    """(도출된 base, 그 base 로 오버레이 안을 가리키는 참조 수, 전체 참조 수) 또는 None."""
    path = os.path.join(OUT_DIR, "scn_jp", f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    offs = {int(e["file_offset"], 16) for e in doc["entries"] if e["kind"] == "block"}
    if not offs:
        return None
    data = common.extract(lba, size)
    refs = [a for _, _, _, a in iter_lui_pairs(data, (MIPS_ADDIU, MIPS_ORI))]
    votes = collections.Counter()
    for a in refs:
        for o in offs:
            b = a - o
            if 0x80000000 <= b < 0x80200000:  # PS1 메인 RAM
                votes[b] += 1
    if not votes:
        return None
    base, hits = votes.most_common(1)[0]
    inside = sum(1 for a in refs if 0 <= a - base < size)
    return base, hits, inside, len(refs)


def main():
    bad = 0
    print(f"{'씬':10} {'참조':>6} {'오버레이내':>10} {'도출 base':>11} {'최빈':>6} {'비율':>6}")
    for name, lba, size in SCN_FILES:
        got = derive(name, lba, size)
        if got is None:
            print(f"{name:10}  (scn_jp 덤프 없음 — 건너뜀)")
            continue
        base, hits, inside, total = got
        share = hits / max(inside, 1)
        want = OVERLAY_BASE.get(name[:3])
        ok = base == want and share >= MIN_SHARE
        bad += not ok
        mark = "" if ok else f"   ❌ 정본은 {want:X}" if base != want else "   ❌ 신뢰도 미달"
        print(f"{name:10} {total:>6} {inside:>10} {base:>11X} {hits:>6} {100 * share:>5.1f}%{mark}")
    print()
    for game, b in sorted(OVERLAY_BASE.items()):
        print(f"  {game} 오버레이 로드 주소 = 0x{b:08X}")
    if bad:
        print(f"\n❌ {bad}개 씬이 정본과 어긋난다 — 포인터 갱신이 통째로 빗나간다(소프트락).")
        return 1
    print("\n✅ 전 씬 정본 일치 — 재삽입 포인터 계산의 전제가 성립한다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
