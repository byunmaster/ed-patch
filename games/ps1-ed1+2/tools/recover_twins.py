#!/usr/bin/env python3
"""쌍둥이 회수 — **JP 원문이 바이트까지 같은** 블록에 이미 붙은 배정을 그대로 복제한다.

**왜 이게 안전한가.** 유사도 배정(`assign_pages`)은 홀드아웃 검증에서 정밀도 79% 였고
구간을 갈라도 안전한 문턱이 없었다(0.85~0.90 구간이 66.7% 로 오히려 최악 — 2026-08-04 실측).
**틀린 한국어는 일본어보다 나쁘다** — 일본어는 스스로 티가 나는데 그럴듯한 오역은 QA 를
통과한다. 반면 여기 쓰는 신호는 추정이 아니라 **동일성**이다: 원문 바이트가 같으면 같은
번역이 맞고, 구조(`%c`·`%s`·`%d`)까지 같으니 창 수 계약도 자동으로 지켜진다.

1장이 93% 까지 간 것도 유사도 문턱을 낮춰서가 아니었다 — 오버라이드 813건이 전부
"상점 공통 프롬프트 캐노니컬"·"인스턴스 단위 회수" 같은 **구조적 회수**였다. 이 도구는 그중
가장 기계적인 갈래를 자동화한다.

⚠ 배정 좌표(table/entry_id/chain)만 복제한다 — 문안은 담지 않는다(저작권).
⚠ 이름·지명 플레이트와 포인터 테이블 블록은 건너뛴다. 오버라이드는 정렬 단계의 그 필터들을
   지나쳐 적용되므로, 여기서 안 걸러내면 `patch_sys_ui` 관할을 침범한다.

  python3 tools/recover_twins.py            # 현황만(기본, 파일 안 건드림)
  python3 tools/recover_twins.py --apply    # align_overrides.json 에 반영
  python3 tools/recover_twins.py --scn ED1SCN2 --apply   # 특정 씬만
"""

import json
import os
import sys

os.environ.setdefault("LOCK_BYPASS", "1")  # 관리 도구 — 락 검증 우회(교착 방지)

from align_map import scene_map
from common import OUT_DIR, ROOT

OV_PATH = os.path.join(ROOT, "align_overrides.json")
NOTE = "쌍둥이 회수 — JP 원문 바이트 동일 블록의 배정 복제"
COPY_KEYS = ("table", "entry_id", "chain", "subs", "speaker", "ours")


def _blocks(R, name):
    """{eid: raw_hex} — `%c` 를 가진 대사 블록만."""
    doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{name}.json"), encoding="utf-8"))
    return {
        e["entry_id"]: e["raw_hex"]
        for e in doc["entries"]
        if e.get("raw_hex") and R.MC in bytes.fromhex(e["raw_hex"])
    }


def _skip_eids(R, name):
    """오버라이드를 걸면 안 되는 블록 — 이름·지명 플레이트 + 포인터 테이블."""
    from align_jp_kr import load_jp_scene
    from patch_sys_ui import is_name_plate

    g, _, sn = name.replace("SCN", "_SCN").partition("_SCN")
    plate = {b["id"] for b in load_jp_scene(g, int(sn)) if is_name_plate(b["body"])}
    return plate | set(R.table_block_eids(name))


def collect(R, ov):
    """(회수 제안, 씬별 통계) — raw_hex 가 같은 번역된 블록의 배정을 미번역 블록에 복제."""
    src_by_raw, state = {}, {}
    for name, _lba, _size in R.SCN_FILES:
        raws = _blocks(R, name)
        tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
        excl_p = os.path.join(OUT_DIR, f"excluded_{name}.json")
        excl = json.load(open(excl_p, encoding="utf-8")) if os.path.exists(excl_p) else {}
        done = {e for e in tr if str(e) not in excl}
        state[name] = (raws, done, _skip_eids(R, name))
        # 배정 좌표의 출처: 오버라이드가 정본보다 우선(reinsert 와 같은 순서)
        canon = scene_map(name)
        # 🔴 **집합을 그냥 돌면 안 된다**(레포 제1원칙). 바로 아래 `raw in src_by_raw` 는
        #    **먼저 만난 쪽이 이기는** 구조라, 같은 원문 바이트에 좌표가 갈리는 자리에서
        #    **어느 쌍둥이의 배정을 복제할지가 순회 순서로 정해진다.** 그 좌표는 `--apply`
        #    로 `align_overrides.json`(커밋되는 빌드 입력)에 박히므로 이미지까지 간다.
        #    실측 2026-08-27: 좌표가 갈리는 원문이 **388개**다.
        #    ⚠ `done` 이 정수 집합이라 같은 내용이면 순서가 안 흔들려 눈에 안 띄었는데,
        #    집합 크기가 바뀌면 해시 배치가 재배열돼 무관한 자리까지 승자가 바뀐다.
        #    `sorted` 로 **가장 작은 eid 가 이긴다**를 못 박는다.
        for eid in sorted(done):
            raw = raws.get(eid)
            if raw is None or raw in src_by_raw:
                continue
            e = ov.get(name, {}).get(str(eid))
            if isinstance(e, dict) and "table" in e:
                src_by_raw[raw] = ({k: e[k] for k in COPY_KEYS if k in e}, name, eid)
            elif eid in canon:
                v = canon[eid]
                src_by_raw[raw] = ({k: v[k] for k in ("table", "entry_id") if k in v}, name, eid)

    out = {}
    for name, (raws, done, skip) in state.items():
        cur = ov.get(name, {})
        for eid, raw in raws.items():
            if eid in done or eid in skip or str(eid) in cur:
                continue
            hit = src_by_raw.get(raw)
            if hit is None:
                continue
            src, from_scn, from_eid = hit
            out.setdefault(name, {})[str(eid)] = dict(
                src, note=f"{NOTE} (← {from_scn} jp{from_eid})"
            )
    return out


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import reinsert_kr_pilot as R

    only = sys.argv[sys.argv.index("--scn") + 1] if "--scn" in sys.argv else None
    ov = json.load(open(OV_PATH, encoding="utf-8"))
    prop = collect(R, ov)
    if only:
        prop = {k: v for k, v in prop.items() if k == only}

    print(f"\n{'씬':10} {'회수':>5}  출처 분포")
    total = 0
    for name, _lba, _size in R.SCN_FILES:
        v = prop.get(name, {})
        if not v:
            continue
        total += len(v)
        same = sum(1 for e in v.values() if f"← {name} " in e["note"])
        print(f"{name:10} {len(v):5}  씬 내 {same} · 씬 간 {len(v) - same}")
    print(f"{'합계':10} {total:5}")
    if not total:
        return
    if "--apply" not in sys.argv:
        print("\n(현황만 — 반영하려면 --apply)")
        return
    for name, v in prop.items():
        ov.setdefault(name, {}).update(v)
    json.dump(ov, open(OV_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n→ {OV_PATH} 에 {total}건 추가. 재빌드해 게이트 통과분을 확인할 것.")


if __name__ == "__main__":
    main()
