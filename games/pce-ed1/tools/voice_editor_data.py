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
import contextlib
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
import translate as T
import typeset
import voice

OPEN_DELAY = {
    (2, 0): 0.0
}  # (씬, 게이트) → 창이 열리는 지연(초) — 장면 2 는 표의 0 이 음성 재생 시작이라 0(재생이 시작되면 창이 열린다, 10-13)
REVIEW_VOICE = common.REVIEW_DIR / "voice"
CARD_VOICE_REL, CARD_VOICE_SECTORS = 8887, 56  # 구형 시스템 카드 안내 화면 음성 — 옛 wav(`syscard-voice.wav`)의 첫 표본으로 디스크에서 찾았다(10-22)


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


def pages_of(kr: str | None, jp: str, speaker: bool = True, sid: int | None = None, on_flow: bool = False) -> tuple[list[str], list[int]]:
    """(쪽 문안 목록, 쪽 바이트 무게). 한국어는 조판기가 정한 창 단위, 원문은 `\\f` 단위. `on_flow` = 음성 자막(비모달) 쪽 나눔 — 시각표 행."""
    if kr:
        with typeset.on_flow() if on_flow else contextlib.nullcontext():
            pgs = typeset.pages(font.expand_packed(kr), speaker=speaker, four=True, keep_windows=typeset.keep_windows(sid))
        txt = ["\n".join(p) for p in pgs]
        w = [sum(2 * len(x) for x in p) + max(0, len(p) - 1) + 1 for p in pgs]
        return txt, w
    parts = [p.strip("\n") for p in jp.split("\f")]
    parts = [p for p in parts if p.strip()] or [jp]
    return parts, [2 * len(p.replace("\n", "")) + p.count("\n") + 1 for p in parts]


def chain_pages(b: bytes, head_key: str, tr: dict, speakers: dict, sid: int | None = None) -> tuple[list[str], list[int], list[str], list[str]] | None:
    """🔴 OFF 경로 첫 메시지가 **화자 머리만**(본문 없이 개행, 종료 바이트 없음)이면 엔진은 이어지는 메시지들을 같은 창에 차례로 찍는다 —
    그 끝(종료 바이트가 있는 메시지)까지가 이 음성이 읽는 문안이다(11-02 씬 40·63·196·204 — 편집기에 한국어가 비어 있던 까닭: 머리 메시지 하나만 읽었다).
    반환 (한국어 쪽 문안, 쪽 무게, 원문 쪽, 쪽마다 화자 표시명) · 머리 메시지가 본문이 있거나 이어지지 않으면 None."""
    ms = M.parse(b)
    i = next((k for k, m in enumerate(ms) if m.key == head_key), None)
    if i is None or ms[i].jp.strip() or ms[i].terminated:
        return None
    texts, weights, jps, spk = [], [], [], []
    cur = speakers.get(ms[i].speaker, ms[i].speaker) if ms[i].speaker else ""
    for m in ms[i:]:
        if m.speaker:
            cur = speakers.get(m.speaker, m.speaker)
        kr = (tr.get(m.key) or {}).get("t")
        if not kr and not m.jp.strip():
            if m.terminated:
                break
            continue
        t, w = pages_of(kr, m.jp, speaker=M.speaker_kind(m, sid), sid=sid)
        jp_pages = [x.strip("\n") for x in m.jp.split("\f") if x.strip()]
        same = len(jp_pages) == len(t)
        for k, (tt, ww) in enumerate(zip(t, w, strict=True)):
            texts.append(tt if kr else "")
            weights.append(ww)
            jps.append(jp_pages[k] if same else (m.jp.replace("\f", "¶") if k == 0 else ""))
            spk.append(cur)
        if m.terminated:
            break
    return texts, weights, jps, spk


# 이어쓰기 조각까지 한 줄로 보여 줄 메시지 열쇠 — 실제로 끊겨 보인 둘만(11-03): 씬 18 「제 이름은」+이름+「…편이옵니다」 · 씬 50 「또」+「도둑맞았어」… 같은 창에 이어지는 조각이라도
# 뒷 조각이 이름 변수·장비 문구로 시작하는 경우(씬 6·198)나 다른 행으로 이미 실린 경우(씬 32·41)는 건드리지 않는다 — 자동 이음은 오탐이 난다.
JOIN_KEYS = {"14de5bc1750b8ace", "9bb472f5ddddac75"}


