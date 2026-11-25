#!/usr/bin/env python3
"""**지명 칸에 반각이 새지 않았나 · 길이가 짝수인가** — 최종 이미지에서 되읽는다.

    python3 tools/check_place_fields.py [--show N]

## 왜 있나 (마스터 판정 (나), 2026-09-27)

PS1 은 지명에 반각 공백이 끼어 **홀수 길이**가 되자 실내 HUD 가 NUL 을 놓쳐 꼬리가 비쳤다
(2바이트 단위 종결 판정). 새턴은 그 코드가 없다는 걸 값과 화면으로 봤지만(11B 「크루즈 마을」
온전), 마스터 판단은 **안전하게 간다**다 — 지명 칸은 전부 전각(2B 단위)이다 — 단 접미 표 칸 끝의 반각 공백 한 개(마스터 11-09)와 배너 전용 표는 예외.
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


BANNER_CELLS = (
    16  # 입장 배너·HUD 상자 — 엔진(`0x0607968C`)이 지명 길이로 좌우 반각 패딩을 만드는 폭
)
HALF_PX = (
    6  # 반각 한 칸의 픽셀 폭 — 전각(12px) 한 칸의 반이 쏠림 한계다(번역 규칙 2-8, 마스터 11-04)
)


def banner_skew(n):
    """지명 바이트 길이 n → 틀 가운데에서 쏠린 px(왼쪽 패딩 (16−n)/2 를 내림하는 엔진 산수). 넘치면 None."""
    if n > BANNER_CELLS:
        return None
    left = (BANNER_CELLS - n) // 2
    return (BANNER_CELLS - n - left - left) * HALF_PX / 2


def banner_check(rows, files_d):
    """씬 지명 헤더(입장 배너·우하단 HUD 가 같은 버퍼를 쓴다) 전부의 가운데 쏠림 — 한 칸(12px) 반(6px) 초과면 실패."""
    worst, bad = 0.0, []
    for path, at, room, kr, where in rows:
        if "헤더" not in where:
            continue
        d = files_d[path]
        z = d.find(b"\x00", at, at + room)
        n = (z if z >= 0 else at + room) - at
        sk = banner_skew(n)
        if sk is None or sk > 6:
            bad.append((where, kr, n, sk))
        else:
            worst = max(worst, sk)
    return worst, bad


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
            # 🔴 접미 표 칸의 끝 반각 공백 한 개는 의도다(마스터 11-09 「방향접미 앞 공백 반각」) — 그 하나만 떼고 평소대로 본다(홀수 길이도 이 한 칸뿐).
            walk = raw[:-1] if (kr.endswith(" ") and raw.endswith(b"\x20")) else raw
            half, is_odd = _walk(walk)
            if half:
                leak.append((where, kr, raw))
            if is_odd:
                odd.append((where, kr, raw))
            if _decode(raw, inv) != kr:
                wrong.append((where, kr, _decode(raw, inv)))
    finally:
        mm1.close()
        f1.close()
    return len(rows), leak, odd, wrong, cache, rows


def table_base_refs():
    """🔴 **표 기준 포인터가 안 움직였나** — 지명 표(+ 시스템 메뉴·전투 명령 같은 UI 표 `dump_ui.TABLES`, 마스터 11-06 manager —
    「한 칸 앞」 기준 포인터는 번호가 1부터라 칸 −1 을 안 읽는다. 표를 옮기면 조용히 깨진다)를 가리키는 코드 풀 값(`적재 주소 + 표 시작 − 한 칸 … + 표 시작`)이
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
            for name, ed, ed2, stride, *_rest in (*dump_ui.GLOSSARY_TABLES, *dump_ui.TABLES):
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
                            # 입장 배너 호출부 리터럴은 **전용 표로 일부러 돌린다**(`patch_ui.BANNER_TABLES`) — 옛 표를 가리키면 오히려 실패다
                            skip = i in patch_ui.BANNER_TABLES.get(path, {}).get("ptrs", ())
                            if not skip and built[i : i + 4] != want:
                                bad.append((path, name, i, built[i : i + 4].hex()))
                        i = orig.find(want, i + 1)
    finally:
        mm1.close()
        f1.close()
    return len(bad), seen, bad


