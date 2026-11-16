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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import narration_gates as G
import scene_apply as A
import voice_editor_data as D
import voice_sched as VS


ADDED_MAP_PATH = Path(__file__).resolve().parent.parent / "script" / "editor_added_map.json"
ADDED_MAP: dict[str, int] = json.loads(ADDED_MAP_PATH.read_text("utf-8")) if ADDED_MAP_PATH.exists() else {}  # {"scn046_s1-1000": 1001} — 편집기 DB 열쇠 → 제품 on_extra idx


def merge_docs(edited: list[dict], base: dict) -> list[dict]:
    """db `edits` 문서(`ts`·`te`·`kr`·`spk`)를 기본 행에 얹어 편집된 행 목록으로. 이미 행 꼴(`scene` 있음)이면 그대로."""
    if edited and "scene" in edited[0]:
        return edited
    docs = {(d["clip"], d["idx"]): d for d in edited if d.get("clip") is not None}
    rows = []
    for k, b in base.items():
        r = dict(b)
        d = docs.get(k)
        if d is None and b.get("dup_of"):  # 같은 음성을 쓰는 짝 토막의 같은 행(`dup_of` = 「기준토막-idx」) — 이쪽 편집이 따로 없으면 기준 행의 마스터 편집을 그대로(11-04 「s0 만 맞춰도 되게」)
            sc, _, si = b["dup_of"].rpartition("-")
            d = docs.get((sc, int(si)))
        d = d or {}
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


def _seg_of(sc, sid: int, clip: str) -> dict:
    """시각표 장면의 토막 — 편집기 토막 이름(`voice_editor_data.sched_rows` 와 같은 규칙: 옛 이름 표 → `scnNNN_sN`)으로 고른다."""
    if not isinstance(sc, list):
        return sc
    for si, seg in enumerate(sc):
        if D.LEGACY_CLIP.get((sid, seg.get("voice_gate")), f"scn{sid:03d}_s{si}") == clip:
            return seg
    return sc[0]