def joined_kr(b: bytes, key: str, tr: dict, listed: set[str] = frozenset()) -> str | None:
    """같은 창에 이어 찍히는 뒷 조각까지 이은 우리 문안(`voice_sched.tail_join`) — 없으면 그 메시지 문안. 뒷 조각이 따로 행으로 있는 메시지(`listed`)는 잇지 않는다(11-03: 씬 18 #3 · 씬 50 #1 끊김)."""
    import voice_sched as VS

    ms = M.parse(b)
    i = next((k for k, m in enumerate(ms) if m.key == key), None)
    kr = (tr.get(key) or {}).get("t")
    if i is None or kr is None:
        return kr
    if key in JOIN_KEYS and not (i + 1 < len(ms) and ms[i + 1].key in listed):
        kr = VS.tail_join(b, ms, i, tr, stop=frozenset(listed)) or kr
        if key == "9bb472f5ddddac75":  # 씬 50: 앞 창 끝 「또」 + 뒷 창 「도둑맞았어.」 — 원문은 띄어쓰기가 없어 이어 붙으면 「또도둑」(11-05 편집기 점검)
            kr = kr.replace("또도둑", "또 도둑")
    # 🔴 쪽 끝 글(「…나는 」 — 마지막 `\f` 조각)이 **뒷 메시지의 이름 변수 앞 글**인 경우(씬 41 「나는 〈게일〉이라고 하는데」): 꼬리는 뒷 행의 문안 맨 앞으로 옮긴다(11-05)
    if i + 1 < len(ms) and ms[i + 1].key in listed and not ms[i].terminated and "\f" in kr and VS.inline_name(b, ms, i + 1)[0] is not None:
        kr = kr.rsplit("\f", 1)[0]
    kr = kr.rstrip("\f")  # 이음 조각 끝의 쪽 넘김(`\f`)은 빈 쪽이 아니다
    out = VS.with_inline_name(b, ms, i, kr)
    if i > 0 and not ms[i - 1].terminated and VS.inline_name(b, ms, i)[0] is not None and ms[i - 1].key in listed:
        ptr = (tr.get(ms[i - 1].key) or {}).get("t", "")
        if "\f" in ptr:
            out = ptr.rsplit("\f", 1)[1] + out
    return out  # 본문에 끼는 이름 변수(엔진이 찍는 파티원 이름)를 문자로 — 씬 32 「로우」·씬 41 「게일」(11-04)


def _gw():
    import gwin_rt

    return gwin_rt


def speaker_override(b: bytes, key: str) -> str | None:
    """이름 변수가 끼는 메시지의 화자 표시명(머리 `09 xx` 가 있으면 그 이름, 없으면 이름 변수 자신 — 씬 41 「게일이라고 하는데」는 게일 대사) — 아니면 None."""
    import gwin_rt
    import voice_sched as VS

    ms = M.parse(b)
    i = next((k for k, m in enumerate(ms) if m.key == key), None)
    if i is None:
        return None
    nm, hd = VS.inline_name(b, ms, i)
    return None if nm is None else gwin_rt.common_speaker(hd if hd is not None else nm)


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
    seg = json.loads(p.read_text("utf-8")).get("stt", [])
    # 받아쓰기 출력(`voice_words.py` 25초 조각)이 글자 중간에서 잘려 U+FFFD 가 남은 구간이 있다(r1762 · r7412, 10-22) — 편집기에는 「…」 로 낸다
    return [{**x, "jp": x["jp"].replace("\ufffd", "…")} for x in seg]


def build() -> tuple[list[dict], list[dict]]:
    rows, clips = [], []
    allmsgs = G.load_messages()
    speakers = M.load_speakers()
    import voice_sched as VS

    sched = VS.scene_ids(drafts=True)
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
                kr = joined_kr(b, msg["key"], tr)
                texts, weights = pages_of(kr, msg["jp"], speaker=bool(msg["speaker"]), sid=sid)
                jp_pages = [x.strip("\n") for x in msg["jp"].split("\f") if x.strip()]
                chain = chain_pages(b, msg["key"], tr, speakers, sid)  # 화자 머리만 있는 메시지 → 이어지는 메시지까지
                if chain:
                    texts, weights, jp_pages, spk_pages = chain
                    kr = "chain"
                else:
                    spk_pages = None
                tot = sum(weights)
                t0, cum = cursor, 0
                tkey = f"scn{sid:03d}@{p:#x}"
                ov = G.timing_overrides().get(
                    tkey
                )  # 마스터·측정이 덮은 쪽 (열림, 닫힘) — 기준은 이 게이트에 닿은 때(`cursor`)
                # 🔴 `last_page2` 게이트는 **둘째 쪽부터** 자막 표가 걸린다(첫 쪽은 게임이 그대로 띄운다 — `patch_block` page2) — 표 길이는 쪽 수 − 1
                skip0 = 1 if g["rule"].endswith("page2") else 0
                items = G.norm_items(ov) if ov and len(ov) == len(texts) - skip0 else None
                for i, (txt, w) in enumerate(zip(texts, weights, strict=True)):
                    cum += w
                    if items and i >= skip0:
                        o, c = items[i - skip0]
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
                            "speaker_name": spk_pages[i]
                            if spk_pages
                            else (speakers.get(msg["speaker"], msg["speaker"]) if msg["speaker"] else ""),
                            "t_start": round(t0, 2),
                            "t_end": round(t1, 2),
                            "video": f"{clip}.mp4",
                            "open_delay": delay,
                            "open_delay_measured": measured,
                            **({"tkey": tkey, "tpage": i - skip0, "tbase": round(cursor, 2)} if i >= skip0 else {}),
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
    extra_rows(rows, clips, allmsgs, speakers)
    gwin_rows(rows, clips)
    greet_rows(rows, clips)
    syscard_rows(rows, clips)
    return rows, clips


