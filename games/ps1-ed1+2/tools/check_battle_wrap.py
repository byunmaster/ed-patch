#!/usr/bin/env python3
"""전투 메시지가 **꼬리 한 글자만 다음 줄로 넘기는지** 본다 — 이름 길이는 런타임 결정이다.

**왜.** 전투 문자열은 우리 조판기(`krwrap`)가 못 닿는다. 엔진이 `%s` 에 이름을 넣고
**29 반각칼럼**에서 스스로 꺾기 때문이다(`patch_battle_wrap` 규명). 그래서 화면에서만
드러난다 — 유저 QA 에서 「세리오스는 전투에서 패배했다」 뒤 **온점 하나만 다음 줄로** 떨어져
발견됐다(2026-08-13). 폭이 딱 0.5슬롯 모자랐다.

**어떻게.** 이름이 붙는 조각을 **최장 파티명(`세리오스`)** 기준으로 재서, 마지막 줄에
1~2칼럼만 남는 자리를 보고한다. 최장으로 재는 이유는 그게 최악이라서다 — 짧은 이름에서
멀쩡해 보여도 세리오스가 들어가면 꺾인다.

⚠ **게이트가 아니다.** 꼬리가 짧아도 문장에 따라 자연스러운 자리가 있고, 무엇보다 고치려면
문안을 줄여야 한다 — 사람이 판정한다. `%d` 가 든 조각은 숫자 자릿수가 가변이라 건너뛴다.

  python3 tools/check_battle_wrap.py [-v]
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import patch_items as P

COLS = 29  # 엔진 자동 줄바꿈 폭(반각칼럼) — patch_battle_wrap 규명
LONGEST = "세리오스"  # 최장 파티명. 이름이 길수록 불리하니 최악으로 잰다
TAIL_MIN = 2  # 마지막 줄에 이만큼 이하만 남으면 보고


def cols(s):
    """반각칼럼 수 — 한글·전각은 2, 나머지는 1."""
    return sum(2 if ord(c) > 0x2000 else 1 for c in s)


def _expand(line):
    """런타임 모습으로 편다 — `%s`·조사 병기 자리에 최장 이름을 넣는다.

    ⚠ 조사 병기(`은(는)`)는 훅이 앞말에 맞춰 **한 글자로 줄인다** — 표기 그대로 재면
    네 칸을 더 세어 오탐이 난다.
    """
    s = re.sub(r"%c|[\x17\x1a\x1b]", "", line)
    # 훅은 **앞말 받침**을 보고 고른다 — 최장 이름 `세리오스` 는 받침이 없어 뒤쪽이 선다.
    has_jong = (ord(LONGEST[-1]) - 0xAC00) % 28 != 0
    pick = {"은(는)": "은" if has_jong else "는", "이(가)": "이" if has_jong else "가",
            "을(를)": "을" if has_jong else "를"}
    s = re.sub(r"은\(는\)|이\(가\)|을\(를\)", lambda m: pick[m.group(0)], s)
    s = s.replace("%s", LONGEST)
    # 이름이 앞에 붙는 조각은 조사·조사구로 시작한다
    if re.match(r"^(은|는|이|가|을|를|에게|의)\b|^(은|는|이|가|을|를)\s", s):
        s = LONGEST + s
    return s


def scan(verbose=False):
    orig = P.extract(P.ED_LBA, P.ED_SIZE)
    seen, hits = set(), []
    for _off, _end, jp in P.corpus_strings(orig):
        kr = P.battle_kr(jp)
        if not kr or jp in seen:
            continue
        seen.add(jp)
        for line in kr.split("\n"):
            s = line.strip()
            if not s or "%d" in s:  # 숫자 자릿수가 가변이라 못 잰다
                continue
            w = cols(_expand(s))
            tail = w % COLS
            if w > COLS and 0 < tail <= TAIL_MIN:
                hits.append((w, tail, _expand(s)))
    hits.sort(key=lambda h: (h[1], -h[0]))
    # ⚠ 요약은 **마지막에** — `check.sh` 가 각 검사기 출력을 `tail -3` 으로 줄여 보여준다.
    for w, tail, s in hits if verbose else hits[:3]:
        print(f"      {w:3d}칼럼 → 꼬리 {tail}  {s}")
    if hits:
        print("      ⚠ 게이트가 아니다 — 문안을 줄여야 풀리니 사람이 판정한다(`-v` 로 전량).")
    print(f"  {'✅' if not hits else '⚠'} 전투 꼬리 개행 {len(hits)}건 (최장 이름 기준 {COLS}칼럼)")
    return len(hits)


if __name__ == "__main__":
    scan(verbose="-v" in sys.argv)
