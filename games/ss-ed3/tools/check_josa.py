"""**고유명사 뒤 조사**가 받침과 맞나 — 정적 검사.

🔴 이 검사가 있는 이유는 **표기를 바꾸면 조사가 깨지기 때문**이다. 실측 2026-08-28:
`ラウアール` 를 「라우아르」→「라우알」로 고치자 「라우아르가」가 **「라우알가」**가 됐고
(`알` 은 받침이 있어 「이」여야 한다), `大蛇` 를 「이무기」→「큰뱀」으로 맞추자 「큰뱀를」·
「큰뱀와」가 여섯 자리 생겼다. 이름 치환은 **한 줄이면 되는데 조사는 따라오지 않는다.**

검사는 둘이다:

  ① **고유명사 뒤** — 공용 사전(`shared/canon/nouns/ed3.json`)에 있는 이름은 받침이 확정이라 판정이
     흔들리지 않는다. ⚠ 정본에 **없는** 이름은 안 보인다 — 실측 2026-09-03: `大蛇`가
     `evidence` 에만 있고 `categories` 엔 없어서 「큰뱀를」 넷·「큰뱀는」 하나를 **다섯 달
     동안 못 봤다.** 표기를 정본에 넣는 것이 곧 검사 범위다.
  ② **일반 낱말 뒤 을/를·과/와** — 은/는·이/가 는 어미(`있는`·`뭔가`)와 겹쳐 소음이지만,
     을/를·과/와 는 갈린다. 다만 `마을`·`무화과`처럼 **그 음절이 낱말의 일부**인 게 있어서
     받침만 보면 167 건이 헛걸린다. ⇒ **앞말이 딴 자리에서 홀로 쓰이는 낱말인가**를 같이
     본다(`큰뱀 등뼈` 의 `큰뱀` 은 홀로 쓰이고, `마을을` 의 `마` 는 아니다).
     실측: 이 규칙으로 전 코퍼스 헛걸림 **0**, `큰뱀를`·`쥬리오을` 은 잡는다.

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
SAFE = frozenset({"사나이", "사나이란"})

# (받침 있을 때, 받침 없을 때)
PAIRS = (
    ("은", "는"),
    ("이", "가"),
    ("을", "를"),
    ("과", "와"),
    #   서술격 「이다」 활용 — 받침 없으면 「이」가 빠진다. 「사막의흑표이라는」 둘이 이 구멍으로 샜다(10-02)
    ("이라는", "라는"),
    ("이란", "란"),
    ("이라고", "라고"),
)
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
        "("
        + "|".join(re.escape(n) for n in ns)
        + r")(이라는|라는|이란|이라고|라고|은|는|이|가|을|를|과|와|란)(?![가-힣])"
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


WORD = re.compile(r"[가-힣]+")
GEN = re.compile(r"([가-힣]{2,12})(을|를|과|와)(?![가-힣])")


def _walk(v, out):
    if isinstance(v, str):
        out.append(v)
    elif isinstance(v, dict):
        for x in v.values():
            _walk(x, out)
    elif isinstance(v, list):
        for x in v:
            _walk(x, out)


def load(paths):
    """`[(파일, 키, 문안)]` — 중첩된 값까지 다 편다."""
    out = []
    for f in paths:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        for k, v in d.items():
            if k.startswith("_"):
                continue
            acc = []
            _walk(v, acc)
            out += [(f, k, s) for s in acc]
    return out


def scan_general(rows):
    """일반 낱말 뒤 **을/를·과/와** — 앞말이 홀로도 쓰이는 낱말일 때만 본다."""
    tok = set()
    for _, _, s in rows:
        tok.update(WORD.findall(s))
    bad = []
    for f, k, s in rows:
        for m in GEN.finditer(s):
            w, j = m.group(1), m.group(2)
            has = batchim(w[-1]) != 0
            if (j in ("을", "과")) == has or w not in tok:
                continue
            right = {"을": "를", "를": "을", "과": "와", "와": "과"}[j]
            bad.append(
                (os.path.basename(f), k, w + j, w + right, s[max(0, m.start() - 14) : m.end() + 10])
            )
    return bad


def main():
    paths = sorted(glob.glob(os.path.join(C.GAME_DIR, "script", "*.json"))) + sorted(
        glob.glob(os.path.join(C.GAME_DIR, "script", "book", "*.json"))
    )
    bad = scan(paths)
    gen = scan_general(load(paths))
    for f, k, got, want, ctx in bad + gen:
        print(f"  ❌ {f}#{k}  {got!r} → {want!r}")
        print(f"       …{ctx.replace(chr(10), ' ').replace(chr(12), ' ')}…")
    print(f"고유명사 뒤 {len(bad)} · 일반 낱말 뒤 {len(gen)} 어긋남 / 이름 {len(names())}")
    raise SystemExit(1 if bad or gen else 0)


if __name__ == "__main__":
    main()