# 🔴 편집기에 없던 음성 토막(마스터 10-30 「아크담 음성이벤트가 편집기에 없어」) — 자막 원천 방침(10-30): **나레이션 OFF 흐름의 같은 대사(게임 데이터의 원문·우리 번역)가 있으면 그걸 쓴다**,
# 받아쓰기(STT)는 OFF 대사가 없는 강제 나레이션 장면에서만. 아래는 (씬, 음성 호출 순번) → OFF 흐름에서 그 음성이 읽는 메시지 열쇠(블록 순서) — 받아쓰기와의 겹침률로 골랐다(`work` 점검,
# 씬 17 0.43~1.0 · 177 0.74~1.0 …). 시각은 **추정**(글자 무게 비례, 받아쓰기가 끝나는 때까지)이라 `approx` 다 — 마스터가 편집기에서 다듬는다. 롬에는 아직 안 닿는다(OFF 흐름 + 음성은 씬 6 꼴 공사).
EXTRA: dict[tuple[int, int], list[str]] = {
    (177, 0): ["767b69", "038dfd", "38e93f", "adfdfd", "918316", "dd7569", "295277", "11b977", "a8abac"],
    (32, 0): ["a8157b", "5ffb5d", "4abc3d", "f0a097", "162b21"],
    (41, 0): ["3e54fd", "2a32b6", "242964", "07b511", "f1f54f", "922386", "8f33a3", "c864a3", "72e5ca", "054d27", "e27906", "b0b2cf", "01d884", "9c8063"],
    (151, 0): ["cf1b8c", "6cdf02", "aba116", "25907c", "683e05", "3b9878", "e3a118", "efaa55", "29645f"],
}


# 시각을 소리로 못 박은 앞머리 행 — (씬, 토막) → [(열쇠 앞머리, 시작, 끝)]. 11-07 누락 자막 전수(마스터 「씬 73 이후」): 177 음성 6.2~7.8초 =
# 디나 「セリオスさま、助けて！！」(메시지 22 — 바이트 순서로는 뒤지만 음성은 첫 대사 앞에서 먼저 나온다). 시각은 초안.
# 원문에 화자 머리가 없는 OFF 대사 토막의 화자(편집기 표시 전용) — (씬, 토막) → {열쇠 앞머리: 원문 화자명}. 11-07 마스터 「씬177 에 대도 게일 화자가 누락」 — 게일 아버지 줄만 채운다.
EXTRA_SPEAKER: dict[tuple[int, int], dict[str, str]] = {(177, 0): {"767b69": "大盗賊 ゲイル", "38e93f": "大盗賊 ゲイル", "adfdfd": "大盗賊 ゲイル", "a8abac": "大盗賊 ゲイル"}}
# 소리 기준 시각 덮어쓰기(편집기 전용, 초안) — (씬, 토막) → {열쇠 앞머리: (시작, 끝)}. 씬 177 #5~#9: 마스터 11-07 청취(#6 30~32.3 · #7 32.3~ · #8 35~37.3 · #9 37.3~45.3)에 받아쓰기(「へえ、親分」 28.5~30 · 「やめろ、クソジジイ」 30~32 · 「３世ってのはやめろ…関係ねえんだ」 33~37.3)를 맞춤.
EXTRA_TIMES: dict[tuple[int, int], dict[str, tuple[float, float]]] = {
    (177, 0): {"918316": (28.0, 30.0), "dd7569": (30.0, 32.3), "295277": (32.3, 35.0), "11b977": (35.0, 37.3), "a8abac": (37.3, 45.3)}
}
EXTRA_HEAD: dict[tuple[int, int], list[tuple[str, float, float]]] = {(177, 0): [("ec9157", 6.2, 7.8)]}