def apply_sched(docs: list[dict], dry: bool = False) -> int:
    """편집기 db 문서(`{clip, idx, ts, te, spk}`)를 **전역 시각표**(`script/voice_sched.json`) 행에 반영한다 — 씬 18·98·224 같은 시각표 장면(행 `sched`).
    · `te` → 그 쪽의 `ends` · 첫 쪽 `ts` → `on_overlay.starts[열쇠]`(비모달 자막이 그 시각에 연다 — 쪽 사이 시작은 앞 쪽 끝이라 둘째 쪽부터의 `ts` 는 따로 안 쓴다, 다르면 알린다)
    · `spk`(첫 쪽) 가 행 기본 화자와 다르면 메시지 `speaker`. `kr` 은 건드리지 않는다(문안은 자료 그대로 — 마스터 11-03).
    값이 없는(`te` 안 고친) 쪽은 시각표의 옛 끝을 둔다."""
    spec = json.loads(VS.SPEC.read_text("utf-8"))
    by = {(d["clip"], d["idx"]): d for d in docs if d.get("clip") is not None}
    n = 0
    for d in docs:  # 🔴 추가 행(idx≥1000 · `added`) — 원문 메시지에 없는 자막 쪽. 시각표 `on_extra` 에 두고 비모달 쪽 목록에만 끼운다(모달 표 `ends` 는 그대로)
        mm = re.match(r"scn(\d+)_[sg]\d+$", d.get("clip") or "")
        if not (d.get("added") and d.get("idx", 0) >= 1000 and mm):
            continue
        sc = spec["scenes"].get(str(int(mm.group(1))))
        if sc is None:
            continue
        seg = _seg_of(sc, int(mm.group(1)), d["clip"])
        pidx = ADDED_MAP.get(f"{d['clip']}-{d['idx']}", d["idx"])  # 🔴 편집기 추가 행 열쇠(`토막-idx`) ↔ 제품 추가 행 번호 — idx 로 곧장 짝지으면 같은 번호의 다른 행을 덮어쓴다(11-11 46 s1: DB 1000 「로, 로우」가 제품 x1000 「예.」를 덮음). 대응표 `script/editor_added_map.json`
        cur = next((x for x in seg.setdefault("on_extra", []) if x["idx"] == pidx), None)
        new_ex = {"idx": pidx, "id": f"x{pidx}", "text": " ".join((d.get("kr") or "").split()), "speaker": d.get("spk") or "", "start": float(d["ts"]), "end": float(d["te"])}
        if cur is None:
            seg["on_extra"].append(new_ex)
            n += 1
        elif cur != new_ex:
            cur.update(new_ex)
            n += 1
    ALL_ROWS = D.build()[0]
    rows = [r for r in ALL_ROWS if r.get("sched") and r["idx"] < 1000 and (r["clip"], r["idx"]) in by]
    for r in rows:
        d = by[(r["clip"], r["idx"])]
        sc = spec["scenes"][str(r["scene"])]
        seg = _seg_of(sc, r["scene"], r["clip"])
        host = next((x for x in seg["msgs"] if x.get("split") == r["key"]), None)
        if host is not None:  # 이어쓰기 조각 행(`split_b`) — 시각표의 `on_overlay.ends[호스트][1]`(ON 뒷 조각 끝). 호스트 메시지의 OFF 창 끝(`ends`)도 같이
            e2 = seg.setdefault("on_overlay", {}).setdefault("ends", {}).setdefault(host["key"], [None, None])
            if d.get("te") is not None and e2[1] != float(d["te"]):
                e2[1] = float(d["te"])
                host["ends"][-1] = float(d["te"])
                n += 1
            continue
        it = next((x for x in seg["msgs"] if x["key"] == r["key"]), None)
        if it is None:  # 시각표 토막에 없는 행(다른 토막으로 옮겨졌거나 이어쓰기 아님) — 건너뛰고 알린다
            print(f"  ⚠ {r['clip']}#{r['idx']}: 시각표 토막에 메시지 {r['key'][:8]} 없음 — 건너뜀")
            continue
        pg = r["page"] - 1
        if it.get("split") and pg == 0:  # 앞 조각 행 — 끝 시각은 ON 전용(`on_overlay.ends[열쇠][0]`), OFF 창 끝은 뒷 조각 행이 쥔다
            e2 = seg.setdefault("on_overlay", {}).setdefault("ends", {}).setdefault(it["key"], [None, it["ends"][-1]])
            if d.get("te") is not None and e2[0] != float(d["te"]):
                e2[0] = float(d["te"])
                n += 1
            if d.get("ts") is not None:
                prev_end = seg["msgs"][seg["msgs"].index(it) - 1]["ends"][-1] if seg["msgs"].index(it) else 0.0
                st = seg.setdefault("on_overlay", {}).setdefault("starts", {})
                if abs(float(d["ts"]) - prev_end) > 0.05 and st.get(it["key"]) != float(d["ts"]):
                    st[it["key"]] = float(d["ts"])
                    n += 1
            continue
        tgt = it["ends"]
        if it.get("split_rows"):  # 쪽 나눔 행(11-11) — 편집기 쪽 수가 자막 쪽 수(시각표 `ends` 보다 많을 수 있다). ON 전용 끝 목록 `on_overlay.ends[열쇠]` 에 쪽마다 쓴다(OFF `ends` 는 그대로)
            oe = seg.setdefault("on_overlay", {}).setdefault("ends", {})
            if it["key"] not in oe:
                oe[it["key"]] = [x["t_end"] for x in sorted((x for x in ALL_ROWS if x["clip"] == r["clip"] and x["key"] == r["key"]), key=lambda x: x["page"])]
            tgt = oe[it["key"]]
        if d.get("te") is not None and tgt[pg] != float(d["te"]):
            tgt[pg] = float(d["te"])
            n += 1
        if d.get("ts") is not None:
            if pg == 0:
                mi = seg["msgs"].index(it)
                prev_end = seg["msgs"][mi - 1]["ends"][-1] if mi else 0.0
                st = seg.setdefault("on_overlay", {}).setdefault("starts", {})
                if abs(float(d["ts"]) - prev_end) <= 0.05 and r["key"] not in st:
                    pass  # 앞 메시지 끝에서 바로 이어 여는 값 — 따로 적지 않는다
                elif st.get(r["key"]) != float(d["ts"]):
                    st[r["key"]] = float(d["ts"])
                    n += 1
            else:
                prev = tgt[pg - 1]
                if abs(float(d["ts"]) - prev) > 0.05:
                    print(f"  ⚠ {r['clip']}#{r['idx']}: 둘째 쪽 이후 시작 {d['ts']} ≠ 앞 쪽 끝 {prev} — 시각표는 앞 쪽 끝에서 이어 연다")
        if pg == 0 and d.get("spk") not in (None, "") and d["spk"] != r.get("speaker_name") and it.get("speaker") != d["spk"]:
            it["speaker"] = d["spk"]
            n += 1
    print(f"시각표 반영 {n}곳")
    if n and not dry:
        VS.SPEC.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return n


