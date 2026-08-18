#!/usr/bin/env python3
"""정발 "사본"을 잘못 고른 배정을 찾아 그 구간의 주류 테이블로 되돌린다.

**왜(2026-08-04 실측, 유저 QA 다섯 번).** 정발은 **같은 방을 시점별 파일로 복제**해 두고
문구를 조금씩 손봤다(루디아 성 `C_001`(2장)↔`C_009`(후반), 마을 `T_013`↔`T_014`,
보물창고 `C_006`↔`C_00B`↔`C_00F`). PS1 도 인스턴스가 여럿인데 **정렬기는 이 사본들을 원리적으로
못 가른다** — JP 가 서로 같기 때문이다. 게다가 `recover_twins`(JP 동일 → 배정 복제)가
그 배분을 적극적으로 뭉갠다. 결과로 2장에서 후반 문구가 나온다.

**판정은 구간의 다수결로 한다.** PS1 블록을 맵·연속성으로 자르면 한 구간은 대체로 한두 개
정발 파일에 몰린다. 거기 **소수로 끼어든 테이블**이 사본 오선택 후보다. 그 블록이 물고 있는
정발 엔트리와 **거의 같은 문장**을 주류 테이블에서 찾아 옮긴다.

⚠⚠ **`--apply` 를 함부로 돌리지 말 것**(2026-08-11 실측). 한 맵에 **시점이 둘 이상**이면
구간 다수결이 그 둘을 한 덩어리로 뭉갠다 — 네리아 항구는 밀매상 **체포 전/후**로 시점이
갈리는데(정발 `T_043` ↔ `T_044`) 주류를 하나로 잡아 `jp1042` 를 **체포 문안에서 훈방
문안으로** 바꿔 놓았다. 이벤트 단계가 뒤바뀌는 오배정이다. 되돌렸다.
⇒ **`--apply` 는 시점이 하나뿐인 구간에서만** 쓰고, 돌린 뒤에는 반드시 재조립 결과를
전후 대조한다. 후보 목록(`--apply` 없이)은 볼 값어치가 있다.

⚠ 실패해도 피해가 작다 — 두 사본은 같은 말을 어투만 달리한 것이라, 틀려도 **다른 시점의 정발
문안**이 나온다(지어낸 한국어가 아니다). 그래서 자동 적용을 허용한다.
⚠ 그래도 **주류 테이블에 짝이 없으면 손대지 않는다.** 시점마다 대사가 실제로 추가·삭제된다.

  python3 tools/retarget_copy.py ED1SCN1            # 후보 보기
  python3 tools/retarget_copy.py ED1SCN1 --apply    # 반영
"""

import difflib
import json
import os
import re
import sys
from collections import Counter

os.environ.setdefault("LOCK_BYPASS", "1")

from align_map import scene_map
from common import OUT_DIR, ROOT
from scn_maps import block_maps

SIM = 0.72  # 사본 간 문장 유사도 문턱 — 사본끼리는 어투만 달라 매우 높게 나온다
# ⚠ 전체 유사도만으로는 놓친다 — 사본은 **앞부분이 같고 어미만 다른** 경우가 많아서다
# (`왕자님 반드시 아크담 녀석을 |박살내 주십시요` ↔ `…|한시바삐 물리쳐 주시옵소서` = 0.68).
# 그래서 **공통 접두**를 두 번째 신호로 쓴다.
PREFIX_MIN = 10  # 공통 접두 최소 글자
PREFIX_FRAC = 0.5  # 짧은 쪽 대비 접두 비율
SIM_FLOOR = 0.5  # 접두로 붙일 때의 전체 유사도 하한
GAP = 6  # eid 가 이만큼 벌어지면 다른 인스턴스 구간으로 본다
_STRIP = re.compile(r"\{[^}]*\}|\\x[0-9A-Fa-f]{2}")
_NORM = re.compile(r"[\s.,!?~…·\-'\"]+")


def norm(s):
    return _NORM.sub("", _STRIP.sub("", s))


def table_entries(table):
    """{entry_id: 정규화 본문} — 사본 대조용."""
    game, name = table.split("/")
    p = os.path.join(OUT_DIR, "dos_kr", game, f"{name}.json")
    if not os.path.exists(p):
        return {}
    doc = json.load(open(p, encoding="utf-8"))
    return {e["entry_id"]: norm(e.get("text") or "") for e in doc["entries"] if isinstance(e, dict)}


