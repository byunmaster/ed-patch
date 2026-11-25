"""색 범위 대조 (번역 규칙 4-6) — 원판의 색 켜기/끄기 `%c` 짝이 빌드 바이트에서 **같은 모양**으로 남았나.

    python3 tools/check_color_span.py            # 축별 수 (새로 생긴 갈림이 있으면 종료코드 1)
    python3 tools/check_color_span.py --show 8   # 축마다 표본

`%c` 하나 = 호출처가 넘기는 인자 한 바이트다(`callargs.py`: 2·3 색 켜기 · 1 끄기). 호출 코드는 번역이 안 건드리므로
인자열은 원판과 같고, **빌드가 `%c` 를 어디에 놓았나**만 달라진다. 토큰 열이 같은지는 `check_ctrl_codes` 가 보고,
여기서는 그 짝이 둘러싼 **범위**를 본다.

    누락      원판엔 켜기 인자가 있는 짝이 있는데 빌드엔 그 짝(켜기·끄기)이 없다 — 색이 통째로 사라진다
    안 닫힘   빌드에서 켜기 뒤 끄기가 없다(원판은 닫혔다) — 색이 뒤 대사까지 번진다
    빈 범위   원판 범위는 글이 있는데 빌드는 비었다
    범위 쪼개짐 이름·낱말을 칠하는 짧은 범위(인자 2)에 원판엔 없던 개행·쪽 넘김이 생겼다 — 색 낱말이 줄/쪽에 걸쳐 갈린다
              (문장을 칠하는 범위(인자 3)가 줄을 접는 건 정상이다)
"""

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import callargs
import check_ctrl_codes as C
import common

ON, OFF = (2, 3), (1,)
SHORT = 24  # 원판 범위 바이트 수 상한 — SJIS 12자
AXES = ("누락", "안 닫힘", "빈 범위", "범위 쪼개짐")
# 알려진 갈림 — 사유를 확인한 것만 올린다(래칫). 키: 축.
KNOWN = {}


def spans(raw, args):
    """`(조각들, [(색 인자, 조각 번호)])` — 색 인자(2·3)로 켠 범위가 `%c` 사이 어느 조각인가."""
    parts = raw.split(b"%c")
    return parts, [(a, i) for i, a in enumerate(args[: len(parts) - 1]) if a in ON]


def compare(orig, new, args):
    """블록 하나의 원판·빌드 바이트 → `{축: 1}` ."""
    bad = {}
    po, so = spans(orig, args)
    pn, sn = spans(new, args)
    if len(po) != len(pn) or so != sn:
        bad["누락"] = 1  # `%c` 수가 다르면 색 인자가 밀린다(check_ctrl_codes 와 겹치는 안전망)
        return bad
    for a, i in so:
        o_txt, n_txt = po[i + 1], pn[i + 1]
        if i + 1 >= len(po) - 1 and i + 1 == len(po) - 1:
            # 마지막 `%c` 가 켜기로 끝난다 — 원판도 그렇다. 빌드가 그 뒤에 글을 더 붙이면 색이 뒤로 번진다
            if not o_txt.strip(b"\n ") and n_txt.strip(b"\n \x08"):
                bad["안 닫힘"] = 1
            continue
        if o_txt.strip(b"\n ") and not n_txt.strip(b"\n \x08"):
            bad["빈 범위"] = 1
        # 짧은 이름·낱말 범위(원판 12자 이하)가 줄/쪽에 걸쳐 갈리면 안 된다. 문장 길이 범위는 긴 글이 접히는 게 정상이다
        if (
            a == 2
            and len(o_txt) <= SHORT
            and not (b"\n" in o_txt or b"\x08" in o_txt)
            and (b"\n" in n_txt or b"\x08" in n_txt)
        ):
            bad["범위 쪼개짐"] = 1
    return bad


def scan():
    built = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    orig, new = C._load(common.ORIG_BIN), C._load(built)
    hits = collections.defaultdict(list)
    blocks = 0
    for p, od in orig.items():
        cargs = callargs.for_file(p)
        bmap = {tuple(e["ptr_at"]): e for e in new.get(p, {"entries": []})["entries"]}
        for e in od["entries"]:
            args = cargs.get(e.get("text", ""))
            if args:  # 인자열은 `%c`·`%s`·`%d` 전부의 것 — `%c` 몫만 남긴다
                args = [x for x, t in zip(args, callargs.MARK.findall(e["text"]), strict=False) if t == "%c"]
            be = bmap.get(tuple(e["ptr_at"]))
            if not args or be is None or not any(a in ON for a in args):
                continue
            blocks += 1
            ob, nb = bytes.fromhex(e["raw_hex"]), bytes.fromhex(be["raw_hex"])
            for k in compare(ob, nb, args):
                hits[k].append(f"{p.rsplit('/', 1)[-1]}#{e['entry_id']}")
    return blocks, hits


def main():
    show = int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 0
    blocks, hits = scan()
    print(
        f"  색 범위 대조 4-6 [색 짝 블록 {blocks:,}] — "
        + " · ".join(f"{a} {len(hits.get(a, ()))}" for a in AXES)
    )
    for a in AXES:
        for x in hits.get(a, ())[:show]:
            print(f"      [{a}] {x}")
    bad = {
        a: len(hits.get(a, ())) - KNOWN.get(a, 0)
        for a in AXES
        if len(hits.get(a, ())) > KNOWN.get(a, 0)
    }
    if bad:
        print("  🔴 새 갈림 — " + " · ".join(f"{a} +{v}" for a, v in bad.items()))
    if not bad:
        print("  ✅ 색 범위 — 원판 색 짝이 빌드에 같은 모양으로 남았다")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
