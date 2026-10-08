#!/usr/bin/env python3
"""**지명 칸에 반각이 새지 않았나 · 길이가 짝수인가** — 최종 이미지에서 되읽는다.

    python3 tools/check_place_fields.py [--show N]

## 왜 있나 (마스터 판정 (나), 2026-09-27)

PS1 은 지명에 반각 공백이 끼어 **홀수 길이**가 되자 실내 HUD 가 NUL 을 놓쳐 꼬리가 비쳤다
(2바이트 단위 종결 판정). 새턴은 그 코드가 없다는 걸 값과 화면으로 봤지만(11B 「크루즈 마을」
온전), 마스터 판단은 **안전하게 간다**다 — 지명 칸은 전부 전각(2B 단위)이고, 공백도 전각이다.
그 약속을 문서가 아니라 **되읽기**로 지킨다.

- 대상: `patch_ui.rows()` 의 지명 표(`dump_ui.GLOSSARY_TABLES`) + `patch_ui.scn_rows()` 의 씬 지명 헤더.
- 판정: NUL 까지를 2B 단위로 걷는다. 선행 바이트가 아닌 1B 가 끼면 **반각 누출**, 바이트 수가
  홀수면 **홀수 길이**. 둘 다 0 이어야 한다.
- 🔴 **민감도** — 읽은 글이 우리가 쓴 이름과 같은지도 본다. 엉뚱한 자리를 읽으면 「반각 0」이
  거짓말이 된다(체크리스트 4-B).
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import dump_ui
import patch_ui
from check_name_tables import _decode, _inv_map

PLACE_TABLES = {t[0] for t in dump_ui.GLOSSARY_TABLES}


def _lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC


def _walk(raw):
    """→ (반각 누출 수, 홀수 길이인가)."""
    i = half = 0
    while i < len(raw):
        if _lead(raw[i]):
            i += 2
        else:
            half += 1
            i += 1
    return half, len(raw) % 2 == 1


def targets():
    """`[(ISO 경로, 파일 안 오프셋, 칸 바이트, 우리 이름, 자리)]` — 원본에서 유도한다."""
    out = []
    for key, name, i, at, stride, _jp, kr in patch_ui.rows():
        if name in PLACE_TABLES and kr:
            out.append((dump_ui.FILES[key], at, stride, kr, f"{key}/{name}[{i}]"))
    f0, mm0 = common.open_image()
    try:
        for path, _lba, _size, s, fl, _jp, kr, *_ in patch_ui.scn_rows(mm0):
            out.append((path, s, fl, kr, f"{path} 헤더 0x{s:X}"))
    finally:
        mm0.close()
        f0.close()
    return out


def check():
    img = glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))
    if not img:
        return None
    inv = _inv_map()
    rows = targets()
    f1, mm1 = common.open_image(img[0])
    leak, odd, wrong = [], [], []
    try:
        files = {p: (l, s) for p, l, s in common.iso_files(mm1)}
        cache = {}
        for path, at, room, kr, where in rows:
            if path not in cache:
                cache[path] = common.read_extent(mm1, *files[path])
            d = cache[path]
            z = d.find(b"\x00", at, at + room)
            raw = d[at : z if z >= 0 else at + room]
            # 🔴 **도트 글리프 예외**(마스터 지시 2026-10-05) — 「늑대의입」은 씬 헤더에서
            #   저장 바이트가 막혀 PS1 처럼 반각 도트 6B 로 적는다(`patch_ui.DOTART_PLACES`).
            #   이 자리는 **의도적으로 반각**이라 위 둘(전각 짝수 약속)을 어겨도 정상이다 —
            #   다만 쓴 바이트가 정확히 그 6개일 때만 봐준다, 아니면 평소대로 전부 잡는다.
            if kr in patch_ui.DOTART_PLACES and raw == patch_ui.DOTART_PLACES[kr]:
                continue
            half, is_odd = _walk(raw)
            if half:
                leak.append((where, kr, raw))
            if is_odd:
                odd.append((where, kr, raw))
            if _decode(raw, inv) != kr:
                wrong.append((where, kr, _decode(raw, inv)))
    finally:
        mm1.close()
        f1.close()
    return len(rows), leak, odd, wrong


def table_base_refs():
    """🔴 **표 기준 포인터가 안 움직였나** — 지명 표를 가리키는 코드 풀 값(`적재 주소 + 표 시작 − 한 칸 … + 표 시작`)이
    빌드에서 원본과 같아야 한다. 표 앞 한 칸이 시스템 문자열로 잡혀 이주하면 기준 포인터가 끌려가
    **표 전체가 엉뚱한 곳을 읽는다**(ED2 엘아스타 칸, 2026-10-08 — 정적 게이트가 하나도 안 울었다).
    → `(깨진 수, 본 수)` 와 표본. 빌드가 없으면 None.
    """
    import struct

    img = glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))
    if not img:
        return None
    f1, mm1 = common.open_image(img[0])
    bad, seen = [], 0
    try:
        files = {p: (l, s) for p, l, s in common.iso_files(mm1)}
        for key, path in dump_ui.FILES.items():
            col = 0 if key == "ED" else 1
            orig = common.extract(path)
            built = common.read_extent(mm1, *files[path])
            for name, ed, ed2, stride, _n, _n2, _cat in dump_ui.GLOSSARY_TABLES:
                off = (ed, ed2)[col]
                if off is None:
                    continue
                # 표 시작 · 한 칸 앞(표 등록 밖 첫 칸) — 둘 다 기준 포인터 후보
                for base in (off, off - stride):
                    want = struct.pack(">I", patch_ui.NAME_PTR_BASE + base)
                    i = orig.find(want)
                    while i >= 0:
                        if i % 2 == 0:
                            seen += 1
                            if built[i : i + 4] != want:
                                bad.append((path, name, i, built[i : i + 4].hex()))
                        i = orig.find(want, i + 1)
    finally:
        mm1.close()
        f1.close()
    return len(bad), seen, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=5)
    a = ap.parse_args()
    r = check()
    if r is None:
        print("     ⏭ 빌드 이미지가 없다 — 건너뜀")
        return 0
    n, leak, odd, wrong = r
    ok = not (leak or odd or wrong)
    print(
        f"     {'✅' if ok else '❌'} 지명 칸 {n:,}곳 — 반각 누출 {len(leak)} · 홀수 길이 {len(odd)}"
        f" · 읽은 글≠쓴 이름 {len(wrong)}"
    )
    for tag, rs in (("반각", leak), ("홀수", odd)):
        for where, kr, raw in rs[: a.show]:
            print(f"        🔴 {tag} {where}: {kr!r} {raw.hex()}")
    for where, kr, got in wrong[: a.show]:
        print(f"        🔴 {where}: {kr!r} 를 썼는데 {got!r} 이 읽힌다")
    refs = table_base_refs()
    if refs is not None:
        nb, seen, bad = refs
        print(f"     {'✅' if not nb else '❌'} 지명 표 기준 포인터 {seen}곳 — 이주로 움직인 것 {nb}")
        for path, name, at, got in bad[: a.show]:
            print(f"        🔴 {path} {name} 풀 0x{at:X}: 원본 값이 {got} 로 바뀌었다")
        ok = ok and not nb
    if not ok:
        raise SystemExit("지명 칸이 전각 짝수 약속을 어겼거나 표 기준 포인터가 움직였다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
