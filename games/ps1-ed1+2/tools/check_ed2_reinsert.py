#!/usr/bin/env python3
"""ED2 문안이 **재삽입을 통과하는지** 체인에 올리기 전에 미리 잰다.

ED2 씬은 `patch_sys_ui.SCN_FILES` 에 아직 없다(등록하면 ED1 씬 LBA 가 밀려서, ED1 인게임
QA 가 끝나야 올린다 — `docs/ed2-notes.md`). 그래서 **빌드가 ED2 문안을 한 번도 안 본다** —
구조 계약 위반이 있어도 조용하고, 등록하는 날 한꺼번에 터진다.

이 도구는 `_scn_layout()` 을 안 거치고 `scn_jp/*.json` 에서 곧장 블록을 읽어
`build_candidate` 를 돌린다. **이미지는 건드리지 않는다** — 통과/탈락만 센다.

⚠ **탈락은 조용한 사고다.** 블록이 탈락하면 원문이 그대로 남아 화면에 일본어가 뜨는데,
빌드는 성공하고 단위 테스트도 통과한다(루트 `CLAUDE.md` 「화면에 나가는 바이트를 게이트로
본다」). 실제로 이 검사를 처음 돌렸을 때 **171건**이 탈락 예약 상태였다(2026-08-15):

| 사유         |  건수 | 원인                                                             |
| ------------ | ----: | ---------------------------------------------------------------- |
| `encode`     |    75 | `ㅡ`(장음)·`·`(가운뎃점) — 글리프가 없다. 정발은 `~`·`...` 를 쓴다 |
| `fmt_excess` |    66 | 선두 `%c%s%c` 를 본문에도 넣었다 — JP 는 그걸 **헤더**로 소비한다 |
| `fmt_drop`   |    27 | `%s`·`%d` 를 **글자 그대로** 썼다 — 센티널이라야 바이트로 나간다  |
| `ctrl_seq`   |     3 | 원본 제어런을 재현 못 하는 자리(오버라이드가 필요하다)           |

  python3 tools/check_ed2_reinsert.py        # 씬별 집계 + 탈락 목록
  python3 tools/check_ed2_reinsert.py -q     # 합계만
"""

import collections
import functools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from common import OUT_DIR, extract
from patch_sys_ui import SCN_FILES

SCENES = [f"ED2SCN{n}" for n in range(1, 14)]


@functools.lru_cache(maxsize=None)
def _tails(scene):
    """`{eid: 꼬리 시작}` — **빌드가 실제로 덮어쓰는 범위**다.

    🔴 **이 검사기가 거짓말을 하고 있었다**(2026-08-19). 블록을 **통째로**
    `build_candidate` 에 넣어 시뮬레이션했는데, `rebuild` 는 앵커가 접두인 블록의 **꼬리만**
    넣는다(`build_candidate(b["raw"][b["tail"]:], …)`). 그래서 화면엔 멀쩡히 한글이 나가는
    `ED2SCN1 jp534`(`[포인터 표 20B][이름창+대사]`, `anchor_tail=20`)를 「탈락 — 화면에
    일본어가 남는다」로 계속 울렸다.

    ⚠ 거짓 경보는 그냥 노이즈가 아니다. 그 한 줄을 쫓아 **파이프라인에 없어도 될 길을
    내다가**(참조 델타를 꼬리로 삼는 코드) 빌드 sha1 이 그대로인 죽은 코드를 만들었다.
    CLAUDE.md 의 「늘 빨간불이면 아무도 안 본다」가 이렇게 물린다.
    """
    src = next((x for x in SCN_FILES if x[0] == scene), None)
    if src is None:
        return {}
    _, lba, size = src
    with open(os.path.join(OUT_DIR, "scn_jp", f"{scene}.json"), encoding="utf-8") as f:
        doc = json.load(f)
    data = extract(lba, size)
    text_end = int(doc["source"]["text_end"], 16)
    with R.overlay_for(scene):
        anchors = R.compute_anchors(data, text_end)
    out = {}
    for e in doc["entries"]:
        if e["kind"] == "gap" or not e.get("raw_hex"):
            continue
        n = len(e["raw_hex"]) // 2
        k = R.anchor_tail(anchors, int(e["file_offset"], 16), n)
        if k is not None and R.MC in bytes.fromhex(e["raw_hex"])[k:]:
            out[e["entry_id"]] = k
    return out


