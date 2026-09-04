#!/usr/bin/env python3
"""배정 정본 — JP 블록이 정발 어느 엔트리를 쓰는지를 **커밋되는 파일**로 못 박는다.

**왜 필요한가(2026-08-03(3) 실측).** 배정은 `past_align_semantic`(LaBSE 임베딩 + 헝가리안)이
매번 다시 푼다. 그런데 원작에는 **글자까지 똑같은 JP 블록**이 있고(같은 대사를 하는 병사
여럿) 정발도 같은 대사를 여러 번 조금씩 다르게 옮겨놨다. 동일 텍스트 → 동일 임베딩 →
**정확한 동점**이고, 승자는 부동소수 잡음이 정한다. 그래서 **회사에서 빌드한 것과 집에서
빌드한 것이 달랐다**(좌표 차이 117건 · 문안까지 달라진 것 24건).

**해법은 배정을 파생물에서 소스로 올리는 것.** 좌표(`table`/`entry_id`)는 정발 파일 안의
포인터고 `speaker` 는 단어 수준 라벨이라 **둘 다 커밋해도 저작권 문제가 없다** —
`textmap` 이 "정발 포인터 + sha"만 담는 것과 같은 관용이다. **문장은 한 글자도 안 담는다.**

이 파일이 있으면 빌드는 `work/derived/align` 을 **안 읽는다.** 새 머신에 LaBSE·torch 가
없어도 빌드가 돌고, 어디서 돌리든 같은 결과가 나온다.

  python3 tools/align_map.py --status              # 현황
  python3 tools/align_map.py --update              # 현재 정렬 결과를 정본으로 (전 씬)
  python3 tools/align_map.py --update ED1SCN2      # 그 씬만
  python3 tools/align_map.py --diff ED1SCN1        # 정본 vs 지금 정렬 (제안 검토용)

**언제 --update 하나** — `past_align_semantic` 을 의도적으로 다시 돌려 제안을 받아들일 때만.
⚠ 머신을 옮긴 직후엔 돌리지 말 것. 그 머신의 동점 결과를 정본으로 승격시켜 버린다
(`lock_lines.py --freeze` 와 같은 함정 — 검증기를 갱신기로 쓰는 셈이다).
"""

import json
import os
import sys

from common import OUT_DIR, ROOT

MAP_PATH = os.path.join(ROOT, "align_map.json")

_DOC = (
    "배정 정본 — JP entry_id → 정발 좌표(table/entry_id/speaker). "
    "문안은 담지 않는다(저작권): 좌표는 포인터, speaker는 단어 라벨이라 커밋 가능. "
    "빌드는 이 파일이 있으면 work/derived/align 을 읽지 않는다 — 그래서 머신이 달라도 "
    "같은 결과가 나온다. 갱신은 tools/align_map.py."
)


def load_map():
    try:
        return json.load(open(MAP_PATH, encoding="utf-8"))
    except FileNotFoundError:
        return {}


def scene_map(scn_name):
    """{jp_entry_id: {table, entry_id, speaker}} — 없으면 빈 dict(=정렬 파일 사용)."""
    return {int(k): v for k, v in load_map().get(scn_name, {}).items()}


def _current(scn_name):
    """지금 정렬 결과로 빌드가 실제로 쓰게 될 배정. reinsert 와 같은 경로를 탄다."""
    import reinsert_kr_pilot as R

    align_name = scn_name.replace("SCN", "_SCN")
    p = os.path.join(OUT_DIR, "align", f"{align_name}.json")
    if not os.path.exists(p):
        return None
    pairs = json.load(open(p, encoding="utf-8"))["pairs"]
    pairs, _ = R.apply_lock_src(pairs, scn_name)  # 확정 락이 이긴다
    table_blocks = R.table_block_eids(scn_name)  # 포인터 테이블에는 배정하지 않는다
    out = {}
    for pr in pairs:
        if not pr.get("jp") or not pr.get("kr"):
            continue
        if pr["jp"]["entry_id"] in table_blocks:
            continue
        if not (pr.get("_locked") or R.accept_pair(pr)):
            continue
        out[pr["jp"]["entry_id"]] = {
            "table": pr["kr"]["table"],
            "entry_id": pr["kr"]["entry_id"],
            "speaker": pr["kr"].get("speaker"),
        }
    return out


def scenes():
    import glob

    out = []
    for p in sorted(glob.glob(os.path.join(OUT_DIR, "align", "ED*_SCN*.json"))):
        out.append(os.path.basename(p)[:-5].replace("_SCN", "SCN"))
    return out


def update(names):
    doc = load_map()
    doc.setdefault("_doc", _DOC)
    for scn in names:
        cur = _current(scn)
        if cur is None:
            print(f"  {scn}: 정렬 파일 없음 — 건너뜀")
            continue
        old = doc.get(scn, {})
        added = sum(1 for k in cur if str(k) not in old)
        moved = sum(
            1
            for k, v in cur.items()
            if str(k) in old
            and (old[str(k)]["table"], old[str(k)]["entry_id"]) != (v["table"], v["entry_id"])
        )
        doc[scn] = {str(k): cur[k] for k in sorted(cur)}
        print(f"  {scn}: 배정 {len(cur)}건 (신규 {added} · 이동 {moved})")
    json.dump(doc, open(MAP_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"→ {MAP_PATH}")


def diff(scn):
    old, cur = scene_map(scn), _current(scn)
    if cur is None:
        print(f"{scn}: 정렬 파일 없음")
        return
    n = 0
    for e in sorted(set(old) | set(cur)):
        a, b = old.get(e), cur.get(e)
        ka = f"{a['table']}#{a['entry_id']}" if a else "-"
        kb = f"{b['table']}#{b['entry_id']}" if b else "-"
        if ka != kb:
            print(f"  jp{e:<5} 정본 {ka:<18} → 지금 {kb}")
            n += 1
    print(f"{scn}: 차이 {n}건 / 정본 {len(old)}건")


def main():
    # ⚠ 이 우회는 **스크립트로 직접 돌 때만** 건다. 모듈 최상단에 두면 `reinsert_kr_pilot` 이
    # 이 모듈을 import 하는 것만으로 **빌드 전체의 락 검증이 꺼진다**(2026-08-03(3) 실측 —
    # 빌드가 "통과"했는데 실은 검증을 안 하고 있었다). 모듈 최상단 env 변경은 이래서 위험하다.
    os.environ.setdefault("LOCK_BYPASS", "1")
    if "--update" in sys.argv:
        names = [a for a in sys.argv[sys.argv.index("--update") + 1 :] if not a.startswith("-")]
        update(names or scenes())
        return
    if "--diff" in sys.argv:
        for scn in sys.argv[sys.argv.index("--diff") + 1 :]:
            if scn.startswith("-"):
                break
            diff(scn)
        return
    doc = load_map()
    for scn, v in doc.items():
        if scn.startswith("_"):
            continue
        print(f"  {scn:10} 배정 {len(v)}건")
    if len(doc) <= 1:
        print("  (아직 없음 — `--update` 로 현재 정렬을 정본으로)")


if __name__ == "__main__":
    main()
