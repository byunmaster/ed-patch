"""**고유명사 뒤 조사**가 받침과 맞나 — 정적 검사.

🔴 이 검사가 있는 이유는 **표기를 바꾸면 조사가 깨지기 때문**이다. 실측 2026-08-28:
`ラウアール` 를 「라우아르」→「라우알」로 고치자 「라우아르가」가 **「라우알가」**가 됐고
(`알` 은 받침이 있어 「이」여야 한다), `大蛇` 를 「이무기」→「큰뱀」으로 맞추자 「큰뱀를」·
「큰뱀와」가 여섯 자리 생겼다. 이름 치환은 **한 줄이면 되는데 조사는 따라오지 않는다.**

⚠ **고유명사 뒤만 본다.** 일반 문장까지 보면 `먹는`·`가는` 같은 어미가 죄다 걸려 소음이
된다. 정본(`glossary_manual.json`)에 있는 이름은 받침이 확정이라 판정이 흔들리지 않는다.

    python3 games/ss-ed3/tools/check_josa.py

⚠ 게이트다 — 어긋나면 실패한다.
"""

import glob
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(_HERE))), "shared"))

import check_fidelity as CF
import common as C
from text.josa import batchim

#   ⚠ **이름 + 조사가 그대로 한 낱말인 자리**는 뺀다. 짧은 이름일수록 걸린다 —
#     `サーナ`=「사나」 뒤에 「이」가 오면 「사나이」(男)가 되는데, 검사기는 조사로 읽고
#     「사나가」로 고치라 한다(실측 2026-08-28, BOOK13 「일곱 바다를 건넌 사나이」).
#     정본에서 그 이름을 뺄 일은 아니고 — 그 이름 자체는 맞다 — 이 짝만 눈감는다.
SAFE = frozenset({"사나이"})

# (받침 있을 때, 받침 없을 때)
PAIRS = (("은", "는"), ("이", "가"), ("을", "를"), ("과", "와"))
FLAT = {j: (i, k == 0) for i, p in enumerate(PAIRS) for k, j in enumerate(p)}


def names():
    """정본의 한국어 표기 중 **조사를 붙여 쓰는 것**만 — 받침이 확정인 한글 이름."""
    out = set()
    for kr in CF.load_gloss().values():
        w = kr.split()[-1] if " " in kr else kr
        if len(w) >= 2 and all("가" <= c <= "힣" for c in w) and batchim(w[-1]) is not None:
            out.add(w)
    return sorted(out, key=len, reverse=True)


def scan(paths):
    bad = []
    pat = None
    ns = names()
    if not ns:
        return bad
    pat = re.compile(
        "(" + "|".join(re.escape(n) for n in ns) + r")(은|는|이|가|을|를|과|와)(?![가-힣])"
    )
    for f in paths:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        for k, v in d.items():
            if k.startswith("_") or not isinstance(v, str):
                continue
            for m in pat.finditer(v):
                name, j = m.group(1), m.group(2)
                has = batchim(name[-1]) != 0
                idx, want_has = FLAT[j]
                if has != want_has and (name + j) not in SAFE:
                    right = PAIRS[idx][0 if has else 1]
                    bad.append(
                        (
                            os.path.basename(f),
                            k,
                            name + j,
                            name + right,
                            v[max(0, m.start() - 14) : m.end() + 10],
                        )
                    )
    return bad


def main():
    paths = sorted(glob.glob(os.path.join(C.GAME_DIR, "script", "*.json"))) + sorted(
        glob.glob(os.path.join(C.GAME_DIR, "script", "book", "*.json"))
    )
    bad = scan(paths)
    for f, k, got, want, ctx in bad:
        print(f"  ❌ {f}#{k}  {got!r} → {want!r}")
        print(f"       …{ctx.replace(chr(10), ' ').replace(chr(12), ' ')}…")
    print(f"고유명사 뒤 조사 어긋남 {len(bad)} / 이름 {len(names())}")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