def extra_rows(rows: list[dict], clips: list[dict], allmsgs: dict, speakers: dict) -> None:
    """`EXTRA` 토막 — OFF 대사 메시지로 행을 만든다(시각 추정). 같은 씬의 「못 건」 안내 토막은 대체한다."""
    scenes = {sid for sid, _ in EXTRA}
    clips[:] = [c for c in clips if not (c.get("skipped") and c["scene"] in scenes)]
    for (sid, k), keys in sorted(EXTRA.items()):
        bf = sorted(glob.glob(str(common.OUT_DIR / "text" / f"*_{sid:03d}.bin")))
        b = Path(bf[0]).read_bytes()
        tr = M.load_translations(sid)
        msgs = {m.key: m for m in M.parse(b)}
        voices = [v.start() for v in G.VOICE_AT.finditer(b)]
        vp = voices[k]
        rel, sec = voice.VOICE_BASE + (b[vp + 3] | (b[vp + 4] << 8)), b[vp + 5] | (b[vp + 6] << 8)
        seg = stt_for(rel)
        vsec = round(sec * G.SEC_PER_SECTOR, 2)
        clip = f"scn{sid:03d}_x{k}"
        import voice_sched as VS

        sp_ov = {it["key"]: it["speaker"] for seg_ in VS.load(drafts=True).get(str(sid), []) for it in seg_["msgs"] if it.get("speaker")}  # 시각표가 고친 화자(씬 41 #6 로우 등)
        picked = []
        for kp in keys:
            full = [x for x in msgs if x.startswith(kp)]
            assert len(full) == 1, (sid, kp, full)
            picked.append(msgs[full[0]])
        pages = []
        for m in picked:
            kr = joined_kr(b, m.key, tr, {x.key for x in picked})
            texts, weights = pages_of(kr, m.jp, speaker=False if m.key in T.INLINE_LEAD else M.speaker_kind(m, sid), sid=sid)
            jp_pages = [x.strip("\n") for x in m.jp.split("\f") if x.strip()]
            for i, (txt, w) in enumerate(zip(texts, weights, strict=True)):
                same = len(jp_pages) == len(texts)
                pages.append((m, i, txt if kr else "", jp_pages[i] if same else (m.jp.replace("\f", "¶") if i == 0 else ""), w))
        total_w = sum(p[4] for p in pages) or 1
        end = min(vsec, max((x["t"][1] or 0) for x in seg) if seg else vsec) or vsec
        t0, cum, nrows = 0.0, 0, 0
        for m, i, txt, jp_txt, w in pages:
            cum += w
            t1 = round(end * cum / total_w, 2)
            nrows += 1
            rows.append(
                {
                    "scene": sid,
                    "gate": 0,
                    "clip": clip,
                    "idx": nrows,
                    "key": m.key,
                    "page": i + 1,
                    "jp": jp_txt,
                    "kr": txt,
                    "stt": "".join(x["jp"] for x in seg if t0 <= (x["t"][0] or 0) < t1),
                    "speaker_name": speaker_override(b, m.key) or (speakers.get(EXTRA_SPEAKER[(sid, k)][m.key[:6]], EXTRA_SPEAKER[(sid, k)][m.key[:6]]) if m.key[:6] in EXTRA_SPEAKER.get((sid, k), {}) else None) or (speakers.get(sp_ov[m.key], sp_ov[m.key]) if m.key in sp_ov else speakers.get(m.speaker, m.speaker) if m.speaker else _gw().common_speaker(m.common) if m.common is not None else ""),
                    "t_start": round(t0, 2),
                    "t_end": t1,
                    "video": f"{clip}.mp4",
                    "open_delay": 0.0,
                    "open_delay_measured": False,
                    "approx": True,
                    "source": "OFF 대사",
                }
            )
            t0 = t1
        for r_ in rows:
            if r_["clip"] == clip and r_["key"][:6] in EXTRA_TIMES.get((sid, k), {}):
                r_["t_start"], r_["t_end"] = EXTRA_TIMES[(sid, k)][r_["key"][:6]]
        for hk, h0, h1 in EXTRA_HEAD.get((sid, k), []):
            hm = [m for x, m in msgs.items() if x.startswith(hk)][0]
            hkr = joined_kr(b, hm.key, tr, {hm.key})
            htx, _w = pages_of(hkr, hm.jp, speaker=False if hm.key in T.INLINE_LEAD else M.speaker_kind(hm, sid), sid=sid)
            rows.append(
                {
                    "scene": sid, "gate": 0, "clip": clip, "idx": 0, "key": hm.key, "page": 1, "jp": hm.jp.strip("\n").replace("\f", ""), "kr": htx[0] if hkr else "",
                    "stt": "".join(x["jp"] for x in seg if h0 - 0.3 <= (x["t"][0] or 0) < h1),
                    "speaker_name": speaker_override(b, hm.key) or (speakers.get(hm.speaker, hm.speaker) if hm.speaker else ""),
                    "t_start": h0, "t_end": h1, "video": f"{clip}.mp4", "open_delay": 0.0, "open_delay_measured": False,
                    "approx": True, "draft": True, "added": True, "source": "OFF 대사(누락 보충 11-07 — 시각 초안)",
                }
            )
            nrows += 1
        clips.append(
            {
                "clip": clip,
                "scene": sid,
                "gate": 0,
                "rel": rel,
                "sectors": sec,
                "voice_sec": vsec,
                "subtitle_end_sec": round(t0, 2),
                "open_delay": 0.0,
                "open_delay_measured": False,
                "rows": nrows,
                "open_run": False,
                "stt": seg,
                "wav": f"voice/{clip}.wav",
                "approx": True,
                "source": "OFF 대사" if keys else "받아쓰기(OFF 대사 못 정함)",
            }
        )


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


def battle_voice_pages(rel: int, bi: int) -> dict:
    """보스 전투 음성 한 곳(`battle.VOICE_SITES`) — 음성 위치(디스크 rel·섹터) · 원판 타이머(프레임) · 자막 쪽 목록(전투 문구 조각 하나가 한 쪽 — 끝 옵코드 `03`·`05` 로 이어지는 조각들)."""
    import battle

    blk = battle.parse(rel)[bi]["data"]
    m = battle.VOICE_GATE.search(blk)
    inline = m.group(2)
    t = re.search(rb"\xa2(.)\xa0(.)", blk[m.end(2) : m.end(2) + 5], re.DOTALL)
    msg = re.search(rb"\xa9(.)\x85\x10\xa9(.)\x85\x11", m.group(1), re.DOTALL)
    off = (msg.group(1)[0] | msg.group(2)[0] << 8) - 0xC400
    kr = battle._msgs()
    pages = []
    for u in battle.msg_units(blk):
        if u["off"] < off:
            continue
        end = u["off"] + len(u["body"])
        tail = blk[end : end + 2]
        pages.append(kr.get(battle.msg_key(u["body"]), "").replace("{01}", " "))
        if tail[:1] not in (b"\x03", b"\x05") or (tail[:1] == b"\x05" and tail[1:2] in (b"\x06", b"\x07", b"\x00")):
            break
    return {
        "rel": voice.VOICE_BASE + (inline[0] | inline[1] << 8),
        "sectors": inline[2] | inline[3] << 8,
        "frames": t.group(1)[0] | t.group(2)[0] << 8,
        "pages": pages,
    }