def apply_sync(clips: list[dict], dry: bool = False) -> list[str]:
    """편집기 `clips/<clip>` 문서의 `sync: true`(마스터 「싱크 확인 끝」, 11-07) — 그 토막의 시각표를 **확정**으로 다룬다.
    · 시각표 토막에서 `draft`(받아쓰기 자동 초안 표시)를 떼고 `synced`(날짜)를 단다 → `voice_sched.load()` 가 정식으로 보고 제품(OFF 흐름 + 시각표 `patch_block`)에 굽는다.
    · 시각(`te`)은 먼저 `apply_sched`(편집기 `edits` 문서) 로 `ends` 에 반영해 둔다 — 이 함수는 확정 표시만 한다.
    · 토막 이름은 `voice_editor_data` 규칙(`scnNNN_sN`·옛 이름 표)이고, 한 토막이 시각표 토막 하나다. 반환 = 확정으로 바뀐 토막 이름 목록(이미 정식이면 안 낸다).
    `sync` 가 아닌(꺼진) 토막은 안 건드린다 — 확정을 되돌리는 일은 이 함수 몫이 아니다(수작업으로 `draft` 를 다시 단다)."""
    import datetime

    spec = json.loads(VS.SPEC.read_text("utf-8"))
    done: list[str] = []
    for c in clips:
        if not c.get("sync"):
            continue
        mm = re.match(r"scn(\d+)_[sg]\d+$", c.get("clip") or "")
        if not mm:
            continue
        sid = int(mm.group(1))
        sc = spec["scenes"].get(str(sid))
        if sc is None:
            continue
        seg = _seg_of(sc, sid, c["clip"])
        if seg.pop("draft", None) is not None:
            seg["synced"] = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
            done.append(c["clip"])
    print(f"싱크 확정 {len(done)}토막: {' '.join(done)}")
    if done and not dry:
        VS.SPEC.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return done


def main() -> int:
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    dry = "--dry" in sys.argv
    if "--sync" in sys.argv:  # 편집기 `clips/<clip>` 문서 덤프(json 목록 또는 폴더) — `sync: true` 토막을 확정으로(`draft` 를 뗀다). 시각은 `--sched` 로 먼저
        src = Path(a[0])
        clips = [json.loads(f.read_text("utf-8")) for f in sorted(src.glob("*.json"))] if src.is_dir() else json.loads(src.read_text("utf-8"))
        apply_sync(clips, dry)
        return 0
    if "--sched" in sys.argv:  # 시각표 장면(18·98·224) — 편집기 db 문서 목록(json) 또는 `edits/*.json` 폴더
        src = Path(a[0])
        docs = [json.loads(f.read_text("utf-8")) for f in sorted(src.glob("*.json"))] if src.is_dir() else json.loads(src.read_text("utf-8"))
        only = next((x.split("=", 1)[1].split(",") for x in sys.argv if x.startswith("--only=")), None)  # 예: --only=scn018_s0,scn098_s0,scn224_x0 — 그 토막만
        docs = [d for d in docs if only is None or d.get("clip") in only]
        return 0 if apply_sched(docs, dry) is not None else 1
    base = {(r["clip"], r["idx"]): r for r in D.build()[0]}
    edited = merge_docs(json.loads(Path(a[0]).read_text("utf-8")), base)
    by_msg: dict[tuple[int, str], list[dict]] = {}
    timing = []
    for r in edited:
        if not r.get("greet"):  # 장면 2 인사 쪽(greet0·1)은 합성 열쇠라 원문 대조표에 없다 — 문안은 `GREET_PAGES`, 시각만 아래 `timing_items` 가 쓴다
            by_msg.setdefault((r["scene"], r["key"], r["clip"]), []).append(r)
        b = base.get((r["clip"], r["idx"]))
        if b and (r.get("t_start") != b["t_start"] or r.get("t_end") != b["t_end"]):
            timing.append({"clip": r["clip"], "idx": r["idx"], "key": r["key"], "t_start": [b["t_start"], r.get("t_start")], "t_end": [b["t_end"], r.get("t_end")]})
    bad = 0
    by_scene: dict[int, dict[str, str]] = {}
    seen: set[tuple[int, str]] = set()
    import voice_sched as VS_

    ontext = {(int(k), x) for k, v in json.loads(VS_.SPEC.read_text("utf-8"))["scenes"].items() for sg in (v if isinstance(v, list) else [v]) for x in sg.get("on_overlay", {}).get("text", {})}  # 비모달 전용 문안 — 모달(OFF) 번역을 건드리지 않는다
    for (sid, key, clip), rs in sorted(by_msg.items()):
        if (sid, key) in ontext or any(r_.get("added") or r_["idx"] >= 1000 for r_ in rs):
            continue
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
            cur = doc["messages"].get(k, {}).get("t", "")
            if cur != t and cur.split("\n", 1)[-1] == t:  # 편집기 행엔 화자 머리줄이 없다(씬 57 「유혈의 동굴 주인 가르고\n…」) — 머리줄만 다른 건 같은 문안이라 머리줄을 지우지 않는다
                continue
            if cur != t:
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
