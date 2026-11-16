"""음성 장면 시각표 **초안**을 받아쓰기 낱말 시각으로 자동 생성한다 — `script/voice_sched.json` 에 `draft` 표시로 넣고 마스터가 편집기에서 검수한다(관리자 11-01 ③).
    python3 tools/voice_draft.py [씬 …] [--min 0.5] [--write]       # 씬을 안 주면 정식 시각표가 없는 음성 씬 전부
방법: 씬 블록의 음성 호출(게이트 ON 경로 안 `JSR $5815`)마다 `voice_pick.pick`(인식 글자열과 가장 비슷한 메시지를 시간 순으로) → `voice_align.align`(쪽 끝 시각:
맞은 글자의 시각, 못 맞춘 건 이웃 사이 글자 수 비례, 마지막 쪽 +0.4초) → 토막 `{"voice_gate", "force_off", "draft": {...}, "msgs"}`. `force_off` 는 그 씬의 다른
게이트(`narration_gates.SITES`, 메시지가 OFF 경로에 있는 것)다. 받아쓰기 낱말(`work/review/voice/words_r<rel>.json`, `voice_words.py`)이 없는 토막은 건너뛰고 적는다.
🔴 초안은 제품에 안 들어간다 — `voice_sched.load()` 가 `draft` 항목을 뺀다(시험 빌드의 비모달 자막 `gwin_rt.on_flow_spec` 과 편집기 자료만 본다). 정식 항목은 안 건드린다.
"""
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import messages as M
import narration_gates as N
import voice
import voice_align as A
import voice_pick as P
import voice_sched as VS

MIN_DEFAULT = 0.5
JOSA = re.compile(r"(은/는|이/가|을/를|과/와|으로/로|아/야|이랑/랑)")  # 런타임 조사 자리표시 — 안 B 가 못 그리는 가변 문안의 표지


def voice_calls(blk: bytes) -> list[tuple[int | None, int, int, int]]:
    """[(게이트 번호 또는 None, 음성 rel, 섹터 수, 호출 오프셋)] — 게이트 ON 경로 안의 호출은 그 게이트, 밖(ALWAYS 류)은 None."""
    gates = [m.start() for m in re.finditer(re.escape(N.GATE), blk)]
    spans = [(k, g + 5, g + 5 + blk[g + 4]) for k, g in enumerate(gates)]
    out = []
    for m in N.VOICE_AT.finditer(blk):
        off = blk[m.start() + 3] | blk[m.start() + 4] << 8
        sec = blk[m.start() + 5] | blk[m.start() + 6] << 8
        rel = voice.VOICE_BASE + off
        if not (1 <= sec <= 600 and 1700 <= rel < 9786):  # 음성 구역 밖은 효과음 류
            continue
        k = next((k for k, lo, hi in spans if lo <= m.start() < hi), None)
        out.append((k, rel, sec, m.start()))
    return out


def draft_scene(sid: int, thr: float) -> tuple[list[dict], list[str]]:
    """씬의 토막 초안들과 메모."""
    blk = A.load_block(sid)
    msgs = {m.key: m for m in M.parse(blk)}
    sites = set(N.SITES.get(sid, {}))
    segs, notes = [], []
    for k, rel, sec, at in voice_calls(blk):
        if not (A.REVIEW / f"words_r{rel}.json").exists():
            notes.append(f"rel {rel}({sec}섹터): 받아쓰기 낱말 없음 — voice_words.py {rel} {sec}")
            continue
        rows = P.pick(sid, rel, thr)
        keys = []
        for r in rows:  # 같은 메시지가 두 번 잡히면 처음 것만(같은 대사 중복은 사람이 본다)
            if r["key"] not in keys:
                keys.append(r["key"])
        if not keys:
            notes.append(f"rel {rel}: 일치 {thr} 이상인 메시지 없음")
            continue
        res = A.align(sid, rel, keys, msgs)
        tr = M.load_translations(sid)
        skip = [k_ for k_ in keys if JOSA.search((tr.get(k_) or {}).get("t", ""))]  # 조사 자리표시(이/가 …)가 든 가변 문안 — 엔진이 ON 에서도 제 창으로 띄우고 안 B 는 건너뛴다(198 「이/가 들어 있었다」)
        seg = {
            "voice_gate": k,
            "force_off": sorted(sites - {k}),
            "draft": {"src": f"words_r{rel}", "pick_min": thr, "match": res["match"], "picked": [r["ratio"] for r in rows], "made": datetime.datetime.now(tz=datetime.UTC).date().isoformat()},
            "msgs": res["msgs"],
        }
        seg["voice_at"] = f"{at:#x}"  # 이 토막의 음성 호출 자리(블록 오프셋) — 한 게이트 안에 호출이 둘이면 게이트 번호만으론 둘째를 못 찾는다(씬 46·50 — 11-05)
        if skip:
            seg["on_overlay"] = {"skip": skip}
            notes.append(f"rel {rel}: 가변 문안(조사 자리표시) {len(skip)}개 → on_overlay.skip(엔진 창 그대로)")
        if k is None:
            # 게이트 밖 호출(ALWAYS 류, 씬 224) — 안 B 는 이 자리를 입구로 쓴다(`gwin_rt.on_flow_spec`)
            notes.append(f"rel {rel}: 게이트 밖 음성 호출(ALWAYS 류) — voice_gate 없음, 안 B 입구는 voice_at {at:#x}")
        segs.append(seg)
    return segs, notes


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    thr = float(sys.argv[sys.argv.index("--min") + 1]) if "--min" in sys.argv else MIN_DEFAULT
    write = "--write" in sys.argv
    formal = VS.load()  # 정식(초안 제외)
    if args:
        sids = [int(a) for a in args]
    else:
        sids = sorted(
            int(p.stem.split("_")[1])
            for p in common.OUT_DIR.glob("text/*_[0-9][0-9][0-9].bin")
            if voice_calls(p.read_bytes()) and p.stem.split("_")[1].lstrip("0") not in formal
        )
        sids = sorted(set(sids))
    raw = json.loads(VS.SPEC.read_text("utf-8")) if VS.SPEC.exists() else {"scenes": {}}
    changed = 0
    for sid in sids:
        if str(sid) in formal:
            print(f"scn{sid:03d}: 정식 시각표가 있다 — 건너뜀")
            continue
        segs, notes = draft_scene(sid, thr)
        for n in notes:
            print(f"scn{sid:03d}: {n}")
        for seg in segs:
            print(f"scn{sid:03d} 게이트 {seg['voice_gate']}: 일치 {seg['draft']['match']} · 메시지 {len(seg['msgs'])} · 쪽 {sum(len(m['ends']) for m in seg['msgs'])} · 끝 {seg['msgs'][-1]['ends'][-1]}초")
        if segs and write:
            raw["scenes"][str(sid)] = segs if len(segs) > 1 else segs[0]
            changed += 1
    if write and changed:
        VS.SPEC.write_text(json.dumps(raw, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"{VS.SPEC}: 초안 {changed}씬 씀")
    return 0


if __name__ == "__main__":
    sys.exit(main())
