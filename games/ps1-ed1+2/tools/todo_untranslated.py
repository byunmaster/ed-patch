#!/usr/bin/env python3
"""아직 손이 필요한 대사 블록만 남긴다 — 씬을 닫을 때 보는 목록.

**빼는 것 넷.** 그냥 "번역 안 된 블록"을 세면 매번 같은 것이 다시 올라와 목록을 못 믿게 된다
(유저 지적 2026-08-04 — 곶의 동굴 보물상자·네리아 현자가 라운드마다 다시 떴다).
  ① 포인터 테이블(`table_block_eids`) · ② 이름·지명 플레이트(`patch_sys_ui` 관할)
  ③ 원문이 빈 블록(`%c` 만 있는 자리) · ④ **판정이 끝난 블록**(`lock_lines --settled`)

⚠ `--settled --later`(`_pending`)로 넣은 「나중에 채움」은 **안 뺀다** — ⏳ 로 계속 보고한다.
조용히 빠지면 잊힌다(SCN1 여섯이 그렇게 일본어로 남아 있었다, 2026-08-10).
⚠ **`%c` 없는 블록은 빼지 않는다**(2026-08-10 수정) — 창 종단이 없을 뿐 다음 블록과 한 창에
그려지는 **대사 앞 조각**이 거기 섞여 있다. 예전 필터가 그걸 통째로 숨겨 SCN4 에서만
13블록이 일본어로 나가고 있었다(포인터 참조로 화면 출력 확인).
④가 핵심이다 — 확정 락은 *번역된* 문안만 지키므로 "미번역이지만 확인 결과 문제없다"나
"이 장에서는 도달하지 않는다"는 판정은 락으로 남길 수 없다.

  python3 tools/todo_untranslated.py            # 전 씬 요약
  python3 tools/todo_untranslated.py ED1SCN2    # 그 씬 상세(맵·화자·원문)
"""

import json
import os
import re
import sys

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from align_jp_kr import load_jp_scene
from common import OUT_DIR
from lock_lines import pending as pending_marks
from lock_lines import settled
from patch_sys_ui import is_name_plate
from scn_maps import block_maps

# 가나 — "이 블록이 진짜 일본어 대사인가"의 판정자. 지명 플레이트 잔재·그래픽 쓰레기
# (`怦怦怦…`)에는 가나가 없다.
KANA = re.compile(r"[\u3041-\u309f\u30a1-\u30fa]")


def pending(game, scn):
    """[(eid, 맵, 화자, 원문)] — 손이 필요한 블록만."""
    name = f"{game}SCN{scn}"
    doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{name}.json"), encoding="utf-8"))
    raws = {e["entry_id"]: bytes.fromhex(e["raw_hex"]) for e in doc["entries"] if e.get("raw_hex")}
    tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
    p = os.path.join(OUT_DIR, f"excluded_{name}.json")
    excl = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    tbl, done = R.table_block_eids(name), settled(name)
    jp = {b["id"]: b for b in load_jp_scene(game, scn)}
    plate = {i for i, b in jp.items() if is_name_plate(b["body"])}
    bm = block_maps(game, scn)
    out = []
    for i in sorted(jp):
        if i not in raws:
            continue
        # ⚠ **`%c`(창 종단)가 없어도 대사일 수 있다.** 정발 한 문장을 PS1 이 두 블록으로
        # 끊어 둔 자리가 그렇다 — 앞 조각은 종단 없이 다음 블록과 **한 창**에 이어 그려진다
        # (`うちの亭主は…けどさあ、` → 다음 블록). 예전엔 `%c` 없는 블록을 통째로 건너뛰어
        # **목록에 안 뜬 채 일본어로 나가고 있었다**(2026-08-10 발견 — 포인터 참조가 살아
        # 있어 화면에 실제로 나온다). 가나가 있는 것만 남긴다.
        if R.MC not in raws[i] and not KANA.search(jp[i]["body"] or ""):
            continue
        if i in tbl or i in plate or str(i) in done:
            continue
        if i in tr and str(i) not in excl:
            continue
        if not (jp[i]["body"] or "").strip():  # `%c` 뿐인 빈 블록
            continue
        out.append((i, bm.get(i) or "?", jp[i].get("speaker") or "-", jp[i]["body"]))
    return out


def main():
    game = "ED1"
    only = next((a for a in sys.argv[1:] if a.startswith(game)), None)
    total = 0
    for scn in range(1, 7):
        name = f"{game}SCN{scn}"
        if only and name != only:
            continue
        rows = pending(game, scn)
        total += len(rows)
        n_settled = len(settled(name))
        # ⚠ `_pending`(나중에 채움)은 **빼지 않는다** — 조용히 사라지면 잊힌다(2026-08-10).
        later = pending_marks(name)
        print(
            f"\n{name}: 손이 필요한 블록 **{len(rows)}건**"
            + (f" (판정완료 {n_settled}건 제외)" if n_settled else "")
            + (f" · ⏳ 나중에 채움 {len(later)}건" if later else "")
        )
        for k, why in sorted(later.items(), key=lambda x: int(x[0])):
            print(f"  ⏳ jp{k:<5} {why[:70]}")
        if only:
            for i, mp, spk, body in rows:
                print(f"  jp{i:<5} [{mp}] {spk:10} {body[:52]}")
    print(f"\n합계 {total}건")


if __name__ == "__main__":
    main()
