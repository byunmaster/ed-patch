#!/usr/bin/env python3
"""조판 규칙 상주 검사(F3) — **번역 문안이 줄바꿈 규칙을 지키나** (대사 정본 · UI 문안).

    python3 tools/check_typeset_rules.py --disc ed3

규칙(공용 `krwrap` 가 지키는 것을 **결과로 다시 잰다** — 조판기가 조용히 깨져도 여기서 운다):
1. 줄 폭이 창 상한 안(`typeset.violations`) · 2. **어절을 쪼개지 않는다**(줄바꿈은 원문의 공백 자리에서만) ·
3. **줄 머리에 부호(`. , ! ? ) 」 』 …`)가 오지 않는다** · 4. 조각이 예산(`budget`+`floor`)을 안 넘는다(넘으면 `wrap` 이 운다).
⚠ 전투 로그 문구는 대부분 **자리를 아직 못 찾아**(실행파일 UI 낱말 일부만 잡힘) 분모에 든 것만 본다 — 분모를 같이 찍는다.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import josa_rt
import script as script_canon
import scriptmap
import textenc
import typeset

NO_LINE_START = tuple(".,!?)」』…~、。！？")


def line_problems(text):
    """한 줄바꿈 결과의 규칙 위반 사유들."""
    out = []
    for ln in text.split("\n")[1:]:  # 첫 줄은 문장의 시작이다(「...내일부터인데」 말줄임으로 시작해도 정상) — 줄바꿈 뒤 줄만 본다
        if ln[:1] in NO_LINE_START and ln[:1]:
            out.append(f"줄 머리에 부호 {ln[:1]!r}: {ln[:12]!r}")
    return out


def scene_rows(disc):
    """[(자리, 원문, 우리 문안, floor)] — 번역 정본 줄(원본에서 원문·바닥을 읽는다)."""
    canon = script_canon.load(disc)
    out = []
    for path, (lba, size) in sorted(common.iso_files(disc).items()):
        if "/SC" not in path or not path.endswith(".DAT"):
            continue
        data = common.read_lba(disc, lba, size)
        try:
            _, ents = common.arc_parse(data)
        except common.ArchiveError:
            continue
        for nm, off, sz in ents:
            rows = canon.get((path, nm))
            if not rows:
                continue
            info = scriptmap.parse(data[off : off + sz])
            jps = [(i, textenc.decode(c, disc)) for i, (_, c) in enumerate(info["segments"])]
            floors = script_canon.member_floors(jps)
            for i, row in sorted(rows.items()):
                out.append((f"{nm}#{i}", jps[i][1], row["kr"], floors.get(i, 0)))
    return out


def check(disc):
    bad, n = [], 0
    for where, jp, kr, floor in scene_rows(disc):
        n += 1
        kr = josa_rt.convert(kr)
        try:
            res = typeset.wrap(kr, disc, jp=jp, floor=floor)
        except typeset.TypesetError as e:
            bad.append(f"{where}: 예산 초과 — {e}")
            continue
        if res.replace("\n", " ").split() != kr.split():  # 어절 쪼갬 = 단어 목록이 달라진다
            bad.append(f"{where}: 어절이 쪼개졌다 {res!r}")
        bad += [f"{where}: {m}" for m in line_problems(res)]
        bad += [f"{where}: {m}" for m in typeset.violations(res, disc, jp=jp, floor=floor)]
    p = os.path.join(common.ROOT, f"ui_{disc}.json")
    n_ui = 0
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for off, row in json.load(f)["strings"].items():
                kr = row.get("kr")
                if not kr:
                    continue
                n_ui += 1
                bad += [f"ui:{off}: {m}" for m in line_problems(kr)]
                for ln in kr.split("\n"):
                    if typeset.width_cells(ln, disc) > typeset.LIMITS[disc]["width"]:
                        bad.append(f"ui:{off}: 줄이 {typeset.width_cells(ln, disc):g}칸 — {ln[:12]!r}")
    return bad, n, n_ui


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3")
    a = ap.parse_args()
    common.verify_source(a.disc)
    bad, n, n_ui = check(a.disc)
    print(f"{a.disc}: 조판 규칙 — 대사 {n}줄 · UI {n_ui} 확인 · 위반 {len(bad)}")
    for m in bad[:20]:
        print(f"  🔴 {m}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
