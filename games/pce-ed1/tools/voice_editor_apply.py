#!/usr/bin/env python3
"""편집기에서 마스터가 고친 값을 정본에 반영한다 — 자막 문안(`kr`)과 나눔(쪽)·시각(`t_start`/`t_end`).

  python3 tools/voice_editor_apply.py <편집된 data.json> [--dry]
입력은 `voice_editor_data.py` 가 낸 data.json 과 같은 꼴(행마다 `scene` · `key` · `page` · `kr` …). 같은 씬·같은 메시지(`key`)의 행들을 `page` 순으로 모아
쪽 사이를 `\\f` 로 이어 `script/scnNNN.json` 에 쓴다(`scene_apply.validate` 검증 통과가 조건 — 일본어 잔존·글리프·조판).
- 줄바꿈은 쓰지 않는다(조판기가 정한다) — 행 안의 `\\n` 은 공백으로 접는다. 행을 지우면 그 쪽이 사라지고, 같은 `page` 를 둘로 가르면 쪽이 늘어난다.
- 시각(`t_start`/`t_end`)은 쪽마다 **(열림, 닫힘)** 으로 `script/voice_timing.json` 에 쓴다(10-18 — `narration_gates.plan_segments`). 열림이 앞 쪽 닫힘과 `GAP_TOL` 이내면 한 창 안 자동 넘김,
  넘으면 창을 닫았다 다시 연다. 첫 쪽의 열림은 게이트 도달(오하요·설교는 음성 시작) 뒤 그 초. 씬 98 시각표(연출이 열림을 쥐고 닫힘만 쓴다)·카드 화면·gwin 의 바뀐 시각은 못 쓰므로 `work/review/voice_timing_edits.json` 에 모아 알린다.
- 입력은 행 전체(`voice_editor_data.py` 꼴)이거나 편집기 db `edits` 문서 덤프(`{clip, idx, ts, te, kr, spk}` 목록 — 기본 자료에 얹어 합친다).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import narration_gates as G
import scene_apply as A
import voice_editor_data as D


def merge_docs(edited: list[dict], base: dict) -> list[dict]:
    """db `edits` 문서(`ts`·`te`·`kr`·`spk`)를 기본 행에 얹어 편집된 행 목록으로. 이미 행 꼴(`scene` 있음)이면 그대로."""
    if edited and "scene" in edited[0]:
        return edited
    docs = {(d["clip"], d["idx"]): d for d in edited if d.get("clip") is not None}
    rows = []
    for k, b in base.items():
        r = dict(b)
        d = docs.get(k, {})
        if d.get("ts") is not None:
            r["t_start"] = float(d["ts"])
        if d.get("te") is not None:
            r["t_end"] = float(d["te"])
        if d.get("kr") not in (None, ""):
            r["kr"] = d["kr"]
        if d.get("spk") not in (None, ""):
            r["speaker_name"] = d["spk"]
        rows.append(r)
    return rows


def timing_items(rows: list[dict], base: dict) -> dict[str, list]:
    """바뀐 (열림, 닫힘)이 있는 `voice_timing` 키마다 쪽 목록 — 원소 = 닫힘 초 또는 [열림|None, 닫힘]. 시각은 게이트 기준(`tbase`) 상대 초."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("tkey"):
            groups.setdefault(r["tkey"], []).append(r)
    out: dict[str, list] = {}
    for tkey, rs in sorted(groups.items()):
        rs.sort(key=lambda r: r["tpage"])
        if not any(
            (b := base.get((r["clip"], r["idx"])))
            and (r["t_start"] != b["t_start"] or r["t_end"] != b["t_end"])
            for r in rs
        ):
            continue
        items: list = []
        prev_close = 0.0
        paired = False
        for r in rs:
            tb = float(r.get("tbase", 0.0))
            o_rel, c_rel = float(r["t_start"]) - tb, float(r["t_end"]) - tb
            first = r["tpage"] == 0
            if (first and o_rel > 0.1) or (not first and o_rel - prev_close > G.GAP_TOL):
                items.append([round(o_rel, 2), round(c_rel, 2)])
                paired = True
            else:
                items.append(round(c_rel, 2))
            prev_close = c_rel
        out[tkey] = [x if isinstance(x, list) else [None, x] for x in items] if paired else items
    return out


def main() -> int:
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    dry = "--dry" in sys.argv
    base = {(r["clip"], r["idx"]): r for r in D.build()[0]}
    edited = merge_docs(json.loads(Path(a[0]).read_text("utf-8")), base)
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
    new_t = timing_items(edited, base)
    for k, v in new_t.items():
        print(f"시각 {k}: {json.dumps(v)}")
    if new_t and not dry:
        cur = json.loads(G.TIMING_FILE.read_text("utf-8")) if G.TIMING_FILE.exists() else {}
        cur.update(new_t)
        G.TIMING_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"→ {G.TIMING_FILE} ({len(new_t)}키)")
    timing = [
        t
        for t in timing
        if not next((r for r in edited if r["clip"] == t["clip"] and r["idx"] == t["idx"]), {}).get(
            "tkey"
        )
    ]
    if timing:
        out = common.REVIEW_DIR / "voice_timing_edits.json"
        if not dry:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(timing, ensure_ascii=False, indent=1), "utf-8")
        print(f"시각 수정 {len(timing)}쪽 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
