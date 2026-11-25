"""본 프로그램 쓰기 장부의 **「덮인 원본 바이트가 무엇이었나」 축**(11-06 횃불 프리징 회귀).

옛 게이트는 「의도한 쓰기가 들어갔나」(되읽기)·「무변경 구간 밖이 같은가」만 봤고, **덮인 원본이 문자열·패딩이었는지**는 안 봤다.
`systext.DEAD_DEBUG` 가 「호출자 0」 근거로 **간접 호출되는 산 코드**를 비워 그 위에 한글을 얹었는데 빌드·되읽기·단위 테스트가 다 통과했다.

쓰기 한 곳마다 원본 바이트의 종류를 매긴다:
  PAD   전부 0xFF/0x00(원판 패딩)
  STR   원본 문자열 리터럴 안(`JSR $4ED5/$503E/$4ED1 · BIT $addr` 가 가리키는 NUL 종결 문자열) 또는 `DEAD_DEBUG`
  FIX   피연산자 2바이트 고치기(참조 재배치 — 라벨 `ref`) 또는 후킹(라벨에 「후킹」/hook)
  CODE  그 밖 — **원본 코드·표를 덮는 쓰기**. `overwrite_allow.json` 에 (뱅크, 오프셋, 길이, 사유) 로 등록된 것만 허용한다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout
import systext

# 라벨로 아는 의도된 코드 고치기(피연산자·이음매·디버그 후킹) — 덮이는 원본이 코드인 게 맞다. 이 밖에 코드를 덮으면 `overwrite_allow.json` 에 사유와 함께 등록한다.
FIX_LABELS = ("ref", "후킹", "hook", "interior write", "seam", "lzring 이음매", "디버그", "RUN 새로", " base ", "placeholder write", "narrow font")

ALLOW = Path(__file__).resolve().parents[1] / "overwrite_allow.json"


def _str_regions(prog: layout.Prog) -> list[tuple[int, int, int]]:
    out = []
    for (b, off) in systext.scan_literals(prog):
        s = prog.o(b, 0, layout.BANK)
        end = s.find(b"\x00", off)
        if end > off:
            out.append((b, off, end + 1))
    for b, off, ln, _h, _t in systext.DEAD_DEBUG:
        out.append((b, off, off + ln))
    for b, off, ln in prog.vacated:  # 문구를 옮기며 비운 칸 — 거기 있던 원본은 (옮긴) 문자열이다
        out.append((b, off, off + ln))
    out.sort()
    merged: list[list[int]] = []
    for b, lo, hi in out:  # 맞닿은 칸은 이어 붙인다(옮긴 문자열이 이웃한 두 칸에 걸친다)
        if merged and merged[-1][0] == b and lo <= merged[-1][2]:
            merged[-1][2] = max(merged[-1][2], hi)
        else:
            merged.append([b, lo, hi])
    return [tuple(m) for m in merged]


def classify(prog: layout.Prog) -> list[dict]:
    regs = _str_regions(prog)
    rows = []
    for lin, new, old, label in prog.spans():
        idx = lin - layout.PROG_REL * 2048
        bank, off = layout.BANK0 + idx // layout.BANK, idx % layout.BANK
        if not (0 <= bank - layout.BANK0 < layout.NBANKS) or off + len(new) > layout.BANK:
            kind = "OUT"  # 프로그램 칸 밖(뱅크 경계 넘음) — 따로 본다
        elif set(old) <= {0xFF, 0x00}:
            kind = "PAD"
        elif any(b == bank and lo <= off and off + len(new) <= hi for b, lo, hi in regs):
            kind = "STR"
        elif any(k in label for k in FIX_LABELS):
            kind = "FIX"
        else:
            kind = "CODE"
        rows.append({"bank": bank, "off": off, "len": len(new), "kind": kind, "label": label})
    return rows


def allowed() -> list[tuple[int, int, int, str]]:
    if not ALLOW.exists():
        return []
    return [tuple(r) for r in json.loads(ALLOW.read_text(encoding="utf-8"))["allow"]]


def unregistered(rows: list[dict]) -> list[dict]:
    al = allowed()
    return [
        r
        for r in rows
        if r["kind"] in ("CODE", "OUT")
        and not any(b == r["bank"] and lo <= r["off"] and r["off"] + r["len"] <= lo + ln for b, lo, ln, _why in al)
    ]