def battle_rows(rows: list[dict], clips: list[dict]) -> None:
    """보스 전투 음성 3곳(아크담 rel 170 · rel 186 · rel 194) — 편집기 토막. 초기 시각은 원판 대기(타이머) 시간을 쪽 글자 수에 비례해 나눈 값 — 마스터가 편집기에서 싱크를 맞춘다.
    시각은 음성 시작 기준이고 `tkey`(`btl<rel>`) 로 `script/voice_timing.json` 에 쓰인다(전투 대사 엔진 자동 넘김이 읽는다)."""
    import battle

    for rel, bi in sorted(battle.VOICE_SITES):
        info = battle_voice_pages(rel, bi)
        total = float(info["frames"]) / 60.0
        weight = [max(1, len(p.replace(" ", ""))) for p in info["pages"]]
        t0 = 0.0
        clip = f"btl{rel:03d}"
        for i, (text, w) in enumerate(zip(info["pages"], weight, strict=True)):
            t1 = total if i == len(weight) - 1 else round(t0 + total * w / sum(weight), 2)
            rows.append(
                {
                    "scene": -2,
                    "gate": bi,
                    "clip": clip,
                    "idx": i + 1,
                    "key": f"{clip}_{i}",
                    "page": 1,
                    "jp": "",
                    "kr": text,
                    "stt": "",
                    "speaker_name": "",
                    "t_start": t0,
                    "t_end": t1,
                    "video": f"{clip}.mp4",
                    "open_delay": 0.0,
                    "open_delay_measured": True,
                    "tkey": clip,
                    "tpage": i,
                    "tbase": 0.0,
                    "battle": True,
                }
            )
            t0 = t1
        clips.append(
            {
                "clip": clip,
                "scene": -2,
                "gate": bi,
                "rel": info["rel"],
                "sectors": info["sectors"],
                "voice_sec": round(info["sectors"] * G.SEC_PER_SECTOR, 2),
                "subtitle_end_sec": total,
                "open_delay": 0.0,
                "open_delay_measured": True,
                "rows": len(info["pages"]),
                "open_run": False,
                "stt": [],
                "wav": f"voice/{clip}.wav",
                "battle": True,
            }
        )


def syscard_rows(rows: list[dict], clips: list[dict]) -> None:
    """구형 시스템 카드 안내 화면(`syscard_screen`) 음성 자막 — 음성 시작 기준 시각. 화자·시각은 마스터가 편집기에서 지정했다(10-21) — `S.SUB_SPEAKERS`."""
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
                "speaker_name": S.SUB_SPEAKERS[i],
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


# 🔴 편집기 저장(db edits)의 열쇠는 「토막이름-idx」다 — 시각표(초안)로 옮겨 온 장면도 **옛 토막 이름을 그대로** 써서 마스터 편집이 붙을 자리를 잃지 않게 한다(관리자 11-02).
LEGACY_CLIP = {(17, 3): "scn017_x0", (40, 0): "scn040_g0", (196, 0): "scn196_g0", (196, 1): "scn196_g1", (198, 0): "scn198_g0", (224, None): "scn224_x0", (20, 0): "scn020_g0", (20, 1): "scn020_g1", (34, 0): "scn034_g0", (57, 0): "scn057_g0", (155, 0): "scn155_g0"}


