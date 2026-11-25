"""이음 표(`script/key_cont.json`)가 현재 문안과 맞나 — 문안에서 다시 계산해 저장된 표와 다르면 실패.

    python3 games/ss-ed1+2/tools/check_key_cont_stale.py

🔴 이유(10-30 전 대사 촬영): 표의 커서 폭은 「앞 메시지의 끝 줄이 어디서 끝났나」를 대사 보기로 실측한 값인데, 문안을 고치면 앞 줄 폭이 바뀌어
표가 낡는다. ED1 해적 「…꺼냈다니까.너 / 무하지」 — 표 14.0(줄 끝이라 엔진이 접는다는 가정)인데 앞 줄이 13.0 이 됐다. 기존 게이트
`check_key_cont_width` 는 **표를 믿고** 그 값으로 첫 줄 폭을 재서(되읽기) 표 자체가 낡은 건 못 본다 — 검사기 자신의 커버리지 구멍.
방법: `chains`(앞 메시지 → 이어 그려지는 메시지)마다 앞 메시지 문안의 끝 줄 폭 — 앞 메시지가 한 줄뿐이면 그 메시지의 커서까지 더한다 —
을 계산해 표의 값과 같은지(±0.25 칸) 본다. 이어 붙는 메시지가 여러 앞 메시지 뒤에 올 수 있어 계산값 중 하나와 같으면 통과.
⚠ 표를 `derive_key_cont` 로 다시 뽑으면 이미 개행 보정이 걸린 롬에서 0 이 나와 순환한다 — 이 검사기의 계산값이 정본 대조다.
"""

import collections
import itertools
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared")
)
import common as C

TOL = 0.25


def _lines(kr):
    return re.sub(r"%c", "", kr.replace("\x08", "\n")).split("\n")


def stale(kc, kr_by_key, width):
    """`(어긋난 [(게임, 열쇠, 표값, 계산값들)], 대조한 칸 수, 표 칸 수)`."""
    bad, seen, total = [], 0, 0
    for g in ("ED1", "ED2"):
        tab = kc.get(g, {})
        total += len(tab)
        preds = collections.defaultdict(set)
        for ch in kc.get("chains", {}).get(g, []):
            cur = tab.get(ch[0], 0)
            for a, b in itertools.pairwise(ch):
                if a not in kr_by_key:
                    break
                ls = _lines(kr_by_key[a])
                w = width(ls[-1]) + (cur if len(ls) == 1 else 0)
                preds[b].add(w)
                cur = w
        for b, tb in tab.items():
            if b not in preds:
                continue
            seen += 1
            if not any(abs(p - tb) <= TOL for p in preds[b]):
                bad.append((g, b, tb, sorted(preds[b])))
    return bad, seen, total


def main():
    import names_corpus as N
    from text.line_key import key as line_key
    from typeset_scn import width

    kr = {}
    for site, jp, k, *_ in N.pairs():
        if k is not None and site.startswith("scn:"):
            kr.setdefault(line_key(jp), k)
    with open(os.path.join(C.GAME_DIR, "script", "key_cont.json"), encoding="utf-8") as f:
        kc = json.load(f)
    bad, seen, total = stale(kc, kr, width)
    print(f"  이음 표 신선도 — 표 {total}칸 · 문안으로 다시 계산한 칸 {seen} · 어긋남 {len(bad)}")
    for g, b, tb, ps in bad:
        print(
            f"    ✗ {g} {b}: 표 {tb} · 앞 글 끝 줄 계산 {ps} — 표가 낡았다(대사 보기로 다시 실측해 값을 고친다)"
        )
    if seen == 0:
        print("    ✗ 대조한 칸이 0 — 0 은 통과가 아니라 「안 쟀다」")
        return 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
