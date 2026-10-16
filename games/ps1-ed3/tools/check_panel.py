#!/usr/bin/env python3
"""월드맵 장소 패널 **넘침 전수**(게이트) — 패널의 모든 줄(지역명 위 칸 · 목록 줄)이 원판 줄 폭(칸) 안에 드는가.

    python3 tools/check_panel.py --disc ed3

패널 풀(`exetext.PANEL`)은 `0x8002` 로 끝나는 문자열마다 줄(= 제어 코드로 끊긴 글자·0 의 연속)이 있고, 한 줄이 쓸 수 있는 칸은 **원판 줄이 차지한 코드 수**다 —
빌드는 그 칸 안에서만 글자를 바꾼다(제어 열 보존, 줄마다 가운데). 우리 표기가 그 칸을 넘는 항목은 (띄어쓰기를 빼고도, 정본 `원문@월드맵` 줄인 꼴로도) 못 넣어 **일본어로 남는다.**
이 검사는 그런 항목을 `원문 | 우리 값 | 글자 수 / 칸` 으로 모아 보이고 하나라도 있으면 실패한다. 한글 한 글자 = 1코드이므로 글자 수로 잰다.
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import exetext
import glossary
import textenc


def rows(disc):
    lba, size = common.iso_files(disc)["/ED3.EXE" if disc == "ed3" else None]
    data = common.read_lba(disc, lba, size)
    cm = textenc.charmap(disc)
    words = dict(glossary.flat(disc))
    canon = glossary._canon()
    out, total, grow = [], 0, 0
    for unit in exetext.panel_units(data, *exetext.PANEL[disc]):
        for off, n in unit:
            _ind, codes, _tail = exetext.panel_line_text(data, off, n)
            if not codes:
                continue
            jp = exetext.match_panel_key(codes, disc, words)
            kr = words.get(jp) if jp else None
            if not kr or kr == jp:
                continue
            total += 1
            nospace = kr.replace(" ", "")
            if len(nospace) > n and len(nospace) <= 6:
                grow += 2 * (len(nospace) - n)  # 칸을 늘려 정본 표기 그대로 넣는다(`build.panel_grow` — 창 폭 6글자까지)
                continue
            cand = [kr, nospace, canon.lookup(jp + "@월드맵", "place", disc) or ""]
            fit = next((c for c in cand if c and len(c) <= n), None)
            if fit is None:
                out.append((jp, kr, len(nospace), n, off))
    start, end = exetext.PANEL[disc]
    tail = 0
    while struct.unpack_from("<H", data, end - tail - 2)[0] == 0:
        tail += 2
    if grow > tail:
        out.append(("(늘릴 칸 합계)", f"{grow}B", grow, tail, start))
    return out, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3")
    a = ap.parse_args()
    common.verify_source(a.disc)
    bad, total = rows(a.disc)
    print(f"{a.disc}: 월드맵 패널 — 사전 항목 {total}줄 중 칸을 넘는 것 {len(bad)}")
    for jp, kr, w, cells, off in bad:
        print(f"  🔴 0x{off:X}  {jp} | {kr} | {w}자 / {cells}칸")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