def sched_rows(rows: list[dict], clips: list[dict], allmsgs: dict, speakers: dict) -> None:
    """전역 시각표 장면(`voice_sched.json`) — 토막마다 메시지 쪽을 시각표 순서대로 한 행씩. 시각은 음성 시작에서 잰 초(창이 열리는 때는 연출을 따라간다)."""
    import voice_sched as VS

    for sid, segs in sorted((int(k), v) for k, v in VS.load(drafts=True).items()):  # 초안(`draft`)도 — 마스터가 편집기에서 검수한다
        bf = sorted(glob.glob(str(common.OUT_DIR / "text" / f"*_{sid:03d}.bin")))
        b = Path(bf[0]).read_bytes()
        tr = M.load_translations(sid)
        msgs = {m.key: m for m in M.parse(b)}
        for si, seg in enumerate(segs):
            if seg.get("voice_gate") is None or seg.get("voice_at"):  # 게이트 밖 호출(ALWAYS 류, 씬 224) · 토막이 호출 자리(`voice_at`)를 쥔 초안 — 블록 오프셋의 음성 호출을 그대로 읽는다
                vp = int(seg["voice_at"], 16)
                assert G.VOICE_AT.match(b, vp), (sid, seg["voice_at"])
                rel, sec = voice.VOICE_BASE + (b[vp + 3] | (b[vp + 4] << 8)), b[vp + 5] | (b[vp + 6] << 8)
            else:
                rel, sec = VS.voice_of(b, seg["voice_gate"])
            clip = LEGACY_CLIP.get((sid, seg.get("voice_gate")), f"scn{sid:03d}_s{si}")
            seg_stt = stt_for(rel)
            t0, nrows = 0.0, 0
            late: list[dict] = []  # 같은 창 이음 조각을 따로 한 행으로 낸 것 — idx 는 뒤에 붙인다(저장 열쇠 「토막-idx」 를 안 당기려고)
            for it in seg["msgs"]:
                m = msgs[it["key"]]
                kr = seg.get("on_overlay", {}).get("text", {}).get(it["key"]) or joined_kr(b, it["key"], tr, {x["key"] for x in seg["msgs"]})
                st_ov = seg.get("on_overlay", {}).get("starts", {}).get(it["key"])
                if st_ov is not None and not it.get("split"):  # 열림 덮어쓰기(마스터 편집) — 첫 쪽은 앞 쪽 끝이 아니라 그 시각에 연다
                    t0 = float(st_ov)
                if it.get("split"):  # 11-04 마스터 「나레이션 OFF 에서도 두 창이면 나누는 게 맞지」 — OFF 창과 같은 경계(원문 메시지 둘)로 두 자막 행
                    import voice_sched as VS2

                    ms_all = M.parse(b)
                    i0 = next(k for k, x in enumerate(ms_all) if x.key == it["key"])
                    pa, pb = VS2.tail_join(b, ms_all, i0, tr, parts=True)[:2]
                    mid, end2 = seg.get("on_overlay", {}).get("ends", {}).get(it["key"], [None, None])
                    nrows += 1
                    spk_a = speakers.get(m.speaker, m.speaker) if m.speaker else ""
                    jp_a = m.jp.strip("\n").replace("\f", "¶")
                    mb = msgs[pb[0]]
                    base = {"scene": sid, "gate": seg["voice_gate"], "clip": clip, "video": f"{clip}.mp4", "open_delay": 0.0, "open_delay_measured": False, "sched": True, "draft": bool(seg.get("draft"))}
                    ta, _ = pages_of(pa[1], m.jp, speaker=True, sid=sid, on_flow=True)
                    rows.append({**base, "idx": nrows, "key": it["key"], "page": 1, "jp": jp_a, "kr": "\n".join(ta), "stt": "", "speaker_name": spk_a, "t_start": round(t0, 2), "t_end": float(mid), "split_a": True})
                    tb, _ = pages_of(pb[1], mb.jp, speaker=False, sid=sid, on_flow=True)
                    late.append({**base, "idx": None, "key": pb[0], "page": 1, "jp": mb.jp.strip("\n").replace("\f", "¶"), "kr": "\n".join(tb), "stt": "", "speaker_name": spk_a, "t_start": float(mid), "t_end": float(end2), "after_idx": nrows, "split_b": True})
                    t0 = float(end2)
                    continue
                spk_k = False if it["key"] in T.INLINE_LEAD else (M.speaker_kind(m, sid) or bool(it.get("speaker")))  # 🔴 비모달 자막(`gwin_rt._on_flow_spec`)과 같은 화자 종류 — 시각표 `speaker` 가 있으면 화자 창(11-11 씬 46 s0 3d33: 편집기 1쪽·자막 2쪽으로 갈렸다)
                texts, _w = pages_of(kr, m.jp, speaker="nl=" if spk_k is True else spk_k, sid=sid, on_flow=True)  # 이름 변수 이어쓰기(INLINE_LEAD)는 화자 창이 아니다(11-05)
                ends_it = list(seg.get("on_overlay", {}).get("ends", {}).get(it["key"], it["ends"]) if it.get("split_rows") else it["ends"])  # 쪽 나눔 행은 자막이 쓰는 끝 목록(`on_overlay.ends`)을 따른다
                if it.get("split_rows") and len(texts) > len(ends_it):  # 🔴 자막이 가른 쪽만큼 행을 낸다(마스터가 쪽마다 시각을 정하게) — 자막(`gwin_rt._on_flow_spec`)과 같이 마지막 구간을 넘친 쪽 수로 균등 나눈다. 시각표 `ends` 는 그대로(반반)
                    kk = len(texts) - len(ends_it) + 1
                    s_ = ends_it[-2] if len(ends_it) > 1 else t0
                    ends_it = [*ends_it[:-1], *[round(s_ + (ends_it[-1] - s_) * (j + 1) / kk, 2) for j in range(kk)]]
                if len(texts) > len(ends_it):  # 이어쓰기 조각이 쪽을 늘렸다 — 시각표(원판 창 쪽 수)는 그대로라 넘친 쪽은 마지막 행에 합친다
                    texts = [*texts[: len(ends_it) - 1], "\n".join(texts[len(ends_it) - 1 :])]
                jp_pages = [x.strip("\n") for x in m.jp.split("\f") if x.strip()]
                same = len(jp_pages) == len(texts)
                for i, (txt, e) in enumerate(zip(texts, VS.fit_ends(ends_it, len(texts)), strict=True)):
                    if it.get("idx0"):  # 11-07 앞머리 보충 줄(씬 88 s0 헤르닐드·151 s0 실피) — 마스터 편집은 「토막-idx」 열쇠라 기존 줄 번호를 안 밀려고 0 번으로 둔다
                        assert len(texts) == 1, (sid, it["key"])
                        row_idx = 0
                    else:
                        nrows += 1
                        row_idx = nrows
                    rows.append(
                        {
                            "scene": sid,
                            "gate": seg["voice_gate"],
                            "clip": clip,
                            "idx": row_idx,
                            "key": it["key"],
                            "page": i + 1,
                            "jp": jp_pages[i]
                            if same
                            else (m.jp.replace("\f", "¶") if i == 0 else ""),
                            "kr": txt if kr else "",
                            "stt": "".join(x["jp"] for x in seg_stt if t0 <= (x["t"][0] or 0) < e),
                            "speaker_name": speaker_override(b, it["key"]) or (speakers.get(it["speaker"], it["speaker"]) if it.get("speaker") else speakers.get(m.speaker, m.speaker) if m.speaker else _gw().common_speaker(m.common) if m.common is not None else ""),  # 시각표 `speaker` 가 원문 머리보다 앞(gwin_rt 와 같다, 11-05 씬 41 #6 로우)
                            "t_start": round(t0, 2),
                            "t_end": float(e),
                            "video": f"{clip}.mp4",
                            "open_delay": 0.0,
                            "open_delay_measured": False,
                            "sched": True,
                            "draft": bool(seg.get("draft")),
                        }
                    )
                    t0 = float(e)
            for ex in seg.get("on_extra", []):  # 추가 행(idx≥1000) — 저장 열쇠 「토막-idx」 를 안 당기려고 번호를 고정으로 둔다
                rows.append(
                    {
                        "scene": sid, "gate": seg["voice_gate"], "clip": clip, "idx": ex["idx"], "key": ex["id"], "page": 1,
                        "jp": "", "kr": ex["text"], "stt": "".join(x["jp"] for x in seg_stt if ex["start"] - 0.3 <= (x["t"][0] or 0) < ex["end"]),
                        "speaker_name": ex["speaker"], "t_start": float(ex["start"]), "t_end": float(ex["end"]), "video": f"{clip}.mp4",
                        "open_delay": 0.0, "open_delay_measured": False, "sched": True, "draft": bool(seg.get("draft")), "added": True,
                    }
                )
            for r_ in late:
                nrows += 1
                r_["idx"] = nrows
                rows.append(r_)
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
                    "draft": seg.get("draft"),
                }
            )


