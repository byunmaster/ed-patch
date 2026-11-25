#!/usr/bin/env python3
"""**전투·시스템 문구(실행파일 문자열)의 제어 토큰(%c %s %d · 제어 바이트)을 원판과 짝지어 대조.**

왜. 씬 대사 블록은 `check_scn_structure` 가 원본↔최종 이미지의 제어 코드 열을 대조하지만, 실행파일(ED.EXE·ED2.EXE·ED2MON*)
문자열은 그 검사 밖이었다. pce-ed1 에서 원문의 색 전환 옵코드를 조립기가 한 번도 안 내 35메시지가 엉뚱한 색으로 나온 사고
(10-29)가 빌드·게이트·짝 표 어느 것에도 안 잡혔다. PS1 의 색은 `%c`(엔진이 색 인자를 소비하는 자리)이므로 그 개수·순서가 곧
색 코드다 — 짝 표의 원판·한글 열에서 토큰 열을 뽑아 같은지 본다. 분모(잰 문자열 수 · 토큰 수)를 항상 같이 찍는다.

  python3 tools/check_exe_ctrl_tokens.py [--kr-bin 이미지]
"""

import argparse
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pair_table_sys as PS
from common import BUILD_DIR

TOK = re.compile(r"%[csd]|<[0-9A-Fa-f]{2}>")
# 의도한 추가 — 원판엔 없는 제어 바이트를 빌드가 일부러 넣은 자리(근거를 적는다).
ALLOW = {
    "ED.EXE:F8ED4": "파티 접미 たち → \\x01 + 「들」 (patch_items.FRAG_TACHI — 앞 낱말에 붙이는 표지)",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kr-bin", default=os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin"))
    a = ap.parse_args()
    if not os.path.exists(a.kr_bin):
        print(f"  ❌ 안 쟀다 — 최종 이미지 없음({a.kr_bin})")
        return 1
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "pairs-battle.tsv")
        PS.battle_system(a.kr_bin, out)
        rows = [l.split("\t") for l in open(out, encoding="utf-8").read().split("\n")[1:] if l.strip()]
    measured = ntok = 0
    bad = []
    allowed = []
    for r in rows:
        if len(r) < 3:
            continue
        tj, tk = TOK.findall(r[1]), TOK.findall(r[2])
        if not tj and not tk:
            continue
        measured += 1
        ntok += len(tj)
        if tj != tk:
            if r[0] in ALLOW:
                allowed.append(r[0])
                continue
            bad.append((r[0], tj, tk))
    if measured == 0:
        print("  ❌ 안 쟀다 — 제어 토큰이 든 문자열이 0 (짝 표가 비었거나 토큰 정의가 어긋남)")
        return 1
    print(
        f"  실행파일 제어 토큰 대조 [ps1-ed1+2] — 토큰이 든 문자열 {measured}개(원판 토큰 {ntok}개, 짝 표 {len(rows)}행 중) · 어긋남 {len(bad)} · 의도 허용 {len(allowed)}"
    )
    for b in bad[:20]:
        print(f"    ❌ {b[0]} 원판 {b[1]} → 한글 {b[2]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
