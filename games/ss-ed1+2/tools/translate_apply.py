#!/usr/bin/env python3
"""번역 반영 — 페이로드의 「번역」을 `script/scn.json` 정본에 넣는다.

**넣는 길은 여기 하나다.** 손으로 붙여넣으면 아래 검사를 통째로 건너뛰는데, 이 층의
실수는 오타가 아니라 **소프트락**이다(구조 계약 · 창 총량).

받아들이기 전에 넷을 본다 — 하나라도 어긋나면 그 줄만 **거절**하고 나머지는 넣는다:

  ① 대상인가      — 페이로드가 준 키인가(임의의 키를 못 넣는다)
  ② 마크업        — 옮기고도 제어문자가 남으면 화면에 글자로 찍힌다
  ③ 구조 계약     — `%s`·`%d` 의 **개수와 순서**가 원문과 같은가 (다르면 소프트락)
  ④ 창 총량       — 전각 14자 × 5행. 넘치면 뒷줄이 조용히 잘린다

⚠ **이미 값이 있는 키는 덮지 않는다**(`--force` 로만). 대량 반영에서 「이미 판단이 든
  자리」를 자동으로 밀어내는 게 이 레포가 겪은 사고다(`patcher-checklist.md` 6).

  python3 tools/translate_apply.py work/review/translate/*.json
  python3 tools/translate_apply.py --dry …      # 넣지 않고 판정만
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "shared"),
)

import patch_scn as S
import typeset_scn as T
from text.line_key import key as line_key

_NAMES = None


def _names():
    global _NAMES
    if _NAMES is None:
        _NAMES = T._names()
    return _NAMES


def _args(t):
    """구조 계약 중 **인자만** — `%s`·`%d` 의 순서열."""
    return "".join(c for c in S.contract(t)[0] if c in "sd")


def judge(row):
    """`(문안, 거절 사유)`. 통과면 사유가 None."""
    kr = (row.get("번역") or "").strip()
    if not kr:
        return None, "비었다"
    if line_key(row["jp"]) != row["key"]:
        return None, "키가 원문과 안 맞는다"
    sat = T.to_saturn(kr)
    if sat is None:
        return None, "제어문자·마크업이 남는다"
    # ⚠ `%c`(창·색 전환)는 조판기가 원문 구조에서 붙인다 — 번역문엔 **인자만** 온다.
    if _args(sat) != _args(row["jp"]):
        return None, f"인자가 다르다 (원문 {row.get('인자')})"
    if not T.fits(sat):
        return None, "창을 넘는다 (전각 14자 × 5행)"
    # 🔴 **여기서 멈추면 안 된다** — 인자 개수가 맞아도 조판기가 자리에 못 넣으면 그 블록은
    #    빌드에서 조용히 탈락하고 화면엔 일본어가 남는다. 레포 규율이 「화면에 나가는
    #    바이트를 게이트로 본다」다. ⇒ **실제로 조판해 보고 계약까지 본다.**
    #    실측 2026-08-29(파일럿): 인자 검사만 통과한 6줄이 전부 여기서 걸렸다.
    built, why = T.typeset(row["jp"], kr, _names())
    if why:
        return None, f"조판이 안 된다 ({why})"
    if T.contract(built) != T.contract(row["jp"]):
        return None, "조판 결과의 구조 계약이 원문과 다르다"
    return kr, None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry, force = "--dry" in sys.argv, "--force" in sys.argv
    files = [f for a in args for f in glob.glob(a)]
    if not files:
        print("  쓸 페이로드가 없다")
        return 1
    with open(S.SCN_CANON, encoding="utf-8") as f:
        doc = json.load(f)
    lines = doc["lines"]
    put = skip = 0
    bad = []
    for path in files:
        with open(path, encoding="utf-8") as f:
            for row in json.load(f):
                if "번역" not in row:
                    continue
                kr, why = judge(row)
                if why:
                    if why != "비었다":
                        bad.append((os.path.basename(path), row["key"][:8], why))
                    continue
                if row["key"] in lines and not force:
                    skip += 1
                    continue
                lines[row["key"]] = kr
                put += 1
    print(f"  받아들임 {put:,} · 이미 있어 건너뜀 {skip:,} · 거절 {len(bad):,}")
    for b in bad[:12]:
        print(f"      {b[0]} {b[1]} — {b[2]}")
    if dry:
        print("  (--dry — 안 넣었다)")
        return 0
    doc["lines"] = dict(sorted(lines.items()))
    with open(S.SCN_CANON, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print(f"  → {S.SCN_CANON} (총 {len(lines):,})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