def main():
    scn_name = next((a for a in sys.argv[1:] if a.startswith("ED")), "ED1SCN1")
    game, scn = scn_name[:3], int(scn_name.split("SCN")[1])
    ov_path = os.path.join(ROOT, "align_overrides.json")
    ov = json.load(open(ov_path, encoding="utf-8"))
    bm = block_maps(game, scn)

    asg = {e: dict(v) for e, v in scene_map(scn_name).items()}
    for k, v in ov.get(scn_name, {}).items():
        if not (k.isdigit() and isinstance(v, dict)):
            continue
        # ⚠ `ours`(우리 문안)는 정본 좌표가 있어도 **그 좌표를 안 쓴다** — 사본 교정 대상이 아니다.
        # 오버라이드에 `ours` 만 있고 table 이 없으면 정본 좌표가 남아 오탐이 된다(jp151 실측).
        # ⚠ 그렇다고 목록에서 빼면 **구간 자르기가 뭉개진다** — 빠진 자리가 메워져 서로 다른
        # 인스턴스가 한 구간이 된다(실측: 마을 4인스턴스가 한 덩어리로 붙어 후보 0건).
        if "ours" in v:
            asg[int(k)] = {"_ours": True}
        elif "table" in v:
            asg[int(k)] = dict(v)

    # 맵 + eid 연속성으로 인스턴스 구간 자르기
    runs, cur = [], []
    for e in sorted(asg):
        if cur and (e - cur[-1] > GAP or bm.get(e) != bm.get(cur[-1])):
            runs.append(cur)
            cur = []
        cur.append(e)
    if cur:
        runs.append(cur)

    cache, moves = {}, []
    for run in runs:
        if len(run) < 8:
            continue
        cnt = Counter(asg[e]["table"] for e in run if "table" in asg[e])
        major = {t for t, n in cnt.items() if n >= max(5, 0.15 * len(run))}
        if not major:
            continue
        # ⚠ **이미 쓰인 엔트리도 후보다.** 정발 사본 수가 PS1 인스턴스 수보다 적은 자리가 실재해
        # (루디아 마을: 정발 사본 4 · PS1 인스턴스 4인데 대사별로는 사본이 둘뿐), 한 사본을 둘이
        # 나눠 쓰는 게 정상이다. 처음엔 '남이 쓰는 건 건드리지 않는다'로 막았다가 유저가 지적한
        # 자리를 그대로 놓쳤다(jp146 실측 2026-08-04).
        used = set()
        for e in run:
            if "table" not in asg[e]:  # `ours` — 구간 자르기에만 쓰고 교정 대상은 아니다
                continue
            tbl, ent = asg[e]["table"], asg[e]["entry_id"]
            if tbl in major:
                continue
            src = cache.setdefault(tbl, table_entries(tbl)).get(ent, "")
            if len(src) < 8:
                continue
            best = (0, None, None)
            for mt in sorted(major):
                for me, txt in cache.setdefault(mt, table_entries(mt)).items():
                    if (mt, me) in used or len(txt) < 8:
                        continue
                    r = difflib.SequenceMatcher(None, src, txt).ratio()
                    if r > best[0]:
                        best = (r, mt, me)
            if best[1] and best[0] < SIM:  # 접두 신호로 한 번 더 본다
                txt = cache[best[1]][best[2]]
                plen = len(os.path.commonprefix([src, txt]))
                if (
                    plen >= PREFIX_MIN
                    and plen / min(len(src), len(txt)) >= PREFIX_FRAC
                    and best[0] >= SIM_FLOOR
                ):
                    best = (SIM, best[1], best[2])
            if best[0] >= SIM:
                moves.append((e, tbl, ent, best[1], best[2], best[0], bm.get(e)))
                used.add((best[1], best[2]))

    print(f"{scn_name}: 사본 오선택 후보 {len(moves)}건")
    for e, t0, n0, t1, n1, r, mp in moves:
        print(f"  jp{e} [{mp}] {t0}#{n0} → {t1}#{n1}  (유사도 {r:.2f})")

    if "--apply" in sys.argv and moves:
        sc = ov.setdefault(scn_name, {})
        skipped = []
        for e, t0, n0, t1, n1, r, _mp in moves:
            cur = dict(sc.get(str(e)) or asg[e])
            # ⚠ **`chain` 이 있으면 건드리지 않는다.** 사람이 페이지·문장 단위로 맞춰 둔
            # 자리이고, 엔트리를 갈면 그 슬라이스가 통째로 무효가 된다 — 실제로 하루치
            # 배정 교정을 되돌릴 뻔했다(2026-08-11). 옮기려면 손으로 chain 을 다시 짠다.
            if "chain" in cur:
                skipped.append(e)
                continue
            cur.update(table=t1, entry_id=n1)
            cur["note"] = (
                f"정발 사본 교정(retarget_copy 2026-08-04) — {t0}#{n0} → {t1}#{n1} "
                f"(구간 주류 테이블, 유사도 {r:.2f})"
            )
            sc[str(e)] = cur
        json.dump(ov, open(ov_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  → align_overrides.json 반영 {len(moves) - len(skipped)}건")
        if skipped:
            print(
                f"  ⚠ `chain` 이 걸린 {len(skipped)}건은 건너뛴다(사람이 맞춘 슬라이스) — "
                + " ".join(f"jp{x}" for x in skipped[:12])
            )


if __name__ == "__main__":
    main()
