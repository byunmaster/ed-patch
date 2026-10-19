#!/usr/bin/env python3
"""**최종 이미지** 시스템 문안 포인터 게이트 — 시스템 문안(`patch_ui.sys_rows`)의 포인터가 **전부** 계획한 번역을 가리키나.

    python3 tools/check_sys_final.py            # 실패면 종료코드 1

🔴 왜(2026-10-19 qa r4 「는 동료를 불렀다」·「는 껍질에 틀어박혀 있다」): MON04 의 「…은(는) 검을 내리쳤다.」 자리에 **뒤 단계(`patch_scn`)가 같은 꼬리 주소부터 다른 문구를
   덮어써** 포인터 둘이 같은 곳(다른 문구)을 가리켰다 — 앞 문구의 꼬리 「쳤다.」만 남았다. 빌드·되읽기·남은 일본어 게이트가 전부 통과했다:
   `patch_ui.verify_sys` 는 ① **첫 포인터만** 보고 ② **자기 단계 직후**에만 돈다(뒤 단계가 덮어쓴 뒤는 아무도 안 본다).
⇒ 체인이 **끝난 최종 이미지**에서 모든 포인터를 따라가 읽는다. 단계 순서에 기대지 않는다.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "shared"))


def main():
    import common
    import font
    import patch_ui as U

    dst = os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.bin")
    if not os.path.exists(dst):
        raise SystemExit("시스템 포인터(최종): 빌드 이미지가 없다 — 먼저 빌드한다")
    _f, mm = common.open_image()
    sysm = U.sys_rows(mm)
    with open(U.HMAP, encoding="utf-8") as f:
        syl = json.load(f)["syllables"]
    inv = {font.sjis_of_index(i): c for c, i in syl.items()}
    _f2, mm2 = common.open_image(dst)
    files = {p: (l, s) for p, l, s in common.iso_files(mm2)}
    cache, bad, n = {}, [], 0
    for path, _lba, _size, at, _span, pre, kr, ptrs, _jp in sysm:
        if not ptrs or at in U.PINNED_INPLACE.get(path, ()):
            continue
        if path not in cache:
            lba, size = files[path]
            size = U._tails().get(path, (0, size))[1] or size
            cache[path] = common.read_extent(mm2, lba, size)
        d = cache[path]
        for q in ptrs:
            n += 1
            a = int.from_bytes(d[q : q + 4], "big") - U.ptr_base(path)
            if not 0 <= a < len(d):
                bad.append((path, q, kr, "포인터가 파일 밖"))
                continue
            j = a + len(pre)
            while j < len(d) and d[j] != 0:
                j += 1
            got = U.decode(d[a + len(pre) : j], inv)
            if got != kr:
                bad.append((path, q, kr, got))
    print(f"  시스템 포인터(최종 이미지) [{n:,}개] — 계획한 번역이 아닌 곳을 가리키는 포인터 {len(bad)}")
    for path, q, kr, got in bad[:20]:
        print(f"     ❌ {path[-12:]} 포인터 0x{q:X} — 계획 {kr!r} ≠ 실제 {got!r}")
    if bad:
        raise SystemExit(f"시스템 포인터 {len(bad)}개 — 같은 자리에 두 단계가 쓰지 않았나(`patch_scn._untouched` 꼬리)")


if __name__ == "__main__":
    main()