AUDIT = common.GAME_DIR / "script" / "voice_audit.json"
AUDIT_MASTER = common.GAME_DIR / "script" / "voice_audit_master.json"


# 같은 음성(rel)을 두 토막이 나눠 쓰는 곳 — (기준 토막, 복사받는 토막, 열쇠 포함 비교 여부). 문안·쪽이 같은 행은 기준 토막의 시각을 기본값으로 받는다(마스터가 두 번 맞추지 않게, 11-04).
#  씬 32 s0=x0(6/6 같음) · 41 x0⊂s0(19/19, s0 에 「뭐, 뭐라고!?」 행 하나 더) · 151 s0/x0(12/13) · 73 g0 = 74 g0_0(같은 사건의 씬 사본 — 열쇠가 달라 쪽·문안으로)
DUP_CLIPS = (("scn032_s0", "scn032_x0", True), ("scn041_s0", "scn041_x0", True), ("scn151_s0", "scn151_x0", True), ("scn073_s0", "scn074_s0", False))


def copy_dup_times(rows: list[dict]) -> int:
    """`DUP_CLIPS` 의 복사받는 토막 행에 기준 행의 시각(`t_start`/`t_end`)을 채운다 — `dup_of` 에 「기준토막-idx」. 짝이 없는 행은 그대로(표시 안 함)."""
    n = 0
    by = {}
    for r in rows:
        by.setdefault(r["clip"], []).append(r)
    for src, dst, bykey in DUP_CLIPS:
        for rb in by.get(dst, []):
            for ra in by.get(src, []):
                same = ra["page"] == rb["page"] and (ra["kr"] == rb["kr"] or (bykey and ra["kr"].startswith(rb["kr"]))) and (not bykey or ra["key"] == rb["key"])  # 11-07: s0 쪽은 이어지는 서술 메시지를 붙여 읽으므로 x0 문안이 앞머리면 같은 줄(씬 151 실피)
                if same:
                    rb["t_start"], rb["t_end"] = ra["t_start"], ra["t_end"]
                    rb["dup_of"] = f"{src}-{ra['idx']}"
                    n += 1
                    break
    return n


FIXED_CLIPS = {"scn002_g0", "scn006_s0", "scn017_x0"}  # 마스터 청취 확정 — 싱크 재점검 대상이 아니다


