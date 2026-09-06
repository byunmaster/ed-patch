#!/usr/bin/env python3
"""**이주로 비운 자리를 아직 가리키는 참조가 있나** — 그리고 우리가 남의 인자를 덮었나.

    python3 tools/check_stale_refs.py

## 왜 있나 (pc98-ed1 중계 2026-09-07)

pc98 이 **남의 분기 주소를 덮어쓰던** 자리를 찾았다 — 덤퍼가 `<0x20` 만 제어코드로 보고
건너뛰는데, **분기 옵코드의 주소 바이트가 `>=0x20` 이면 다음 텍스트 런의 머리로 딸려
들어온다.** 문안을 쓰면 점프가 쓰레기 주소로 가 **진행이 깨진다.**

우리 축은 둘이다:

1. **머리 바이트가 남의 것인가** — 우리는 **포인터가 가리키는 자리에만** 쓴다. 머리가
   포인터 대상이면 그건 게임 자신이 「여기가 문자열 시작」이라고 말한 것이라 남의 인자일
   수 없다. ⇒ **포인터 없는 블록(핀)에 쓰는 일이 없어야 한다.**
2. **비운 자리를 아직 누가 보나** — 이주하면 원래 자리에 옛 바이트가 남는다. 우리가 아는
   참조(`ptr_at`)는 새 자리로 돌리지만, **덤프가 못 찾은 참조**가 있으면 그쪽은 옛 자리를
   계속 읽는다. ⇒ 빌드 이미지의 **모든 BE32** 를 훑어 비운 구간을 가리키는 것이 있나 본다.

⚠ 라운드트립(자리·디코드)은 이 축을 **안 본다** — 덤프가 원본과 같은지만 보기 때문이다.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import patch_scn


def check():
    """`(핀에 쓴 블록, 비운 블록 수, 옛 자리를 가리키는 미지의 참조)`."""
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if not os.path.exists(dst):
        raise SystemExit(f"먼저 빌드한다 — {dst} 가 없다")
    f1, m1 = common.open_image()
    f2, m2 = common.open_image(dst)
    pinned, vac_n, stale = [], 0, []
    try:
        canon = patch_scn.augment_names(patch_scn.load_canon(quiet=True), m1)
        for name, _l, _s in common.iso_files(m1):
            if not patch_scn.SCN_RE.match(name):
                continue
            got = patch_scn.load(name)
            if not got:
                continue
            base, ent = got
            built = bytes(common.extract(name, m2))
            sites = patch_scn.sites_for(name)
            mine = patch_scn.owned_elsewhere(name)
            vac, known = [], set()
            for e in ent:
                off = int(e["file_offset"], 16)
                pa = e.get("ptr_at")
                if not pa:
                    # ① 포인터가 없는데 우리 문안이 붙으면 **머리가 남의 것일 수 있다**
                    if off not in mine and patch_scn.canon_of(
                        canon, e.get("text", ""), sites.get(off)
                    ):
                        pinned.append((name, off, (e.get("text") or "")[:20]))
                    continue
                known.update(int(p, 16) for p in pa)
                at = struct.unpack(">I", built[int(pa[0], 16) : int(pa[0], 16) + 4])[0] - base
                if at != off:
                    vac.append((off, off + len(bytes.fromhex(e["raw_hex"])) + 1))
            vac_n += len(vac)
            if not vac:
                continue
            for o in range(0, len(built) - 3, 2):
                if o in known:
                    continue
                v = struct.unpack(">I", built[o : o + 4])[0]
                if not (base <= v < base + len(built)):
                    continue
                t = v - base
                for a, b in vac:
                    if a <= t < b:
                        stale.append((name, o, t, a))
                        break
    finally:
        f1.close()
        f2.close()
    return pinned, vac_n, stale


def main():
    pinned, vac_n, stale = check()
    mark = "✅" if not (pinned or stale) else "❌"
    print(
        f"     {mark} 이주로 비운 블록 {vac_n:,} — 옛 자리를 가리키는 미지의 참조 {len(stale)}"
        f" · 포인터 없는 자리에 쓴 블록 {len(pinned)}"
    )
    for name, off, t, a in stale[:8]:
        print(f"        🔴 {name} 참조 0x{off:X} → 0x{t:X} (비운 블록 0x{a:X})")
    for name, off, t in pinned[:8]:
        print(f"        🔴 {name} 0x{off:X} 포인터 없는 자리에 썼다 — {t!r}")
    if pinned or stale:
        raise SystemExit("참조가 옛 자리를 보거나, 포인터 없는 자리에 썼다 — 진행이 깨질 수 있다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
