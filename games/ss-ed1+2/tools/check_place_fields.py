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
    if not ok:
        raise SystemExit("지명 칸이 전각 짝수 약속을 어겼다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