def annotate_audit(rows: list[dict], clips: list[dict], master: dict | None = None) -> int:
    """음성 감사 결과(`script/voice_audit.json`, 마스터 11-03 「음성이 없으면 당연히 자막도 빼야지」 · 「편집기에서도 빼도 될 것 같아」)를 행에 붙인다 —
    `voice_match`(있음/일부/불가) · `voice_note`(근거) · 후보 시각 `cand_start`/`cand_end`(마스터가 안 만진 줄은 `t_start`/`t_end` 에도 넣고 `sync_src`=소리 실측) · 마스터 편집값과 0.5초 넘게 어긋나면 `sync_off`(표시만). **음성에 없는 줄(`없음`)은 행을 뺀다**
    (OFF 창 문안은 그대로 — 원판도 OFF 에서만 나오는 글). 🔴 남는 행의 `idx` 는 다시 매기지 않는다 — 편집기 저장 열쇠가 「토막-idx」라 번호가 당겨지면 마스터 편집이 엉뚱한 줄에 붙는다.
    열쇠 = (토막, 메시지 열쇠, 쪽) — 쪽은 편집기 행 `page`(1부터). 뺀 행 목록은 토막의 `dropped_idx` 에 둔다."""
    if not AUDIT.exists():
        return 0
    spec = json.loads(AUDIT.read_text("utf-8"))["rows"]
    by = {(r["clip"], r["key"], r["page"]): r for r in spec}
    if AUDIT_MASTER.exists():  # 마스터 청취 판정이 기계 판정을 덮는다
        for r in json.loads(AUDIT_MASTER.read_text("utf-8"))["rows"]:
            by[(r["clip"], r["key"], r["page"])] = r
    drop = []
    for r in rows:
        a = by.get((r["clip"], r["key"], r["page"]))
        if a is None:
            continue
        r["voice_match"] = a["voice_match"]
        r["voice_note"] = a.get("why", "")
        if a.get("cand_start") is not None:
            r["cand_start"], r["cand_end"] = a["cand_start"], a["cand_end"]
            ed = (master or {}).get((r["clip"], r["idx"]), {})
            if "ts" in ed and abs(a["cand_start"] - float(ed["ts"])) > 0.5:  # 마스터 편집값은 안 덮는다 — 어긋남만 표시
                r["sync_off"] = round(a["cand_start"] - float(ed["ts"]), 2)
            if r["clip"] not in FIXED_CLIPS and not r.get("split_a"):  # 마스터 청취 확정 토막(씬 2·6·17, 11-03 「2,6,17만 고정」)만 기본값을 안 건드린다 — 그 밖은 마스터 편집(db)이 있어도 소리 실측으로 다시 맞춘다(db 수정이 편집기에서 그 위에 얹힌다)
                r["t_start"], r["t_end"] = a["cand_start"], a["cand_end"]
                r["sync_src"] = "소리 실측" if a.get("sync_conf") else "소리 실측(닻 불일치)"
        if a["voice_match"] == "없음":
            drop.append(r)
    for ra in [x for x in rows if x.get("split_a")]:  # 두 행으로 나눈 메시지 — 감사의 소리 실측 구간(메시지 하나 몫)을 글자 수 비례로 두 행에 나눠 준다
        a_ = by.get((ra["clip"], ra["key"], ra["page"]))
        rb = next((x for x in rows if x.get("split_b") and x["clip"] == ra["clip"] and x.get("after_idx") == ra["idx"]), None)
        if a_ and a_.get("cand_start") is not None and rb is not None:
            la, lb = len(ra["kr"].replace("\n", "")), len(rb["kr"].replace("\n", ""))
            mid = round(a_["cand_start"] + (a_["cand_end"] - a_["cand_start"]) * la / (la + lb), 2)
            ra["t_start"], ra["t_end"], rb["t_start"], rb["t_end"] = a_["cand_start"], mid, mid, a_["cand_end"]
            ra["sync_src"] = rb["sync_src"] = "소리 실측" if a_.get("sync_conf") else "소리 실측(닻 불일치)"
            ra["voice_match"] = rb["voice_match"] = a_["voice_match"]
    for r in drop:
        rows.remove(r)
    copy_dup_times(rows)
    cl = {c["clip"]: c for c in clips}
    for r in drop:
        c = cl.get(r["clip"])
        if c is not None:
            c.setdefault("dropped_idx", []).append(r["idx"])
            c["rows"] = c.get("rows", 0) - 1
    return len(drop)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    out = a.out or main_tree() / ".local" / "work" / "inbox" / "pce-ed1" / "voice-editor"
    out.mkdir(parents=True, exist_ok=True)
    rows, clips = build()
    battle_rows(rows, clips)
    annotate_audit(rows, clips)
    for r_ in rows:  # 소리 기준 시각 덮어쓰기(감사 후보 시각보다 뒤 — 마스터 청취가 우선)
        ov = EXTRA_TIMES.get((r_["scene"], 0), {}).get(r_["key"][:6]) if r_["clip"].endswith("_x0") else None
        if ov:
            r_["t_start"], r_["t_end"] = ov
    # 🔴 같은 음성 사본 클립의 `dup_of` 행은 편집기에 안 낸다(마스터 11-05 「편집기에 씬41은 왜 또 두개야?」) — 마스터는 짝의 원본(s0)만 맞추고, 굽기(`voice_editor_apply.merge_docs`)가 짝으로 승계한다.
    #  고유 행(짝에 없는 행, 예: 씬 151 x0 #1)만 남기고 고유 행이 0 이면 토막째 뺀다. 빌드(`build()`)는 그대로 — 승계가 이 행들을 기준으로 한다.
    dup_rows = [r for r in rows if r.get("dup_of")]
    rows = [r for r in rows if not r.get("dup_of")]
    left = {r["clip"] for r in rows}
    gone = {r["clip"] for r in dup_rows} - left
    clips = [c for c in clips if c["clip"] not in gone]
    for c in clips:
        if c["clip"] in {r["clip"] for r in dup_rows}:
            c["rows"] = sum(1 for r in rows if r["clip"] == c["clip"])
    (out / "dup_rows_removed.json").write_text(json.dumps([{"clip": r["clip"], "idx": r["idx"], "dup_of": r["dup_of"], "key": r["key"], "page": r["page"]} for r in dup_rows], ensure_ascii=False, indent=1), "utf-8")
    (out / "data.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    (out / "clips.json").write_text(json.dumps(clips, ensure_ascii=False, indent=1), "utf-8")
    (out / "voice").mkdir(exist_ok=True)
    n = 0
    for c in clips:
        if c.get("skipped"):
            continue
        p = out / c["wav"]
        if not p.exists() and c.get("rel") is None:  # 카드 화면 음성 — 디스크 rel 8887 × 56섹터(안내 프로그램 `AD_CPLAY` 의 음성)
            voice.write_wav_clean(p, voice.clip_clean(CARD_VOICE_REL, CARD_VOICE_SECTORS))
        elif not p.exists():
            voice.write_wav_clean(p, voice.clip_clean(c["rel"], c["sectors"]))  # 직류·포화 정리판(`voice.decode_clean`)
        n += 1
    done = [c for c in clips if not c.get("skipped")]
    print(
        f"{out}: 토막 {len(done)} · 자막 쪽 {len(rows)} · 못 건 토막 {len(clips) - len(done)} · wav {n}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
