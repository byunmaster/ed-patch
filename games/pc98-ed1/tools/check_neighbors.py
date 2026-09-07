#!/usr/bin/env python3
"""표에서 **이웃은 다 넣었는데 자기만 빠진** 자리를 찾는다.

🔴 왜 필요한가 — 2026-09-07 에 유저가 「한글은 나오는데 빈칸이 있다」고 했다. 그때 시스템
   자리는 **371/371** 이었다. 문제는 분모였다 — 덤퍼가 두 글자를 안 떠서 `はい`·`強さ`·
   `ロー`·주문 넷이 **목록에 아예 없었다.** 커버리지는 **분모가 맞을 때만** 뜻이 있다.

   ⇒ 분모를 의심하는 축이 이것이다. 주문 표 스물아홉 중 **넷만** 일본어로 남아 있었는데,
   표를 나란히 놓고 보니 한눈에 보였다. 「이웃이 다 있는데 자기만 없다」는 **빠뜨림의
   냄새**다(원문 그대로 두기로 한 자리는 대개 이웃도 같이 남는다).

## 게이트다

여기 걸리는 건 대개 진짜 빠뜨림이라 **실패로 친다.** 일부러 원문으로 두는 자리가 생기면
`script/sys.json` 에 `"keep_jp": true` 로 적어 빼 둔다 — 판단을 코드가 아니라 정본에 남긴다.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import patch_sys

JP = re.compile(r"[ぁ-んァ-ヶ一-鿿]")
NEED = 3  # 이웃 넷 중 몇이 정본에 있으면 「표 한복판」으로 보나


def main() -> int:
    canon = patch_sys.load()
    bad = []
    for disk in patch_sys.DISKS:
        site = patch_sys.sites(disk)
        offs = sorted(site)
        for i, o in enumerate(offs):
            k = f"{disk}:{o:#x}"
            v = canon.get(k)
            if v is not None or not JP.search(site[o].get("t", "")):
                continue
            if canon.get(k, {}).get("keep_jp"):
                continue
            nb = [offs[j] for j in (i - 2, i - 1, i + 1, i + 2) if 0 <= j < len(offs)]
            done = sum(1 for x in nb if f"{disk}:{x:#x}" in canon)
            if done >= NEED:
                bad.append((k, site[o]["n"], site[o]["t"], done, len(nb)))
    if not bad:
        print("  ✅ 표 한복판에 빠뜨린 자리 없음")
        return 0
    print(f"  🔴 이웃은 다 넣었는데 자기만 빠진 자리 {len(bad)}")
    for k, n, t, d, m in bad:
        print(f"     {k:18s} n={n:3d} 이웃 {d}/{m}  {t[:44]!r}")
    print('     ⚠ 일부러 원문으로 두는 자리면 `sys.json` 에 "keep_jp": true 로 적어라')
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
