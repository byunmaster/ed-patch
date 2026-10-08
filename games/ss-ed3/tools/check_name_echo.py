#!/usr/bin/env python3
"""**화자 이름이 본문에서 또 나가는가** — 이름창이 제 줄에 이름을 찍는데 본문 첫 줄이 그 이름으로 다시 시작하는 자리.

    python3 games/ss-ed3/tools/check_name_echo.py        # 게이트(0건)
    python3 games/ss-ed3/tools/check_name_echo.py -v     # 자리마다

PS1(ED1·ED2)은 원문이 이름을 제 창에 두는 꼴과 본문 안에 두는 꼴을 섞어 써서 화면에 「소니아소니아가」가 나갔다.
이 게임의 이름창은 블록 머리(`02 <화자>`)가 정하고 본문엔 이름이 안 들어가므로 **같은 사고는 구조적으로 안 난다** —
남는 건 번역이 이름표 꼴(「쥬리오: …」「크리스 「…」」)을 본문에 옮겨 쓰는 사고뿐이다. 그걸 재서 **0 으로 못 박는다**.

화자 번호: 0~13 = 파티원(`reinsert_battle.NAMES`, 사전 person), 0x14 이상 = 그 맵의 이름표 칸(`name_slots`) 순서.
그 밖(0x0e~0x13 전역 인물·화자 없음)은 이름을 모르니 분모에서 뺀다 — 몇 줄을 뺐는지도 찍는다.
"""

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import mapfile as M
import reinsert as R
import reinsert_battle as RB

SEP = ":：「『"


def scan():
    """`(분모, 이름 모르는 줄, [(맵, 블록, 이름, 첫 줄)])`"""
    total = nolabel = 0
    hits = []
    with C.open_disc(1) as d:
        files = {n: (lba, size) for n, lba, size in d.files()}
        for p in sorted(glob.glob(os.path.join(C.OUT_DIR, "map_jp", "MAP*.json"))):
            stem = os.path.basename(p)[:-5]
            kr, _ = R.load_script(stem)
            if not kr:
                continue
            b = d.read_extent(*files[f"/MAP/{stem}.BIN"])
            bl = M.blocks(b)
            slots = sorted(R.name_slots(bl, b))
            for k, v in kr.items():
                head = bl[int(k)]["head"]
                if head[:2] not in ("02", "42"):
                    continue
                n = int(head[2:], 16)
                label = None
                if n < 14:
                    label = RB.NAMES.get(n)
                elif n >= 0x14 and n - 0x14 < len(slots):
                    label = kr.get(str(slots[n - 0x14]))
                if not label:
                    nolabel += 1
                    continue
                total += 1
                first = v.replace("\x0c", "\n").split("\n")[0].strip()
                if first.startswith(label) and (len(first) == len(label) or first[len(label)] in SEP):
                    hits.append((stem, k, label, first[:40]))
    return total, nolabel, hits


def main():
    total, nolabel, hits = scan()
    print(f"이름창 대사 {total:,} 줄 중 본문이 이름을 또 쓴 자리 {len(hits)} (이름을 몰라 뺀 {nolabel:,})")
    for h in hits if ("-v" in sys.argv or hits) else []:
        print(f"  ✗ {h[0]}#{h[1]}  [{h[2]}] {h[3]!r}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
