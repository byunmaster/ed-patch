#!/usr/bin/env python3
"""게임 폴더에 **자기 JP→KR 표**가 남았나 — 있으면 실패(마스터 2026-10-08 「모든 워커는 자기 사전을 들고 있으면 안 된다」).

고유명사는 사전, 그 밖의 공통 문안은 정본(`shared/canon`)에서 읽는다. 게임 폴더의 코드(`tools/*.py`)에 **가나/한자 열쇠 ≥2 + 한글 값 ≥2** 인
dict·쌍 목록(상수)이 있거나, JSON(`textmap/`·`script/` 의 평탄 사전)에 가나/한자 열쇠가 있으면 잡는다.

예외는 `own_tables_allow.json` 에만 둔다(사유 필수, 두 종류):
- `exempt`  — 표가 아니라 **규칙·장부**이거나 마스터가 예외로 정한 것(스태프롤은 게임마다 제작진이 달라 게임 폴더에 둔다 — 마스터 10-08).
- `pending` — 정본에 아직 없는 값이라 **관리자에게 후보로 올린 것**. 관리자가 main 정본에 올리면 읽게 바꾸고 줄을 지운다.

  python3 tools/check_own_tables.py
"""

import ast
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOW = os.path.join(ROOT, "own_tables_allow.json")
JP = re.compile(r"[ぁ-ゖァ-ヺ一-鿋]")
KO = re.compile(r"[가-힣]")


def _jp(s):
    return isinstance(s, str) and bool(JP.search(s))


def scan_code():
    """[(상대경로|상수이름, 줄, 항목 수)]"""
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "tools", "**", "*.py"), recursive=True)):
        if os.sep + "tests" + os.sep in f:
            continue
        try:
            tree = ast.parse(open(f, encoding="utf-8").read())
        except SyntaxError:
            continue
        rel = os.path.relpath(f, ROOT)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            name = next((t.id for t in node.targets if isinstance(t, ast.Name)), "?")
            v, n = node.value, 0
            if isinstance(v, ast.Dict):
                n = sum(
                    1
                    for k, x in zip(v.keys, v.values, strict=True)
                    if isinstance(k, ast.Constant)
                    and _jp(k.value)
                    and isinstance(x, ast.Constant)
                    and isinstance(x.value, str)
                    and KO.search(x.value)
                )
            elif isinstance(v, ast.List | ast.Tuple):
                n = sum(
                    1
                    for e in v.elts
                    if isinstance(e, ast.Tuple)
                    and len(e.elts) >= 2
                    and isinstance(e.elts[0], ast.Constant)
                    and _jp(e.elts[0].value)
                    and isinstance(e.elts[1], ast.Constant)
                    and isinstance(e.elts[1].value, str)
                    and KO.search(e.elts[1].value)
                )
            if n >= 2:
                out.append((f"{rel}|{name}", node.lineno, n))
    return out


def scan_json():
    out = []
    for sub in ("textmap", "script"):
        for f in sorted(glob.glob(os.path.join(ROOT, sub, "*.json"))):
            rel = os.path.relpath(f, ROOT)
            if re.match(r"script/ED[12]SCN\d+\.json$", rel) or rel.endswith("ED2MON_LINES.json"):
                continue  # 번역 정본(엔트리 번호·sha 키) — 표가 아니라 본문
            try:
                d = json.load(open(f, encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if isinstance(d, dict):
                n = sum(1 for k in d if _jp(k))
                if n >= 2:
                    out.append((rel, 0, n))
    for rel in ("names_exceptions.json", "canon_exceptions.json"):
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            n = sum(1 for k in d if _jp(k))
            if n >= 2:
                out.append((rel, 0, n))
    return out


def check(strict=True):
    allow = {}
    if os.path.exists(ALLOW):
        raw = json.load(open(ALLOW, encoding="utf-8"))
        allow = {k: v for k, v in raw.items() if not k.startswith("_")}
    found = scan_code() + scan_json()
    bad = [(k, ln, n) for k, ln, n in found if k not in allow or not allow[k].get("why")]
    stale = sorted(set(allow) - {k for k, _l, _n in found})
    pend = sum(1 for k, *_ in found if allow.get(k, {}).get("status") == "pending")
    ex = sum(1 for k, *_ in found if allow.get(k, {}).get("status") == "exempt")
    print(f"  자기 표 {len(found)}종 — 예외 {ex} · 관리자 후보 대기 {pend} · 위반 {len(bad)}")
    for k, ln, n in bad:
        print(f"    ❌ {k} (줄 {ln}, 항목 {n}) — 사전·정본에서 읽게 바꾸거나 own_tables_allow.json 에 사유를 적는다")
    for k in stale:
        print(f"    ⚠ 예외 목록에만 있다(표가 사라졌다 — 줄을 지운다): {k}")
    if bad and strict:
        raise SystemExit("게임 폴더에 자기 JP→KR 표가 남았다")
    return len(bad)


if __name__ == "__main__":
    sys.exit(1 if check(strict=False) else 0)
