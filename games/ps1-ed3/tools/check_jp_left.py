#!/usr/bin/env python3
"""화면 일본어 잔존 검사(F7) — **번역했다고 올린 문안에 가나·한자가 섞였나.**

    python3 tools/check_jp_left.py --disc ed3

🔴 「화면에 일본어 0」을 지금 요구하면 번역 대사가 0.5% 라 **늘 빨간불**이다(아무도 안 본다). 그래서 **옮겼다고 올린 자리**만 본다:
   번역 정본 `script/`(우리 문안) · UI 정본 `ui_*.json` · 사전이 읽은 낱말(`glossary.flat`). 거기에 가나·한자가 한 글자라도 있으면
   옮기다 만 것이다(「・」 U+30FB 는 말줄임 원문 부호라 뺀다).
⚠ 아직 안 옮긴 자리(미번역)는 실패가 아니다 — 개수만 찍는다(분모).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import glossary
import script as script_canon


def has_jp(s):
    return any(("぀" <= c <= "ヿ" and c != "・") or "一" <= c <= "鿿" for c in s)


def scan(disc):
    bad, total = [], 0
    for (_a, member), rows in script_canon.load(disc).items():
        for i, row in sorted(rows.items()):
            total += 1
            if has_jp(row["kr"]):
                bad.append(f"{member}#{i}: {row['kr'][:30]!r}")
    p = os.path.join(common.ROOT, f"ui_{disc}.json")
    n_ui = 0
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for off, row in json.load(f)["strings"].items():
                if row.get("kr"):
                    n_ui += 1
                    if has_jp(row["kr"]):
                        bad.append(f"ui:{off}: {row['kr'][:30]!r}")
    names = glossary.flat(disc)
    for jp, kr in names.items():
        if has_jp(kr):
            bad.append(f"낱말 {jp}→{kr}")
    return bad, total, n_ui, len(names)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3")
    a = ap.parse_args()
    bad, total, n_ui, n_names = scan(a.disc)
    print(f"{a.disc}: 일본어 잔존 — 옮긴 대사 {total}줄 · UI {n_ui} · 낱말 {n_names} 중 가나·한자 섞임 {len(bad)}")
    for m in bad[:20]:
        print(f"  🔴 {m}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
