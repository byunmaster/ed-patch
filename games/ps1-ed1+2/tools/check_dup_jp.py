#!/usr/bin/env python3
"""⚠ **게이트 밖 · 정발 배정 시대 진단기**(2026-09-13 실측 — 자체 번역 전환 이후 재검토
없이 남았다). 손으로 돌리는 용도로만 쓴다.

**같은 원문인데 문안이 갈리는가** — 한 씬 안의 중복 블록을 대조한다.

**왜.** 원작은 같은 대사를 여러 블록에 복제해 둔다(상점·숙소·신부 응대는 마을마다, 이벤트
분기는 조건마다). 저본을 블록 단위로 옮기면 **같은 원문에 다른 문안**이 붙는다 — 화면에서는
같은 NPC 가 말을 걸 때마다 다르게 말하는 꼴이다. 실측으로 SCN3 도구점 한 벌에서만 31곳이
갈려 있었다(2026-08-12).

⚠ **전부 오류는 아니다.** 원문이 같아도 **화자가 다르면** 문안이 갈리는 게 맞다(주인공
넷이 같은 말을 하는 분기). 그래서 화자까지 묶어서 센다.

⚠ **게이트가 아니다.** 판정이 필요한 후보를 보여 줄 뿐이다 — 정발이 일부러 갈라 쓴 자리도
있고(사투리 상점 vs 표준어 상점), 그건 살리는 게 방침이다.

  python3 tools/check_dup_jp.py            # 전 씬 요약
  python3 tools/check_dup_jp.py ED1SCN3    # 한 씬, 자리마다
"""

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from check_align_fit import jp_text


def scan(scenes=None, verbose=False):
    tot = 0
    for scn in R.scene_list(scenes):
        if scenes and scn not in scenes:
            continue
        groups = collections.defaultdict(list)
        for _s, eid, jp, cand, _t in R.iter_candidates((scn,)):
            j = jp_text(jp).replace("　", " ").strip()
            if len(j) < 8:  # 「예」「아니오」같은 조각은 갈려도 무해하다
                continue
            groups[j].append((eid, R.render_bytes(cand, ctrl=False)))
        split = {j: v for j, v in groups.items() if len({k for _e, k in v}) > 1}
        tot += len(split)
        print(f"  {'✅' if not split else '⚠'} {scn}: 원문은 같은데 문안이 갈린 곳 {len(split)}")
        if verbose:
            for j, v in sorted(split.items(), key=lambda kv: -len(kv[1])):
                print(f"      jp{' jp'.join(str(e) for e, _ in v)}  ← {j[:40]}")
                for kr in sorted({k.replace("\n", " ") for _e, k in v}):
                    print(f"           {kr[:64]}")
    print(f"\n{'✅ 갈린 곳 없음' if not tot else f'⚠ 갈린 곳 {tot}종 — 판정용(게이트 아님)'}")
    return tot


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    scan(set(args) if args else None, verbose=bool(args) or "-v" in sys.argv)
