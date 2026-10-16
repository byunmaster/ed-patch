#!/usr/bin/env python3
"""편집기에서 마스터가 고친 값을 정본에 반영한다 — 자막 문안(`kr`)과 나눔(쪽)·시각(`t_start`/`t_end`).

  python3 tools/voice_editor_apply.py <편집된 data.json> [--dry]
입력은 `voice_editor_data.py` 가 낸 data.json 과 같은 꼴(행마다 `scene` · `key` · `page` · `kr` …). 같은 씬·같은 메시지(`key`)의 행들을 `page` 순으로 모아
쪽 사이를 `\\f` 로 이어 `script/scnNNN.json` 에 쓴다(`scene_apply.validate` 검증 통과가 조건 — 일본어 잔존·글리프·조판).
- 줄바꿈은 쓰지 않는다(조판기가 정한다) — 행 안의 `\\n` 은 공백으로 접는다. 행을 지우면 그 쪽이 사라지고, 같은 `page` 를 둘로 가르면 쪽이 늘어난다.
- 시각(`t_start`/`t_end`)은 아직 엔진이 읽는 자리가 없다 — **반영하지 않고** `work/review/voice_timing_edits.json` 에 바뀐 것만 모아 둔다(쪽 마감 표 설계 뒤에 쓴다).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import scene_apply as A
import voice_editor_data as D


def main() -> int:
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    dry = "--dry" in sys.argv
    edited = json.loads(Path(a[0]).read_text("utf-8"))
    base = {(r["clip"], r["idx"]): r for r in D.build()[0]}
    by_msg: dict[tuple[int, str], list[dict]] = {}
    timing = []
    for r in edited:
        by_msg.setdefault((r["scene"], r["key"], r["clip"]), []).append(r)
        b = base.get((r["clip"], r["idx"]))
        if b and (r.get("t_start") != b["t_start"] or r.get("t_end") != b["t_end"]):
            timing.append({"clip": r["clip"], "idx": r["idx"], "key": r["key"], "t_start": [b["t_start"], r.get("t_start")], "t_end": [b["t_end"], r.get("t_end")]})
    bad = 0
    by_scene: dict[int, dict[str, str]] = {}
    seen: set[tuple[int, str]] = set()
    for (sid, key, clip), rs in sorted(by_msg.items()):
        rs.sort(key=lambda x: (x.get("page", 0), x.get("idx", 0)))
        orig = [b["kr"] for (c, i), b in sorted(base.items()) if b["key"] == key and b["scene"] == sid and c == clip]
        if (sid, key) in seen:  # 같은 메시지가 여러 토막에 걸리면 첫 토막 값만 쓴다 — 다른 토막이 다르게 고쳐졌으면 알린다
            if [x["kr"] for x in rs] != orig:
                print(f"  ⚠ scn{sid:03d} {key}: 토막 {clip} 에서도 고쳐졌다 — 첫 토막 값을 쓴다")
            continue
        seen.add((sid, key))
        if [x["kr"] for x in rs] == orig:  # 안 고친 메시지는 건드리지 않는다(조판기가 나눈 창을 `\\f` 로 굳히지 않으려고)
            continue
        pages = [" ".join(x["kr"].split()) for x in rs if x["kr"].strip()]
        if not pages:
            continue
        by_scene.setdefault(sid, {})[key] = "\f".join(pages)
    for sid, new in sorted(by_scene.items()):
        errs = A.validate(sid, new)
        if errs:
            bad += len(errs)
            print("\n".join(f"  ✗ scn{sid:03d} {e}" for e in errs))
    if bad:
        print(f"반영 안 함 — 위반 {bad}")
        return 1
    for sid, new in sorted(by_scene.items()):
        p = A.SCRIPT / f"scn{sid:03d}.json"
        doc = json.loads(p.read_text("utf-8"))
        ch = 0
        for k, t in new.items():
            if doc["messages"].get(k, {}).get("t") != t:
                doc["messages"][k] = {"t": t}
                ch += 1
        print(f"scn{sid:03d}: 문안 {ch}건 바뀜")
        if ch and not dry:
            p.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    if timing:
        out = common.REVIEW_DIR / "voice_timing_edits.json"
        if not dry:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(timing, ensure_ascii=False, indent=1), "utf-8")
        print(f"시각 수정 {len(timing)}쪽 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
