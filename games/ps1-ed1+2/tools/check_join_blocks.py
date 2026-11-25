#!/usr/bin/env python3
"""이어 받는 블록 게이트 — 11-11 밤샘 실화면에서 나온 두 꼴을 막는다(마스터 11-11 핫픽스 판정).

 ① 이어 받는 블록(선두 붙임 공백 `NOBREAK_SP`)의 **첫 줄이 앞 블록 마지막 줄에 이어 붙을 폭을 넘는다** —
    장면 코드는 앞 블록과 이 블록을 한 버퍼에 이어 붙여 한 번에 그리므로, 첫 줄이 14칸 안에 안 들어가면 엔진이
    다시 접어 한 낱말 외톨이 줄이 남는다(ED2SCN2 354→355 「대로」). 고치는 법: 첫 줄을 이어 붙는 폭에 맞춰 `{n}` 으로 끊는다.
 ② 최종 바이트에서 **쪽 끝 개행 + 대기(`%c`) 바로 뒤가 공백** — ▽ 뒤 새 줄 첫 칸이 한 칸 들여쓰기로 보인다(ED1SCN3 470).
    (개행 없이 같은 줄에 이어 쓰는 대기는 공백이 낱말 사이 공백이라 정상이다.)

핫픽스 문안까지 보려면 `ED_HOTFIX=1`(check.sh 가 그렇게 부른다).
  python3 tools/check_join_blocks.py
"""

import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")
os.environ.setdefault("ED_HOTFIX", "1")

import reinsert_kr_pilot as R
from check_window_nl import SCN_COUNT, raws_of
from text import krwrap as K

WIDTH = float(R.WRAP)
WIDOW = 4.0  # 이 칸 이하 줄이 쪽 중간에 남으면 외톨이(「대로」 2칸)


def _last_line(t):
    pg = R.wrap_page(t)
    return pg[-1][-1] if pg and pg[-1] else ""


def scan_join(script):
    fails, n = [], 0
    for scn, blocks in script.items():
        for k, v in blocks.items():
            if k.startswith("_") or not k.isdigit():
                continue
            t = v.get("t") if isinstance(v, dict) else v
            prev = blocks.get(str(int(k) - 1))
            if not t or not t.startswith(R.NOBREAK_SP) or prev is None:
                continue
            pt = prev.get("t") if isinstance(prev, dict) else prev
            if not pt:
                continue
            if pt.rstrip()[-1:] in ".?!…」』”~\n}" or "{" in pt[-3:]:  # 앞 블록이 문장·쪽을 닫았으면 이어 받는 게 아니다(상점 조사 칸 등)
                continue
            n += 1
            last = _last_line(pt).rstrip()
            first = R.wrap_page(t[len(R.NOBREAK_SP) :].replace("{n}", R.HARD_NL))[0][0].strip()
            # 엔진 쪽 접기는 **탐욕적**이다(조판기의 균형 잡힌 나눔이 아니다): 이어 붙인 줄이 14칸을 넘으면
            # 들어가는 데까지 채우고 나머지를 다음 줄로 보낸다 — 그 나머지가 외톨이면 실화면에서 눈에 띈다.
            cur, rest = last, []
            for w in first.split():
                if not rest and K.text_width((cur + " " + w).strip()) <= WIDTH:
                    cur = (cur + " " + w).strip()
                else:
                    rest.append(w)
            tail = " ".join(rest)
            if rest and K.text_width(tail) <= WIDOW and tail[-1] not in ".?!…」』”~":
                fails.append(f"{scn}:{k} 이어 붙이면 외톨이 줄 「{tail}」 — 「{last} {first}」: 첫 줄을 이어 붙는 폭에 맞춰 {{n}} 으로 끊는다")
    return fails, n


def scan_bytes():
    fails = []
    with contextlib.redirect_stdout(io.StringIO()):
        for game in ("ED1", "ED2"):
            for n in range(1, SCN_COUNT[game] + 1):
                name = f"{game}SCN{n}"
                tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
                for eid, raw in raws_of(name).items():
                    t = tr.get(eid)
                    if not t:
                        continue
                    try:
                        cand, _ = R.build_candidate(raw, t, eid)
                    except Exception:
                        continue
                    if cand is not None and b"\x0a%c " in cand and b"\x0a%c " not in raw:
                        fails.append(f"{name}:{eid} 쪽 끝 개행+대기 뒤 새 줄 첫 칸 공백")
    return fails


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        script = R._load_script()
    fails, n = scan_join(script)
    fails += scan_bytes()
    print(f"이어 받는 블록 검사 [ps1-ed1+2] — 이어 받는 블록 {n}건")
    for f in fails:
        print("  ❌", f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
