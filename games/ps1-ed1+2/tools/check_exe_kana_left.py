#!/usr/bin/env python3
"""EXE 안에 **일본어 가나 문자열이 남았나** — ED.EXE·ED2.EXE 최종 이미지 전수.

**왜.** 화면 일본어 게이트(`check_scn_jp_left`)는 씬·ED2MON 만 본다. ED.EXE·ED2.EXE 의 시스템 문자열(메뉴·아이템·
몬스터·지명·전투 문구)은 `patch_*` 가 제자리로 바꾸는데, **빠진 자리가 있어도 아무 게이트도 안 걸렸다**
(10-08 전 세션 점검 — ps1-ed3 월드맵 지명이 그렇게 일본어로 남았다). 한글은 한자 슬롯에 놓여 가나가 아니므로
**가나 2자 이상이 이어진 널 종단 문자열**은 우리가 안 바꾼 원문이다.

기준선: 데이터 조각이 가나처럼 읽히는 오탐(코드·표 바이트)을 `script/exe_kana_baseline.json` 에 둔다(문자열 → 사유).
새로 생기면 실패 — 의도된 것이면 기준선에 사유와 함께 추가한다.

  python3 tools/check_exe_kana_left.py
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import BUILD_DIR, ROOT, extract

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"
BASELINE = os.path.join(ROOT, "script", "exe_kana_baseline.json")
EXES = {"ED.EXE": (257, 1021952), "ED2.EXE": (756, 872448)}
_RUN = re.compile(rb"(?:[\x20-\x7e]|[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]|[\xa1-\xdf]){2,}")
_KANA = re.compile(r"[ぁ-ゖァ-ヺ]")


def kana_runs(buf):
    """[(오프셋, 문자열)] — 가나 2자 이상이 든 SJIS 런.

    ⚠ **「알려진(번역된) 구간과 겹치는지」를 보지 않는다** — 런 하나하나에 가나가 있나만 본다.
    그래서 한글 슬롯(번역된 자리)이 앞뒤에 붙어 있어도 가나 둘이면 걸린다(회귀 테스트:
    `test_jp_gates.py`). 임계는 실측으로 정했다(2026-10-18): 런 최소 3→2자(여기 반영) 는 같은 3건·신규 0,
    **가나 1자로 낮추면 코드 바이트 오탐이 305건**이라 못 낮춘다 — 가나 1자짜리 조각은 이
    게이트가 원리상 못 본다(되읽기·화면 몫).
    """
    hits = []
    for m in _RUN.finditer(buf):
        try:
            s = m.group().decode("cp932")
        except UnicodeDecodeError:
            continue
        if len(_KANA.findall(s)) >= 2:
            hits.append((m.start(), s))
    return hits


def scan(img=IMG):
    """{파일: [(오프셋, 문자열)]} — 가나 2자 이상이 든 SJIS 런."""
    return {
        name: kana_runs(bytes(extract(lba, size, path=img))) for name, (lba, size) in EXES.items()
    }


def check(strict=True, img=IMG):
    base = {}
    if os.path.exists(BASELINE):
        with open(BASELINE, encoding="utf-8") as f:
            base = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    res = scan(img)
    new = [(n, o, s) for n, hs in res.items() for o, s in hs if f"{n}|{s}" not in base]
    total = sum(len(h) for h in res.values())
    print(f"  EXE 가나 잔존 {total} (기준선 {total - len(new)}) — 새로 생긴 것 {len(new)}")
    for n, o, s in new[:20]:
        print(f"    ❌ {n} @{o:#x} {s!r}")
    if new and strict:
        raise SystemExit(
            "EXE 에 일본어 가나 문자열이 새로 남았다 — 번역 누락이거나 기준선에 사유를 적어야 한다"
        )
    return len(new)


if __name__ == "__main__":
    sys.exit(1 if check(strict=False) else 0)
