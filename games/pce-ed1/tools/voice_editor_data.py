#!/usr/bin/env python3
"""음성 자막 편집기 자료 — 나레이션 게이트(음성 토막)마다 자막 쪽의 시각표를 정적 모델로 계산해 낸다.

  python3 tools/voice_editor_data.py [--out DIR]     # 기본 `<메인 트리>/.local/work/inbox/pce-ed1/voice-editor/`

산출(원문·음성 포함이라 **커밋 금지** — `.local`):
  data.json   줄(쪽)마다 한 행 — scene · gate · clip · idx · jp · kr · stt · speaker_name · t_start · t_end · video · open_delay · open_delay_measured
  clips.json  토막마다 — 음성 위치(rel·섹터)·길이·타이머·창이 열리는 지연·받아쓰기 구간
  voice/<clip>.wav  음성(디스크 ADPCM 디코드)
시각 모델 = 상주부와 같다: 쪽 마감 = 창이 열린 시각 + T × (그 쪽까지 누적 바이트 / 전체 바이트), T = 원래 타이머(+ `retime` 늘리기).
창이 열리는 시각의 지연은 **실측한 장면만** 값을 넣고 나머지는 0 · `open_delay_measured: false` 다(scn002 = 4.5초, 컷신 입장 뒤에 열린다).
`kr` 은 정본에 번역이 있으면 그 문안, 없으면 빈 문자열이다(빌드는 원문을 그대로 낸다).
"""

import argparse
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font
import messages as M
import narration_gates as G
import typeset
import voice

OPEN_DELAY = {
    (2, 0): 0.0
}  # (씬, 게이트) → 창이 열리는 지연(초) — 장면 2 는 표의 0 이 음성 재생 시작이라 0(재생이 시작되면 창이 열린다, 10-13)
REVIEW_VOICE = common.REVIEW_DIR / "voice"


