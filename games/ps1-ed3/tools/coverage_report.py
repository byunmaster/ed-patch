#!/usr/bin/env python3
"""화면 글 **출처 전수 표** — 빌드가 화면에 내보내는 모든 글이 이름 검사(`names_corpus.pairs`)·F7 에 들어가는가.

    python3 tools/coverage_report.py --disc ed3 [--built "<(TEST).bin 경로>"] [--out coverage.md]

🔴 검사기는 **자기 분모 안만** 본다 — 분모 밖에서 월드맵 장소 패널이 일본어로 남았다(마스터 실기 10-08). 이 표는 분모를 출처별로 펼쳐
   「아무 검사도 안 보는 출처」를 눈에 보이게 한다. 실행파일 낱말은 **구운 이미지와 원본을 문자열 단위로 비교**해 「안 바뀐 것 = 일본어로 남음」을 센다.
"""

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import dump_names
import exetext
import glossary
import script as S
import textenc
import uitext

NAME_KINDS = ("person", "item", "spell", "monster", "place", "rank")


def region_strings(exe, start, end):
    out, p = [], start
    while p < end:
        codes, term = exetext.raw_string(exe, p)
        if codes is None:
            break
        if codes:
            out.append((p, codes))
        p += 2 * (len(codes) + 1)
        while p < end and exetext.is_term(struct.unpack_from("<H", exe, p)[0]):
            p += 2
    return out


def exe_rows(disc, built):
    exe = uitext.exe_bytes(disc)
    new = None
    if built and os.path.exists(built):
        lba, size = common.iso_files(disc)[dump_names.EXE[disc]]
        new = common.read_lba(disc, lba, size, path=built)
    words = set(dict(glossary.flat(disc)))
    _, sites = uitext.sites(disc)
    reg = sorted(dump_names.REGIONS[disc].items())
    rows = {}
    for i, (st, kind) in enumerate(reg):
        end = reg[i + 1][0] if i + 1 < len(reg) else st + 0x400
        for off, codes in region_strings(exe, st, end):
            jp = textenc.decode(codes, disc)
            src = "ui" if off in sites else ("glossary" if jp in words else "none")
            left = None
            if new is not None:
                cur, _t = exetext.raw_string(new, off)
                left = cur == codes  # 안 바뀜 = 일본어 그대로(구운 시험 이미지 기준)
            r = rows.setdefault(kind, {"n": 0, "ui": 0, "glossary": 0, "none": 0, "left": 0, "left_none": 0})
            r["n"] += 1
            r[src] += 1
            if left:
                r["left"] += 1
                if src == "none":
                    r["left_none"] += 1
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3")
    ap.add_argument("--built", default=os.path.join(common.BUILD_DIR, "Eiyuu Densetsu III (KR) (TEST).bin"))
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = exe_rows(a.disc, a.built)
    canon = S.load(a.disc)
    total = tr = 0
    for _arc, _mem, segs in S.members(a.disc):
        total += sum(1 for _i, jp in segs if jp.strip())
    tr = sum(len(v) for v in canon.values())
    with open(os.path.join(common.ROOT, "graphics_ed3.json"), encoding="utf-8") as f:
        g = json.load(f)["images"]
    import patch_title_font as P

    L = []
    L.append(f"# 화면 글 출처 전수 — {a.disc} (구운 이미지: {'있음' if os.path.exists(a.built) else '없음'})\n")
    L.append("| 출처 | 줄 수 | 이름검사(pairs) | F7(일본어 잔존) | 비고 |")
    L.append("|---|---|---|---|---|")
    L.append(f"| 씬 대사·화자명(`script/`) | {total:,} (옮김 {tr}) | O (미번역은 None 분모) | O (옮긴 줄만) | 화자명 길이 고정 멤버 272 는 일본어로 남음 |")
    ui = len(uitext.sites(a.disc)[1])
    L.append(f"| UI 문안(`ui_ed3.json` — menu·text 구역) | {ui} | O (`ui:0x…`) | O | 표 없는 구역은 길이 고정 |")
    for kind in NAME_KINDS + ("menu", "text"):
        r = rows.get(kind)
        if not r:
            continue
        pairs = "O (`ui:`+`exe:`)" if r["ui"] else "O (`exe:` — 읽히는 문자열만, 사전 값과 짝)"
        f7 = "시험 빌드 게이트(`check_names_left` — 사전 낱말이 구운 이미지에 안 바뀐 채 남으면 실패)" if kind in NAME_KINDS else "UI 쪽만 O · 나머지 미번역(분모)"
        note = f"사전 {r['glossary']} · UI {r['ui']} · **어느 쪽도 아님 {r['none']}**" + (
            f" · 구운 이미지에서 안 바뀐 것 {r['left']}(그중 **출처 없음 {r['left_none']}**)" if r["left"] is not None else ""
        )
        L.append(f"| 실행파일 `{kind}` | {r['n']} | {pairs} | {f7} | {note} |")
    L.append(f"| 그림 속 글(TIM) | {len(g)} 장 | X | X | 적용 21 · 크레딧 4·간판 1·글자판 1 미적용 |")
    L.append(f"| 타이틀 「이어서 하기」(BIOS 폰트) 문자열 | {len(P.STRINGS)} + 슬롯 지명 86 | X | X | `patch_title_font` 가 사전으로 채움 |")
    text = "\n".join(L) + "\n"
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()
