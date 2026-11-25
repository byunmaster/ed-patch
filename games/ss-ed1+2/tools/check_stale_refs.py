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

3. **바꾼 칸의 안쪽을 누가 보나**(11-07, PCE II 실측 결함 부류) — 원판 문자열 칸 안쪽에 코드가 읽는 표 바이트가 겹쳐 있으면, 칸을 비우거나
   새 문자열을 앉히는 순간 그 읽기가 조용히 깨진다. ⇒ 원본의 모든 BE32 중 **우리가 바이트를 바꾼 칸의 안쪽**(시작 다음 ~ 끝 NUL)을 가리키는 것이 없어야 한다.
   (측정: 이진 파일 포함 93 파일 · 15,501 칸 중 안쪽 참조 43 = 전부 안 바뀐 데이터 3곳이라 위반 0. 한계: 절대 주소 참조만 본다 — `기준+인덱스` 읽기는 못 본다.)

⚠ 라운드트립(자리·디코드)은 이 축을 **안 본다** — 덤프가 원본과 같은지만 보기 때문이다.
"""

import bisect
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
    pinned, vac_n, stale, interior = [], 0, [], []
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
            # 입장 배너 호출부 리터럴은 **일부러 새 자리(전용 표·끼움 루틴)로 돌린 것**이다(`patch_ui.BANNER_TABLES` · `ED2_BANNER_HOOK_LIT`) —
            #   그 자리가 이주로 비운 블록이라 옛 자리 참조로 오인된다. 돌린 곳은 patch_ui 가 선언한 이 리터럴들뿐이다.
            import patch_ui

            known.update(patch_ui.BANNER_TABLES.get(name, {}).get("ptrs", ()))
            known.update(off for off, _orig in patch_ui.BANNER_HOOKS.get(name, {}).values())
            # 끼움·보정 루틴과 칸별 [위치, 보정] 표는 **코드·바이트 표**라 4B 씩 읽으면 우연히 주소 꼴이 나올 수 있다(보정이 바뀌면 달라진다) —
            #   리터럴이 가리키는 그 덩이 바이트 범위는 포인터 검사에서 뺀다. 범위는 patch_ui 가 정하는 길이 그대로다.
            skip_rng = []
            if name in patch_ui.BANNER_HOOKS:
                _a, _b = patch_ui.banner_hook_codes(name, bytes(2 * patch_ui.BANNER_HOOK_ROWS[name]["n"]))
                for kind, blob in (("strlen", _a), ("draw", _b)):
                    lit = patch_ui.BANNER_HOOKS[name][kind][0]
                    st = struct.unpack(">I", built[lit : lit + 4])[0] - base
                    skip_rng.append((st, st + len(blob)))
            # ③ 우리가 바이트를 바꾼 문자열 칸의 **안쪽**(시작 다음 바이트부터 끝 NUL 까지)을 원본에서 가리키는 참조 — 문자열이 아니라
            #    표·인자로 읽히는 겹친 칸일 수 있다(PCE II 실측: 칸 안쪽에 코드가 읽는 표 바이트가 겹쳐 있었다). 안 바뀐 칸은 안 센다.
            orig = bytes(common.extract(name, m1))
            refs = sorted(
                {
                    struct.unpack(">I", orig[o : o + 4])[0] - base
                    for o in range(0, len(orig) - 3, 2)
                    if base <= struct.unpack(">I", orig[o : o + 4])[0] < base + len(orig)
                }
            )
            for e in ent:
                off0 = int(e["file_offset"], 16)
                n0 = len(bytes.fromhex(e["raw_hex"])) + 1
                if built[off0 : off0 + n0] != orig[off0 : off0 + n0]:
                    i = bisect.bisect_right(refs, off0)
                    while i < len(refs) and refs[i] < off0 + n0:
                        interior.append((name, off0, refs[i]))
                        i += 1
            for e in ent:
                off = int(e["file_offset"], 16)
                pa = e.get("ptr_at")
                if not pa:
                    # ① 포인터가 없는데 우리 문안이 붙으면 **머리가 남의 것일 수 있다**
                    if off not in mine and patch_scn.canon_of(
                        canon, e.get("text", ""), sites.get(off), path=name
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
                if o in known or any(x <= o < y for x, y in skip_rng):
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
    return pinned, vac_n, stale, interior


def main():
    pinned, vac_n, stale, interior = check()
    mark = "✅" if not (pinned or stale or interior) else "❌"
    print(
        f"     {mark} 이주로 비운 블록 {vac_n:,} — 옛 자리를 가리키는 미지의 참조 {len(stale)}"
        f" · 포인터 없는 자리에 쓴 블록 {len(pinned)} · 바뀐 칸 안쪽을 가리키는 참조 {len(interior)}"
    )
    for name, off, t in interior[:8]:
        print(f"        🔴 {name} 바뀐 칸 0x{off:X} 안쪽 0x{t:X} 를 가리키는 참조(원본)")
    for name, off, t, a in stale[:8]:
        print(f"        🔴 {name} 참조 0x{off:X} → 0x{t:X} (비운 블록 0x{a:X})")
    for name, off, t in pinned[:8]:
        print(f"        🔴 {name} 0x{off:X} 포인터 없는 자리에 썼다 — {t!r}")
    if pinned or stale or interior:
        raise SystemExit("참조가 옛 자리를 보거나, 포인터 없는 자리에 썼다 — 진행이 깨질 수 있다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
