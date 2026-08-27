"""저본의 **순수 문안**에 원문의 마크업을 다시 입힌다 — 조판기.

    python3 tools/typeset_scn.py          # 얼마나 조판되는지 센다
    python3 tools/typeset_scn.py --show 8 # 표본을 보여 준다

## 왜 필요한가

사전(`line_dict.json`)은 **문안만** 담는다 — 화자도 창 전환도 개행도 없다:

    JP  `%cライアス%c\\n王子、ちゃんと いすに 座って\\n…%c`
    KR  `왕자님, 의자에 얌전히 앉아 기다리고 계시옵소서. …`

그대로 넣으면 **구조 계약**(`%c`·`%s`·`%d` 의 개수와 순서)이 깨져 소프트락이 난다
(`docs/reference/our-findings.md`). 그래서 **원문의 마크업을 그대로 두고 텍스트 자리만**
우리 문안으로 갈아 끼운다.

## 어떻게 가르나 — 마크업으로 쪼개면 자리가 드러난다

원문을 `%c`/`%s`/`%d` 로 쪼개면 `[텍스트][마크업][텍스트]…` 가 번갈아 나온다.

    `%cライアス%c\\n본문%c`  →  텍스트 ['', 'ライアス', '\\n본문', '']  ·  마크업 ['c','c','c']

- **화자** — 앞이 `%c…%c` 꼴이면 그 사이가 화자다. 이름이라 **정본으로 번역**한다
  (`shared/glossary` person·monster·place). ⚠ `%c%s%c` 는 런타임 이름이라 그대로 둔다.
- **본문** — 화자를 뺀 텍스트 자리 중 **가장 긴 것**. 여기에 우리 문안을 넣는다.
- 나머지 자리는 **비운다**(원문에서도 대개 비어 있다).

실측(저본이 붙는 12,091 블록): `c` 5,013 · `ccc` 4,961 · 없음 755 · `cscc` 704 · `cc` 402
— **상위 다섯이 97.9%** 다.

## 🔴 조판은 못 하면 **안 한다**

- 마크업 개수·순서가 하나라도 달라지면 버린다(계약).
- 본문 자리를 못 고르면 버린다(자리가 둘 이상 크면 어디에 넣을지 근거가 없다).
- 창 총량(전각 15자 × 5행)을 넘으면 버린다 — 넘치면 뒷줄이 잘린다.
⚠ 「대충 넣고 나중에 고친다」가 안 되는 층이다. 계약 위반은 **오타가 아니라 소프트락**이다.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ),
        "shared",
    ),
)

import common
from glossary import table

MARK = re.compile(r"(%[csd])")
COLS = 15  # 창 한 줄 = 전각 15자 (status 6절, 실측)
ROWS = 5  # 본문 5행 (창 6행 중 화자가 1행)


def _names():
    """이름 정본 하나로 합친 것 — 화자는 사람·몬스터·지명 어디서든 온다."""
    out = {}
    for cat in ("person", "monster", "place"):
        out.update(table(cat))
    return out


def width(s):
    """전각 칸 수 — 반각은 0.5 로 센다(엔진이 그렇게 접는다)."""
    return sum(0.5 if c.isascii() else 1 for c in s)


def fits(body):
    """창 총량 안에 드나. ⚠ 엔진이 글자 단위로 접으므로 **총량만** 본다(status 6절)."""
    return width(body.replace("\n", "")) <= COLS * ROWS


def split(jp):
    """`(텍스트 자리들, 마크업들)` — 번갈아 나온다."""
    parts = MARK.split(jp)
    return parts[0::2], [p[1] for p in parts[1::2]]


def speaker_slot(marks):
    """화자가 든 텍스트 자리의 번호. 없으면 None.

    ⚠ `%c%s%c`(런타임 이름)는 **화자 자리가 아니다** — 인자라 우리가 손댈 게 없다.
    """
    return 1 if marks[:2] == ["c", "c"] else None


def body_slot(texts, skip):
    """본문이 든 자리 — 화자를 뺀 것 중 **가장 긴** 하나. 애매하면 None."""
    cand = [(len(t), i) for i, t in enumerate(texts) if i != skip and t.strip()]
    if not cand:
        return None
    cand.sort(reverse=True)
    if len(cand) > 1 and cand[0][0] == cand[1][0]:
        return None  # 어디에 넣을지 근거가 없다
    return cand[0][1]


def typeset(jp, kr, names):
    """`(우리 블록, 못 한 이유)` — 원문 마크업을 그대로 두고 텍스트만 간다."""
    texts, marks = split(jp)
    if not marks:
        return kr, None  # 마크업이 없다 — 그대로 쓴다
    sp = speaker_slot(marks)
    bi = body_slot(texts, sp)
    if bi is None:
        return None, "본문 자리를 못 고른다"
    if not fits(kr):
        return None, "창을 넘는다"
    out = list(texts)
    for i in range(len(out)):
        if i == sp:
            out[i] = names.get(texts[i], texts[i])  # 화자 — 정본 표기로
        elif i == bi:
            out[i] = kr
        else:
            out[i] = ""  # 나머지 자리는 비운다
    built = "".join(a + ("%" + m if m else "") for a, m in zip(out, marks + [""], strict=True))
    return built, None


def main():
    import patch_scn as P

    common.verify_source()
    names = _names()
    canon = P.load_canon()
    _f, mm = common.open_image()
    ok = 0
    why = {}
    show, shown = ("--show" in sys.argv and int(sys.argv[sys.argv.index("--show") + 1])), 0
    for path, _lba, _size in common.iso_files(mm):
        if not P.SCN_RE.match(path):
            continue
        got = P.load(path)
        if not got:
            continue
        for e in got[1]:
            jp = e.get("text", "")
            kr = P._canon_get(canon, jp)
            if not kr:
                continue
            built, bad = typeset(jp, kr, names)
            if bad or P.contract(built) != P.contract(jp):
                why[bad or "계약이 달라졌다"] = why.get(bad or "계약이 달라졌다", 0) + 1
                continue
            ok += 1
            if show and shown < show:
                shown += 1
                print(f"  JP {jp[:56]!r}\n  KR {built[:56]!r}\n")
    print(f"조판 성공 {ok:,}")
    for k, v in sorted(why.items(), key=lambda x: -x[1]):
        print(f"  ⏭ {k}: {v:,}")
    mm.close()
    _f.close()


if __name__ == "__main__":
    main()
