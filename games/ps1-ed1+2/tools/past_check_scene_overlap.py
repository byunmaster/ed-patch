#!/usr/bin/env python3
"""두 씬이 **같은 정발 엔트리**를 문 자리를 점수차 순으로 보고한다 (ED2 전용 실패 방식).

ED1 에는 없던 층이다 — ED1 은 씬↔정발 그룹이 1:1이라 후보 집합이 서로 겹치지 않았다.
ED2 는 정발 한 그룹이 여러 PS1 씬에 걸리므로(그룹0 → 씬1+2, 그룹2 → 씬4+5+13) 같은 정발
문장을 **두 씬이 각자 자기 것이라 주장할 수 있다.** 헝가리안은 씬마다 따로 풀리니 서로를
모른다.

⚠ **겹침 자체는 오류가 아니다.** 정발 한 엔트리가 PS1 여러 블록에 쓰이는 건 이 프로젝트의
일상이고(시점 사본·페이지 슬라이스·chain), 씬을 넘어도 마찬가지다 — 같은 대사를 진행
단계별로 다시 쓰는 자리가 실재한다. 그래서 **자동으로 지우지 않는다.**

판정에 쓰는 건 **점수차**다. 한쪽이 0.95인데 다른 쪽이 0.50이면 낮은 쪽은 헝가리안이
자리를 채우느라 억지로 물린 것이다(실측: 씬1 이 루디아 성 표 `C_00x` 를 0.5 대로 물었고
같은 엔트리를 씬2 가 0.9 대로 물고 있었다). 점수가 비슷하면 진짜 공유일 가능성이 높다.

  python3 tools/check_scene_overlap.py            # ED2 요약 + 점수차 큰 순
  python3 tools/check_scene_overlap.py ED2 -v     # 전부
"""

import collections
import glob
import json
import os
import sys

from common import OUT_DIR

ALIGN = os.path.join(OUT_DIR, "align")
GAP_SUSPECT = 0.15  # 이 이상 벌어지면 낮은 쪽을 의심한다


def claims(game):
    """(표, 엔트리) → [(씬, jp_id, 점수)] · {씬: (jp수, kr후보수, 매칭수)}"""
    by_kr = collections.defaultdict(list)
    stats = {}
    for p in sorted(glob.glob(os.path.join(ALIGN, f"{game}_SCN*.json"))):
        scn = int(os.path.basename(p)[:-5].split("_SCN")[1])
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        n = 0
        for pair in doc["pairs"]:
            if not pair.get("jp") or not pair.get("kr"):
                continue
            n += 1
            by_kr[(pair["kr"]["table"], pair["kr"]["entry_id"])].append(
                (scn, pair["jp"]["entry_id"], pair.get("score") or 0.0)
            )
        stats[scn] = (doc["jp_blocks"], doc["kr_blocks"], n)
    return by_kr, stats


def main(game="ED2", verbose=False):
    by_kr, stats = claims(game)
    if not stats:
        print(f"{game}: 정렬 파일 없음 — `python3 tools/past_align_semantic.py` 먼저")
        return 0

    print(f"{'씬':>3} {'JP':>6} {'KR후보':>7} {'매칭':>6} {'JP회수율':>9}")
    for s in sorted(stats):
        jp, kr, m = stats[s]
        print(f"{s:>3} {jp:>6} {kr:>7} {m:>6} {100 * m / max(jp, 1):>8.1f}%")

    multi = {k: v for k, v in by_kr.items() if len({s for s, _, _ in v}) > 1}
    print(f"\n두 씬 이상이 문 정발 엔트리 {len(multi)} / 전체 청구 {len(by_kr)}")
    pairs = collections.Counter()
    for v in multi.values():
        seen = sorted({s for s, _, _ in v})
        for i, a in enumerate(seen):
            for b in seen[i + 1 :]:
                pairs[(a, b)] += 1
    for (a, b), c in pairs.most_common():
        print(f"  씬{a} ↔ 씬{b}: {c}건")

    # 점수차가 큰 순 — 낮은 쪽이 억지 매칭 후보다
    ranked = sorted(
        multi.items(),
        key=lambda kv: max(s for _, _, s in kv[1]) - min(s for _, _, s in kv[1]),
        reverse=True,
    )
    susp = [
        kv
        for kv in ranked
        if max(s for _, _, s in kv[1]) - min(s for _, _, s in kv[1]) >= GAP_SUSPECT
    ]
    print(f"\n점수차 {GAP_SUSPECT} 이상(낮은 쪽 의심) {len(susp)}건")
    for (tbl, eid), v in susp[: (None if verbose else 20)]:
        best = max(s for _, _, s in v)
        cells = " · ".join(
            f"{'✔' if s == best else '✗'}씬{scn} jp{jp}({s:.2f})" for scn, jp, s in sorted(v)
        )
        print(f"  {tbl}#{eid}: {cells}")
    if not verbose and len(susp) > 20:
        print(f"  … 그 밖 {len(susp) - 20}건 (-v 로 전부)")
    return 0  # 보고만 한다 — 겹침은 정상일 수 있다


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    sys.exit(main(args[0] if args else "ED2", "-v" in sys.argv))