def banner_table_check():
    """🔴 **입장 배너 전용 표**(`patch_ui.BANNER_TABLES`, 마스터 11-09) — 빌드에서 호출부 리터럴이 가리키는 곳의 행이 전부
    `banner_name`(정본 일반 꼴, 띄움) 으로 읽히고 · 짝수 길이 · 칸−1 이하인가. `table_base_refs` 가 이 리터럴을 면제하는 대신 여기서 본다.
    → `(검사한 행 수, 문제 목록)`; 빌드가 없으면 None."""
    import struct

    img = glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))
    if not img:
        return None
    inv = _inv_map()
    rs = patch_ui.rows()
    f1, mm1 = common.open_image(img[0])
    n, bad = 0, []
    built_cache = {}
    try:
        files = {p: (l, s) for p, l, s in common.iso_files(mm1)}
        for path, c in patch_ui.BANNER_TABLES.items():
            built = common.read_extent(mm1, *files[path])
            lits = {struct.unpack(">I", built[o : o + 4])[0] for o in c["ptrs"]}
            if len(lits) != 1:
                bad.append((path, "리터럴이 서로 다르다", sorted(lits)))
                continue
            start = lits.pop() + c["lead"] - patch_ui.ptr_base(path)
            for k, tn, i, _at, _st, jp, kr in sorted(rs, key=lambda r: r[2]):
                if k != c["key"] or tn != c["tab"] or not kr:
                    continue
                raw = built[start + i * c["stride"] : start + (i + 1) * c["stride"]]
                z = raw.find(b"\x00")
                raw = raw[: z if z >= 0 else len(raw)]
                want = patch_ui.banner_name(
                    jp.strip(patch_ui.WIDE_SP + " "), kr.strip(patch_ui.WIDE_SP + " "), c["title"]
                )
                got = _decode(raw, inv)
                n += 1
                if len(raw) > c["stride"] - 1:  # 배너 전용 표는 반각 공백(홀수 길이)이 정상이다 — 배너 그리기는 길이로 센다
                    bad.append((path, i, f"길이 {len(raw)}"))
                elif got != want and got != kr.strip(
                    patch_ui.WIDE_SP + " "
                ):  # 칸에 안 들면 붙인 꼴
                    bad.append((path, i, got))
        # 끼움·보정 루틴(두 파일) — 풀 리터럴이 루틴을 가리키고, 루틴·칸별 [위치, 보정] 표 바이트가 정본과 같은가
        dx = patch_ui.banner_dx()
        pos = patch_ui.ed2_banner_space_pos(rs)
        for path, key, nn in (("/ED.BIN", "ED1", 48), ("/ED2.BIN", "ED2", 36)):
            bb = built_cache.setdefault(path, common.read_extent(mm1, *files[path]))
            data = b"".join(
                bytes([(pos.get(i, 0) if key == "ED2" else 0) & 0xFF, dx[key][i] & 0xFF])
                for i in range(nn)
            )
            want_a, want_b = patch_ui.banner_hook_codes(path, data)
            for kind, want in (("strlen", want_a), ("draw", want_b)):
                lit_at = patch_ui.BANNER_HOOKS[path][kind][0]
                at = struct.unpack(">I", bb[lit_at : lit_at + 4])[0] - patch_ui.ptr_base(path)
                n += 1
                if bb[at : at + len(want)] != want:
                    bad.append((path, f"{kind} 루틴", "리터럴이 정본 루틴·표를 안 가리킨다"))
    finally:
        mm1.close()
        f1.close()
    return n, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=5)
    a = ap.parse_args()
    r = check()
    if r is None:
        print("     ⏭ 빌드 이미지가 없다 — 건너뜀")
        return 0
    n, leak, odd, wrong, cache, rows = r
    hn = sum("헤더" in w for _p, _a, _r, _k, w in rows)
    worst, bbad = banner_check(rows, cache)
    print(
        f"     {'✅' if not bbad else '❌'} 입장 배너 가운데 — 지명 헤더 {hn}곳, 틀 가운데에서 쏠림 최대 {worst:g}px"
        f"(한계 6px = 전각 반 칸) · 넘침/초과 {len(bbad)}"
    )
    for where, kr, nb, sk in bbad[: a.show]:
        print(f"        🔴 {where}: {kr!r} {nb}B 쏠림 {sk}")
    ok = not (leak or odd or wrong or bbad)
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
        print(
            f"     {'✅' if not nb else '❌'} 지명 표 기준 포인터 {seen}곳 — 이주로 움직인 것 {nb}"
        )
        for path, name, at, got in bad[: a.show]:
            print(f"        🔴 {path} {name} 풀 0x{at:X}: 원본 값이 {got} 로 바뀌었다")
        ok = ok and not nb
    bt = banner_table_check()
    if bt is not None:
        bn, bb = bt
        print(
            f"     {'✅' if not bb else '❌'} 입장 배너 전용 표 {bn}행 — 정본 일반 꼴(띄움)로 읽힘 · 문제 {len(bb)}"
        )
        for x in bb[: a.show]:
            print(f"        🔴 {x}")
        ok = ok and not bb
    if not ok:
        raise SystemExit(
            "지명 칸이 전각 짝수 약속을 어겼거나 배너가 가운데에서 벗어났거나 표 기준 포인터가 움직였다"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
