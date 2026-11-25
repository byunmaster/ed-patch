#!/usr/bin/env python3
"""문장부호 전수 게이트(번역 규칙 1-1·1-3·1-7·2-12, 마스터 11-13) — 정본 줄과 UI 문안 전량.

    python3 tools/check_punct.py            # 위반이 하나라도 있으면 실패
    python3 tools/check_punct.py --selftest # 양성 대조

잡는 것 — ① 전각 ！？．，·⁉‼ (반각 `! ? . ,` 만 쓴다) ② 가운뎃점 ・ ･ 잔존 ③ 띄어 쓴 `… …`
④ `?.` `!.` 겹침 ⑤ **원문 점 n 개 → `…` round(n/3) 개(최소 1)** — 원문과 한국어의 점 덩이 수가 같은 줄에서만 센다
⑦ 원문 `〜` `!` `?` `…` 개수보다 번역이 적으면(원문 부호는 빼지 않는다) ⑥ 원문이 `！？` 면 `!?`, `？！` 면 `?!` 로 — 순서는 원문을 따른다.
`..`·`~`·`～.`·`…?` 순서·`…` 뒤 공백은 check_typeset_rules 가 이미 본다.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

_FULL = re.compile("[！？．，⁉‼⁈⁇]")
_NAKA = re.compile("[・･]")
_SPACED = re.compile("…\\s+…")
_OVER = re.compile(r"[?!]\.")
_JP_DOTS = re.compile("[…・･]+")


def dots_of(jp):
    """원문의 점 덩이마다 점 개수(「…」 한 글자는 점 셋)."""
    return [len(m.group(0)) * (3 if "…" in m.group(0) else 1) for m in _JP_DOTS.finditer(jp)]


def problems(jp, kr):
    out = []
    flat = kr.replace("\n", "").replace("\f", "")
    if _FULL.search(kr):
        out.append("전각 ！？．， 또는 ⁉‼ (반각으로)")
    if _NAKA.search(kr):
        out.append("가운뎃점 ・ ･ 잔존 (…로)")
    if _SPACED.search(flat):
        out.append("`… …` 띄어 쓴 말줄임 (… 하나로)")
    if _OVER.search(flat):
        out.append("?. · !. 겹침")
    if jp:
        j = dots_of(jp)
        k = [len(m.group(0)) for m in re.finditer("…+", kr)]
        if j and len(j) == len(k):
            exp = [max(1, round(n / 3)) for n in j]
            if exp != k:
                out.append(f"말줄임 개수 원문 점 {j} → … {exp} 이어야 하는데 {k}")
        jf = jp.replace("\n", "")
        if "！？" in jf and "?!" in flat and "!?" not in flat:
            out.append("원문 ！？ 인데 ?! 순서")
        if "？！" in jf and "!?" in flat and "?!" not in flat:
            out.append("원문 ？！ 인데 !? 순서")
    return out


# 눈으로 본 예외 — 원문 점·물결 덩이가 한국어 음절 수와 안 맞아 1:1 이 안 되는 줄(11-13)
LOST_OK = {"OT0500.BIN#123", "FT5100.BIN#87"}


def lost(jp, kr):
    """원문 부호(`〜` `!` `?` `…`)를 번역이 뺀 자리 — 원문 개수보다 한국어가 적으면 (마스터 11-13 「원문 부호는 빼지말자」).

    ⚠ 장음 `ー`(→ 〜)는 세지 않는다 — 한국어는 모음을 늘여 쓰는 경우가 많아 마스터 판정 전이다. 빈 한국어(앞 줄에 이은 조각)는 대상 밖."""
    if not jp or not kr.replace("\n", "").replace("\f", "").strip():
        return []
    t = re.sub("\ufffd[0-9a-f]{3,4}", "", jp)
    out = []
    for name, j, k in (
        ("물결표", len(re.findall("[\u301c\uff5e]", t)), len(re.findall("[\u301c\uff5e]", kr))),
        ("느낌표", len(re.findall("[\uff01!]", t)), kr.count("!")),
        ("물음표", len(re.findall("[\uff1f?]", t)), kr.count("?")),
        (
            "말줄임",
            sum(
                max(1, round(len(m.group(0)) * (3 if "\u2026" in m.group(0) else 1) / 3))
                for m in re.finditer("\u30fb{2,}|\u2026+", t)
            ),
            kr.count("\u2026"),
        ),
    ):
        if k < j:
            out.append(f"{name} 원문 {j} → 번역 {k}")
    return out


def selftest():
    d = "・"
    ok = bool(problems(d * 6, "…"))  # 6 → 2 인데 1
    ok &= not problems(d * 6, "……")
    ok &= not problems(d * 3, "…")
    ok &= bool(problems(d * 13, "…" * 8))
    ok &= bool(problems("", "！"))
    ok &= bool(problems("", "… …"))
    ok &= bool(problems("", "x?."))
    ok &= bool(problems("！？", "x?!"))
    ok &= not problems("！？", "x!?")
    ok &= bool(problems("？！", "x!?"))
    ok &= bool(lost("\u3042\u301c\uff01", "x"))
    ok &= bool(lost("\u3042\uff1f", "x."))
    ok &= not lost("\u3042\u301c\uff01", "x\u301c!")
    ok &= not lost("\u3042\uff1f", "")  # 빈 조각은 대상 밖
    ok &= not lost("\u30fb\u30fb", "x\u2026")  # 점 둘 → … 하나
    print("양성 대조", "통과" if ok else "🔴 실패")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()
    if selftest():
        return 1
    common.verify_source("ed3")
    import check_typeset_rules as ctr

    bad, n = [], 0
    for where, jp, kr, _f in ctr.scene_rows("ed3"):
        n += 1
        bad += [f"{where}: {m} {kr[:20]!r}" for m in problems(jp, kr)]
        if where.split("\\")[-1] not in LOST_OK:
            bad += [f"{where}: 원문 부호 빠짐 — {m} {kr[:20]!r}" for m in lost(jp, kr)]
    p = os.path.join(common.ROOT, "ui_ed3.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for off, row in json.load(f)["strings"].items():
                if row.get("kr"):
                    n += 1
                    bad += [f"ui:{off}: {m} {row['kr'][:20]!r}" for m in problems("", row["kr"])]
    print(f"ed3: 문장부호 전수 {n}줄 — 위반 {len(bad)}")
    for b in bad[:40]:
        print("  🔴", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
