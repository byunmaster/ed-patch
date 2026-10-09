#!/usr/bin/env python3
"""조사 일치 상주 검사(F8) — **이름 뒤 조사가 받침과 맞나** + **조사 병기가 안 풀린 채 남았나**.

    python3 tools/check_josa.py --disc ed3

잡는 것 둘(둘 다 번역 정본 `script/` · UI 정본 `ui_*.json` 의 우리 문안):
1. 🔴 **병기 잔존** — 한글 뒤에 「을(를)」 같은 병기가 남았다. 빌드(`josa_rt.convert`)가 앞 글자 받침으로 확정하거나(고정 문자열 뒤)
   런타임 표지로 바꾸는(조각 첫머리) 것이라 **문안에 남아 있어도 화면엔 안 나가지만**, 앞이 한글인데 못 푼 병기가 문안에 남으면
   (예: 「…도 읽어(를)」 처럼 앞 글자를 못 정하는 자리) 사람이 고칠 자리다.
2. 🔴 **이름 뒤 조사 불일치** — 사전 이름(고유명사 정본)·화자명 바로 뒤에 은/는·이/가·을/를·과/와 가 오는데 받침과 안 맞는다.
   ⚠ 이름을 앞세운 정확 일치만 본다(일반 명사 뒤는 「나이가」 같은 낱말 속 글자와 구별이 안 돼 못 센다) — 그래서 분모를 같이 찍는다.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import glossary
import josa_rt
import script as script_canon

_PARTICLES = {"은": 1, "는": 0, "이": 1, "가": 0, "을": 1, "를": 0, "과": 1, "와": 0}  # 받침 필요(1)/불필요(0)
_TOKEN = re.compile("|".join(re.escape(k) for k in sorted(josa_rt._PAIRS, key=len, reverse=True)))


def names(disc):
    out = set(glossary.flat(disc).values())
    sys.path.append(os.path.join(os.path.dirname(os.path.dirname(common.ROOT)), "shared"))
    import canon

    out |= set(canon.table("speaker", disc).values()) if disc == "ed3" else set()
    return sorted((n for n in out if len(n) >= 2 and " " not in n), key=len, reverse=True)


def texts(disc):
    for (_a, member), rows in script_canon.load(disc).items():
        for i, row in sorted(rows.items()):
            yield f"{member}#{i}", row["kr"]
    p = os.path.join(common.ROOT, f"ui_{disc}.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for off, row in json.load(f)["strings"].items():
                if row.get("kr"):
                    yield f"ui:{off}", row["kr"]


def check(disc):
    nm = names(disc)
    bad, leftover, seen = [], [], 0
    pat = re.compile("(" + "|".join(re.escape(n) for n in nm) + ")([은는이가을를과와])(?![가-힣])") if nm else None
    for where, kr in texts(disc):
        for mo in _TOKEN.finditer(kr):
            if mo.start() > 0 and "가" <= kr[mo.start() - 1] <= "힣":
                leftover.append(f"{where}: 「{kr[max(0, mo.start() - 6) : mo.end()]}」 병기가 앞말 뒤에 남았다")
        if pat:
            for mo in pat.finditer(kr):
                seen += 1
                need = _PARTICLES[mo.group(2)]
                k = josa_rt.klass(mo.group(1)[-1])
                has = 1 if k else 0
                if k is not None and has != need:
                    bad.append(f"{where}: 「{mo.group(0)}」 받침과 조사가 안 맞는다")
    return bad, leftover, seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3")
    a = ap.parse_args()
    bad, leftover, seen = check(a.disc)
    print(f"{a.disc}: 조사 일치 — 이름 뒤 조사 {seen}곳 확인 · 불일치 {len(bad)} · 병기 잔존 {len(leftover)}")
    for m in bad + leftover:
        print(f"  🔴 {m}")
    return 1 if (bad or leftover) else 0


if __name__ == "__main__":
    sys.exit(main())