def run(scene):
    """(집계, 탈락 목록) — 탈락은 `(사유, eid, 우리 문안)`."""
    path = os.path.join(OUT_DIR, "scn_jp", f"{scene}.json")
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    raw = {e["entry_id"]: bytes.fromhex(e["raw_hex"]) for e in doc["entries"] if e.get("raw_hex")}
    src = os.path.join(R.SCRIPT_DIR, f"{scene}.json")
    ours = {}
    if os.path.exists(src):
        with open(src, encoding="utf-8") as f:
            ours = json.load(f)

    tally, bad = collections.Counter(), []
    tails = _tails(scene)
    with R.overlay_for(scene):
        tr, _, _ = R.load_translations(scene.replace("SCN", "_SCN"), scene)
        # ⚠ **`STOCK_MID` 는 탈락이 아니다.** 선두가 포인터 표라 제자리 재작성은 못 하지만,
        # 재삽입이 **참조를 대표 사본으로 돌려** 화면엔 한글이 나간다(`compute_stock_alias`).
        # 이걸 모르고 세면 「화면에 일본어가 남는다」는 거짓 경보가 된다 — ED2 에서 3건이
        # 그렇게 잡혀 있었다(2026-08-17). 따로 세어 보고한다(조용히 빼지 않는다).
        mid = {**R.STOCK_MID, **R.MID_ALIAS}
        for eid, t in sorted(tr.items()):
            if eid in mid:
                tally["mid_alias"] += 1
                continue
            if eid not in raw:
                tally["no_raw"] += 1
                continue
            k = tails.get(eid)
            try:
                # 앵커 접두 블록은 빌드도 꼬리만 다시 쓴다 — 같은 범위로 시뮬레이션해야
                # 결과가 맞는다(`_tails` 주석). 남는 자리도 꼬리 길이로 잰다.
                cand, why = R.build_candidate(raw[eid][k:] if k else raw[eid], t, eid)
                if cand is not None and k and len(cand) > len(raw[eid]) - k:
                    cand, why = None, "anchor_tail_size"
            except Exception as e:  # noqa: BLE001 — 검사기는 빌드를 안 세운다
                tally["exc"] += 1
                bad.append(("exc:" + type(e).__name__, eid, repr(e)[:60]))
                continue
            if cand is None:
                tally[why or "none"] += 1
                bad.append((why or "none", eid, ours.get(str(eid), {}).get("t", "")))
            else:
                tally["ok"] += 1
    return tally, bad


def main():
    quiet = "-q" in sys.argv
    total, all_bad = collections.Counter(), []
    for scene in SCENES:
        tally, bad = run(scene)
        total.update(tally)
        all_bad += [(scene, *b) for b in bad]
        if not quiet:
            drop = sum(v for k, v in tally.items() if k not in ("ok", "no_raw", "mid_alias"))
            print(f"  {scene:<10} 통과 {tally['ok']:>5}   탈락 {drop:>3}")
    if not quiet and all_bad:
        print("\n  탈락 목록 — 이 블록은 **화면에 일본어가 남는다**")
        for scene, why, eid, text in all_bad:
            print(f"    [{why}] {scene} jp{eid}  {text[:56]!r}")
    drop = sum(v for k, v in total.items() if k not in ("ok", "no_raw", "mid_alias"))
    if total["mid_alias"]:
        print(f"  ℹ 대표 사본으로 참조를 돌리는 블록 {total['mid_alias']}건 — 탈락 아님")
    print(f"\n  ED2 재삽입 예행: 통과 {total['ok']} · 탈락 {drop} {dict(total)}")
    # ⚠ 게이트로 세우지 않는다 — ED2 는 아직 체인 밖이라 「지금 고칠 수 있는 것」이 아닌
    # 자리가 섞인다(제어런 재현 불가 블록). 수치를 보고 사람이 판단한다.
    return 0


if __name__ == "__main__":
    sys.exit(main())
