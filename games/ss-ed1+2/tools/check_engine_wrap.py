"""엔진이 접은 뒤의 화면을 재현해 **창을 넘는 창**과 **줄머리 부호**를 센다.

    python3 tools/check_engine_wrap.py            # 수치만
    python3 tools/check_engine_wrap.py --show 12  # 표본을 보여 준다

## 왜 따로 있나 — `typeset_scn.fits` 는 **총량만** 본다

새턴 엔진은 우리가 아니라 **자기가** 줄을 접는다(글자 단위). 그래서 조판기는 문단 개행만
넣고 창 총량(`COLS × ROWS`)만 지킨다. 그 전제는 맞지만 **총량이 같아도 접히는 자리가
다르면 줄 수가 달라진다** — 15자에 딱 안 떨어지는 낱말이 줄마다 반 칸씩 흘리면 5줄이
6줄이 된다. 총량 검사로는 안 보인다.

🔴 **접기 규칙의 정본은 `typeset_scn` 이다** — 여기서 다시 쓰지 않는다(체크리스트 4-D).
   한 줄 = **전각 14 = 반각 28**, 창은 **7행**(RAM 눈금자 실측 2026-08-31, status 6-0절).

⚠ 이 파일은 **읽기 전용 계측**이다 — 고치지 않고 세기만 한다. 무엇을 할지(문안을 줄일지,
  밀어내기 조건을 손볼지)는 사람이 정한다.
"""

import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import patch_scn
import typeset_scn

# 🔴 **규칙의 정본은 조판기다** — 여기서 다시 쓰지 않는다(체크리스트 4-D).
#    `lines`(엔진 접기) · `HEAD_BAN`(금칙) · `WIN_ROWS`(창 6행) · `nudge`(밀어내기)가
#    전부 `typeset_scn` 것이다. 이 파일은 **세기만** 한다.
from typeset_scn import HEAD_BAN, WIN_ROWS, lines


def scan(body):
    """`(줄 수가 넘는 창들, 줄머리 부호들)`."""
    over, head = [], []
    for seg in body.split("%c"):
        ls = lines(seg)
        if len(ls) > WIN_ROWS:
            over.append((len(ls), seg))
        for prev, ln in itertools.pairwise(ls):
            if ln and ln[0] in HEAD_BAN and prev:
                head.append((ln[0], prev, ln))
    return over, head


def main():
    show = int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 0
    canon = patch_scn.load_canon()
    _f, mm = common.open_image()
    canon = patch_scn.augment_names(canon, mm)
    names = typeset_scn._names()
    blocks = over = head = 0
    ex_over, ex_head = [], []
    for path in (p for p, _l, _s in common.iso_files(mm) if patch_scn.SCN_RE.match(p)):
        got = patch_scn.load(path)
        if not got:
            continue
        _base, entries = got
        for e in entries:
            jp = e.get("text", "")
            kr = patch_scn._canon_get(canon, jp)
            if not kr:
                continue
            built, _bad = typeset_scn.typeset(jp, kr, names)
            if not built:
                continue
            blocks += 1
            o, h = scan(built)
            over += len(o)
            head += len(h)
            ex_over += [(path, *x) for x in o]
            ex_head += [(path, *x) for x in h]
    mm.close()
    _f.close()

    print(f"조판된 블록 {blocks:,}")
    print(f"  🔴 {WIN_ROWS}행을 넘는 창 {over:,}  — 뒷줄이 화면에서 잘린다")
    print(f"  ⚠ 줄머리에 부호가 온 자리 {head:,}  — 금칙 위반(잘리진 않는다)")
    for path, n, seg in ex_over[:show]:
        print(f"     [{n}행] {path} {seg[:60]!r}")
    for _path, ch, prev, ln in ex_head[:show]:
        print(f"     [{ch}] …{prev[-14:]!r} / {ln[:14]!r}")
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())