def main_tree() -> Path:
    git = common.ROOT / ".git"
    if git.is_file():  # 워크트리 — 메인 트리는 git common dir 의 부모
        import subprocess

        cd = subprocess.run(
            [
                "git",
                "-C",
                str(common.ROOT),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return Path(cd).parent
    return common.ROOT


def pages_of(kr: str | None, jp: str) -> tuple[list[str], list[int]]:
    """(쪽 문안 목록, 쪽 바이트 무게). 한국어는 조판기가 정한 창 단위, 원문은 `\\f` 단위."""
    if kr:
        pgs = typeset.pages(font.expand_packed(kr), speaker=True)
        txt = ["\n".join(p) for p in pgs]
        w = [sum(2 * len(x) for x in p) + max(0, len(p) - 1) + 1 for p in pgs]
        return txt, w
    parts = [p.strip("\n") for p in jp.split("\f")]
    parts = [p for p in parts if p.strip()] or [jp]
    return parts, [2 * len(p.replace("\n", "")) + p.count("\n") + 1 for p in parts]


def gate_info(b: bytes, sid: int) -> dict[int, dict]:
    """게이트 번호 → {m: 메시지 적재 매치, tgt, o} — `patch_block` 과 같은 방식으로 OFF 경로 메시지를 찾는다."""
    idx = [m.start() for m in re.finditer(re.escape(G.GATE), b)]
    out = {}
    for gi, rule in G.SITES.get(sid, {}).items():
        if rule == "skip":
            continue
        o = idx[gi]
        tgt = o + 5 + (9 if rule == "raias" else b[o + 4])
        m = (
            G.MSG.search(b, tgt, tgt + G.PRE_MAX + 11)
            if rule == "single_pre"
            else G.MSG.match(b, tgt)
        )
        out[gi] = {"m": m, "tgt": tgt, "o": o, "rule": rule}
    return out


def runs_with_voice(b: bytes, sid: int) -> list[dict]:
    """`voice_runs` 와 같은 규칙으로 음성 토막을 만들되 음성 자리·섹터를 함께 낸다. 토막마다 timers = [(자리, 프레임, 자막인가)]."""
    runs: list[dict] = []
    cur = None

    def vinfo(vp: int) -> tuple[int, int]:
        return voice.VOICE_BASE + (b[vp + 3] | (b[vp + 4] << 8)), b[vp + 5] | (b[vp + 6] << 8)

    for gi, rule, _o, tgt, voices, timers in G.gate_events(b, sid):
        if rule == "raias":  # 음성 호출이 게이트 앞에 있다 — 블록의 첫 `JSR $5815`
            v = G.VOICE_AT.search(b)
            rel, sec = vinfo(v.start())
            runs.append(
                {
                    "gate": gi,
                    "rel": rel,
                    "sectors": sec,
                    "timers": [(p, t, True) for p, t in timers[:1]],
                    "open": False,
                }
            )
            cur = None
            continue
        if rule == "skip":
            if cur:
                cur["open"] = True
            cur = None
            continue
        if rule == "all":
            for k, (vp, vf) in enumerate(voices):
                nxt = voices[k + 1][0] if k + 1 < len(voices) else tgt
                tm = [(p, v, True) for p, v in timers if vp < p < nxt][:1]
                rel, sec = vinfo(vp)
                runs.append({"gate": gi, "rel": rel, "sectors": sec, "timers": tm, "open": False})
            cur = None
            continue
        picked = (
            {timers[-1][0]} if rule in ("last", "last_page2") and timers else {p for p, _ in timers}
        )
        for p, kind, val in sorted(
            [(p, "V", f) for p, f in voices] + [(p, "T", v) for p, v in timers]
        ):
            if kind == "V":
                rel, sec = vinfo(p)
                cur = {"gate": gi, "rel": rel, "sectors": sec, "timers": [], "open": False}
                runs.append(cur)
            elif cur is not None:
                cur["timers"].append((p, val, p in picked))
    return runs


def stt_for(rel: int) -> list[dict]:
    p = REVIEW_VOICE / f"r{rel}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text("utf-8")).get("stt", [])


def build() -> tuple[list[dict], list[dict]]:
    rows, clips = [], []
    allmsgs = G.load_messages()
    speakers = M.load_speakers()
    import voice_sched as VS

    sched = VS.scene_ids()
    for sid in sorted(set(G.SITES) - sched):  # 시각표 장면은 아래 `sched_rows` 가 낸다
        bf = sorted(glob.glob(str(common.OUT_DIR / "text" / f"*_{sid:03d}.bin")))
        b = Path(bf[0]).read_bytes()
        tr = M.load_translations(sid)
        extras = G.retime(b, sid)
        info = gate_info(b, sid)
        # 타이머 자리 → 그 타이머가 속한 게이트(자막 메시지는 게이트의 OFF 경로 메시지)
        gate_of = {}
        for gi, rule, o, tgt, _v, timers in G.gate_events(b, sid):
            for p, _t in timers:
                gate_of[p] = gi
        for gi, rule in sorted(G.SITES[sid].items()):
            if rule == "skip":
                clips.append(
                    {
                        "clip": f"scn{sid:03d}_g{gi}",
                        "scene": sid,
                        "gate": gi,
                        "skipped": "자동으로 못 건 자리 — 이 구간 자막 없음"
                        + (f" ({G.OPEN_RUNS[sid]})" if sid in G.OPEN_RUNS else ""),
                    }
                )
        runs = runs_with_voice(b, sid)
        for k, run in enumerate(runs):
            clip = f"scn{sid:03d}_g{run['gate']}" + (
                f"_{k}" if sum(r["gate"] == run["gate"] for r in runs) > 1 else ""
            )
            delay = OPEN_DELAY.get((sid, run["gate"]), 0.0)
            measured = (sid, run["gate"]) in OPEN_DELAY
            seg = stt_for(run["rel"])
            cursor = delay  # 초 — 음성 시작 기준
            nrows = 0
            for p, val, ok in run["timers"]:
                T = (val + extras.get(p, 0)) / G.FPS
                if not ok:
                    cursor += T
                    continue
                g = info[gate_of[p]]
                m = g["m"]
                addr = (m.group(1)[0] | (m.group(2)[0] << 8)) - G.BASE
                msg = allmsgs[sid].get(addr) or next(
                    (allmsgs[sid][x] for x in range(addr + 1, addr + 24) if x in allmsgs[sid]), None
                )
                if msg is None:
                    raise SystemExit(f"scn{sid:03d}: 메시지 {addr:#x} 를 못 찾았다")
                kr = (tr.get(msg["key"]) or {}).get("t")
                texts, weights = pages_of(kr, msg["jp"])
                jp_pages = [x.strip("\n") for x in msg["jp"].split("\f") if x.strip()]
                tot = sum(weights)
                t0, cum = cursor, 0
                tkey = f"scn{sid:03d}@{p:#x}"
                ov = G.timing_overrides().get(
                    tkey
                )  # 마스터·측정이 덮은 쪽 (열림, 닫힘) — 기준은 이 게이트에 닿은 때(`cursor`)
                items = G.norm_items(ov) if ov and len(ov) == len(texts) else None
                for i, (txt, w) in enumerate(zip(texts, weights, strict=True)):
                    cum += w
                    if items:
                        o, c = items[i]
                        t1 = cursor + c
                        if o is not None:
                            t0 = cursor + o
                    else:
                        t1 = cursor + T * cum / tot
                    same = len(jp_pages) == len(texts)
                    stt_txt = "".join(x["jp"] for x in seg if t0 <= (x["t"][0] or 0) < t1)
                    nrows += 1
                    rows.append(
                        {
                            "scene": sid,
                            "gate": gate_of[p],
                            "clip": clip,
                            "idx": nrows,
                            "key": msg["key"],
                            "page": i + 1,
                            "jp": jp_pages[i]
                            if same
                            else (msg["jp"].replace("\f", "¶") if i == 0 else ""),
                            "kr": txt if kr else "",
                            "stt": stt_txt,
                            "speaker_name": speakers.get(msg["speaker"], msg["speaker"])
                            if msg["speaker"]
                            else "",
                            "t_start": round(t0, 2),
                            "t_end": round(t1, 2),
                            "video": f"{clip}.mp4",
                            "open_delay": delay,
                            "open_delay_measured": measured,
                            "tkey": tkey,
                            "tpage": i,
                            "tbase": round(cursor, 2),
                        }
                    )
                    t0 = t1
                cursor += items[-1][1] if items else T
            clips.append(
                {
                    "clip": clip,
                    "scene": sid,
                    "gate": run["gate"],
                    "rel": run["rel"],
                    "sectors": run["sectors"],
                    "voice_sec": round(run["sectors"] * G.SEC_PER_SECTOR, 2),
                    "subtitle_end_sec": round(cursor, 2),
                    "open_delay": delay,
                    "open_delay_measured": measured,
                    "rows": nrows,
                    "open_run": run["open"],
                    "stt": seg,
                    "wav": f"voice/{clip}.wav",
                }
            )
    sched_rows(rows, clips, allmsgs, speakers)
    gwin_rows(rows, clips)
    greet_rows(rows, clips)
    syscard_rows(rows, clips)
    return rows, clips


def greet_rows(rows: list[dict], clips: list[dict]) -> None:
    """장면 2 인사 창(`GREET_PAGES`) — 설교(`scn002_g0`) 앞 두 쪽. 설교 첫 쪽은 인사가 닫히는 때에 열린다. 시각은 음성 재생 시작 기준(`voice_timing` 의 `scn002@greet` 가 덮는다)."""
    for sid, pages in G.GREET_PAGES.items():
        clip = f"scn{sid:03d}_g0"
        mine = [r for r in rows if r["clip"] == clip]
        if not mine:
            continue
        raw = G.timing_overrides().get(G.GREET_KEY[sid])
        items = (
            G.norm_items(raw)
            if raw and len(raw) == len(pages)
            else [(o, c) for _w, _t, o, c in pages]
        )
        for r in mine:
            r["idx"] += len(pages)
        if mine[0]["t_start"] == 0.0:  # 설교 첫 쪽은 열림 값이 없으면 인사가 닫히는 때에 열린다
            mine[0]["t_start"] = items[-1][1]
        t0 = 0.0
        for i, ((who, text, *_t), (o, c)) in enumerate(zip(pages, items, strict=True)):
            if o is not None:
                t0 = o
            rows.append(
                {
                    "scene": sid,
                    "gate": 0,
                    "clip": clip,
                    "idx": i + 1,
                    "key": f"greet{i}",
                    "page": 1,
                    "jp": "",
                    "kr": text,
                    "stt": "",
                    "speaker_name": who,
                    "t_start": t0,
                    "t_end": c,
                    "video": f"{clip}.mp4",
                    "open_delay": 0.0,
                    "open_delay_measured": True,
                    "greet": True,
                    "tkey": G.GREET_KEY[sid],
                    "tpage": i,
                    "tbase": 0.0,
                }
            )
            t0 = c
        for c in clips:
            if c["clip"] == clip:
                c["rows"] += len(pages)
    rows.sort(key=lambda r: (r["clip"] != "", r["scene"], r["clip"], r["idx"]))


def syscard_rows(rows: list[dict], clips: list[dict]) -> None:
    """구형 시스템 카드 안내 화면(`syscard_screen`) 음성 자막 — 음성 시작 기준 시각. 화자는 아직 정해지지 않았다(디나·세리오스 — 마스터 판정 대기)."""
    import syscard_screen as S

    rows_ = []
    for i, (text, start) in enumerate(S.SUBS):
        end = S.SUBS[i + 1][1] if i + 1 < len(S.SUBS) else S.VOICE_END_S
        rows_.append(
            {
                "scene": -1,
                "gate": -1,
                "clip": "syscard",
                "idx": i + 1,
                "key": f"syscard{i}",
                "page": 1,
                "jp": "",
                "kr": text,
                "stt": "",
                "speaker_name": "",
                "t_start": start,
                "t_end": end,
                "video": "syscard.mp4",
                "open_delay": 0.0,
                "open_delay_measured": True,
                "band": True,
            }
        )
    rows.extend(rows_)
    clips.append(
        {
            "clip": "syscard",
            "scene": -1,
            "gate": -1,
            "rel": None,
            "sectors": None,
            "voice_sec": S.VOICE_END_S,
            "subtitle_end_sec": S.VOICE_END_S,
            "open_delay": 0.0,
            "open_delay_measured": True,
            "rows": len(rows_),
            "open_run": False,
            "stt": [],
            "wav": "voice/syscard.wav",
            "band": True,
        }
    )


def gwin_rows(rows: list[dict], clips: list[dict]) -> None:
    """월드를 안 멈추는 대사창 모양 자막(`gwin_rt`) — 장면 2 인사. 음성 시작에서 잰 초."""
    import gwin_rt

    for sid, spec in sorted((int(k), v) for k, v in gwin_rt.build_specs().items()):
        bf = sorted(glob.glob(str(common.OUT_DIR / "text" / f"*_{sid:03d}.bin")))
        b = Path(bf[0]).read_bytes()
        v = G.VOICE_AT.search(b)
        rel = voice.VOICE_BASE + (b[v.start() + 3] | b[v.start() + 4] << 8)
        sec = b[v.start() + 5] | b[v.start() + 6] << 8
        clip = f"scn{sid:03d}_gwin"
        for i, pg in enumerate(spec["pages"]):
            rows.append(
                {
                    "scene": sid,
                    "gate": -1,
                    "clip": clip,
                    "idx": i + 1,
                    "key": f"gwin{i}",
                    "page": 1,
                    "jp": "",
                    "kr": pg["text"],
                    "stt": "",
                    "speaker_name": pg.get("speaker", ""),
                    "t_start": pg["start"],
                    "t_end": pg["end"],
                    "video": f"{clip}.mp4",
                    "open_delay": 0.0,
                    "open_delay_measured": True,
                    "gwin": True,
                }
            )
        clips.append(
            {
                "clip": clip,
                "scene": sid,
                "gate": -1,
                "rel": rel,
                "sectors": sec,
                "voice_sec": round(sec * G.SEC_PER_SECTOR, 2),
                "subtitle_end_sec": spec["pages"][-1]["end"],
                "open_delay": 0.0,
                "open_delay_measured": True,
                "rows": len(spec["pages"]),
                "open_run": False,
                "stt": stt_for(rel),
                "wav": f"voice/{clip}.wav",
                "gwin": True,
            }
        )


def sched_rows(rows: list[dict], clips: list[dict], allmsgs: dict, speakers: dict) -> None:
    """전역 시각표 장면(`voice_sched.json`) — 토막마다 메시지 쪽을 시각표 순서대로 한 행씩. 시각은 음성 시작에서 잰 초(창이 열리는 때는 연출을 따라간다)."""
    import voice_sched as VS

    for sid, segs in sorted((int(k), v) for k, v in VS.load().items()):
        bf = sorted(glob.glob(str(common.OUT_DIR / "text" / f"*_{sid:03d}.bin")))
        b = Path(bf[0]).read_bytes()
        tr = M.load_translations(sid)
        msgs = {m.key: m for m in M.parse(b)}
        for si, seg in enumerate(segs):
            rel, sec = VS.voice_of(b, seg["voice_gate"])
            clip = f"scn{sid:03d}_s{si}"
            seg_stt = stt_for(rel)
            t0, nrows = 0.0, 0
            for it in seg["msgs"]:
                m = msgs[it["key"]]
                kr = (tr.get(it["key"]) or {}).get("t")
                texts, _w = pages_of(kr, m.jp)
                jp_pages = [x.strip("\n") for x in m.jp.split("\f") if x.strip()]
                same = len(jp_pages) == len(texts)
                for i, (txt, e) in enumerate(zip(texts, it["ends"], strict=True)):
                    nrows += 1
                    rows.append(
                        {
                            "scene": sid,
                            "gate": seg["voice_gate"],
                            "clip": clip,
                            "idx": nrows,
                            "key": it["key"],
                            "page": i + 1,
                            "jp": jp_pages[i]
                            if same
                            else (m.jp.replace("\f", "¶") if i == 0 else ""),
                            "kr": txt if kr else "",
                            "stt": "".join(x["jp"] for x in seg_stt if t0 <= (x["t"][0] or 0) < e),
                            "speaker_name": speakers.get(m.speaker, m.speaker) if m.speaker else "",
                            "t_start": round(t0, 2),
                            "t_end": float(e),
                            "video": f"{clip}.mp4",
                            "open_delay": 0.0,
                            "open_delay_measured": False,
                            "sched": True,
                        }
                    )
                    t0 = float(e)
            clips.append(
                {
                    "clip": clip,
                    "scene": sid,
                    "gate": seg["voice_gate"],
                    "rel": rel,
                    "sectors": sec,
                    "voice_sec": round(sec * G.SEC_PER_SECTOR, 2),
                    "subtitle_end_sec": round(t0, 2),
                    "open_delay": 0.0,
                    "open_delay_measured": False,
                    "rows": nrows,
                    "open_run": False,
                    "stt": seg_stt,
                    "wav": f"voice/{clip}.wav",
                    "sched": True,
                }
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    out = a.out or main_tree() / ".local" / "work" / "inbox" / "pce-ed1" / "voice-editor"
    out.mkdir(parents=True, exist_ok=True)
    rows, clips = build()
    (out / "data.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    (out / "clips.json").write_text(json.dumps(clips, ensure_ascii=False, indent=1), "utf-8")
    (out / "voice").mkdir(exist_ok=True)
    n = 0
    for c in clips:
        if c.get("skipped"):
            continue
        p = out / c["wav"]
        if not p.exists() and c.get("rel") is None:  # 카드 화면 음성 — 따로 뽑아 둔 wav
            src = REVIEW_VOICE / "syscard.wav"
            if src.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(src.read_bytes())
        elif not p.exists():
            voice.write_wav(p, voice.clip(c["rel"], c["sectors"]))
        n += 1
    done = [c for c in clips if not c.get("skipped")]
    print(
        f"{out}: 토막 {len(done)} · 자막 쪽 {len(rows)} · 못 건 토막 {len(clips) - len(done)} · wav {n}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
