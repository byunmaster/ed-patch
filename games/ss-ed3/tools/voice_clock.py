"""시계 장면(V02~V16) 자료 만들기 — `work/review/voice/ko/V0N.json`(문안·시각) + arm 자리 → `script/voice.json` 항목.

    python3 games/ss-ed3/tools/voice_clock.py --sites            # arm 자리(FF 42 바로 뒤)만 본다
    python3 games/ss-ed3/tools/voice_clock.py --write V02 V03    # 항목을 voice.json 에 쓴다

🔴 **왜 시계인가** — 스크립트 안 위치로 마디를 거는 방식(V01·V17~19)은 장면마다 에뮬로 프레임을 재야 했다(장면 직전 세이브가 필요).
시계 방식은 **음성 시작(`FF 42`) 바로 뒤 옵코드 하나**만 후킹해 그때부터 전역 프레임 시계(`subtitle_stub.GCLK`)로 센다 — 마디 시각은
받아쓰기의 **음성 기준 초**(에너지 구간)를 그대로 쓴다. 스크립트 흐름이 달라도 음성은 같은 속도로 흐르므로 흐름에 안 흔들린다.
arm 이 음성보다 늦거나 빠르면 `clock.origin`(초) 하나로 민다.

⚠ 얼굴(초상화)은 **음성 앞**에 미리 싣기 자리가 있어야 뜬다(음성 중엔 CD 가 음성 것). 그 자리는 장면마다 사람이 정해야 해서 기본은 **얼굴 없음**이다
(`face: null` — 이름 줄 + 글자만). 자리를 정하면 `clock.preload` 에 적고 `face` 를 지우면 된다.
"""

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import script_ops as S
import voice_sub as VS

KO_DIR = os.path.join(C.WORK_DIR if hasattr(C, "WORK_DIR") else os.path.join(C.GAME_DIR, "work"), "review", "voice", "ko")
SCENES = {
    "V02": (2, 0x14068),
    "V03": (5, 0xF48E),
    "V04": (6, 0x1BBE2),
    "V05": (14, 0x1779A),
    "V06": (15, 0x1A1D8),
    "V07": (17, 0xEFD6),
    "V08": (19, 0x122BE),
    "V09": (35, 0xFC2E),
    "V10": (31, 0x15910),
    "V11": (56, 0x187F6),
    "V12": (60, 0x14900),
    "V13": (46, 0x12372),
    "V14": (47, 0x1579E),
    "V15": (49, 0x116B6),
    "V16": (66, 0xAECC),
}
GOTO_MIN, DISPLACED_MAX = 6, 14  # 밀어낼 옵코드 묶음의 길이 범위(GOTO 6B 가 들어야 하고 칸 24B 안)


def arm_site(mapno, ff42):
    """`(off, len, 건너뛴 대기 프레임, 건너뛴 알 수 없는 옵코드)` — `FF 42` 바로 뒤에서 처음 밀어낼 수 있는 옵코드 묶음.

    `FF 35` 대기는 건너뛴다(그 프레임만큼 arm 이 음성보다 늦다 → `origin`). 그 밖의 짧은 옵코드는 뒤 옵코드와 묶어 6~14B 로 맞추고,
    묶어도 안 맞으면(뒤가 14B 짜리) 시간 0 으로 보고 건너뛴다 — ⚠ 그 옵코드의 시간을 모르니(예: `FF 37`) 어긋나면 `origin` 으로 민다.
    """
    seq = list(S.ops(f"MAP{mapno:03d}", ff42, 12))
    assert seq[0][1] == "FF 42" and seq[0][2] == 2, seq[0]
    with C.open_disc(1) as d:
        b = d.read(f"/MAP/MAP{mapno:03d}.BIN")
    i, skipped, unknown = 1, 0, []
    while i < len(seq):
        off, tag, ln, _ = seq[i]
        if ln is None:
            raise SystemExit(f"MAP{mapno:03d} {off:#x}: 길이를 모르는 옵코드 {tag}")
        size = 2 + ln
        if tag == "FF 35":
            skipped += struct.unpack(">H", b[off + 2 : off + 4])[0] + 1
            i += 1
            continue
        end, j = off + size, i + 1
        total = size
        while total < GOTO_MIN and j < len(seq) and seq[j][1] != "FF 35" and seq[j][2] is not None:
            total += 2 + seq[j][2]
            j += 1
        if GOTO_MIN <= total <= DISPLACED_MAX:
            return off, total, skipped, unknown
        unknown.append(tag)
        i += 1
    raise SystemExit("arm 자리를 못 찾았다")


def preload_site(mapno, ff42):
    """`(off, len)` — `FF 42` **바로 앞** 옵코드 묶음(6~14B). 얼굴을 음성 전에 싣는 후킹 자리.

    뒤에서 거꾸로 못 읽으므로 앞 `FF 42` 직전 16B 안의 짝수 시작점마다 앞으로 읽어 `FF 42` 에 정확히 닿는 것 중
    가장 짧은 것을 고른다. ⚠ 정적 후보라 **실제로 실행되는지는 에뮬로 본다**(죽은 코드면 얼굴이 안 뜬다).
    """
    best = None
    for st in range(ff42 - 14, ff42 - 5):
        total, ok = 0, False
        for off, tag, ln, _ in S.ops(f"MAP{mapno:03d}", st, 8):
            if off != st + total:
                break
            if off == ff42:
                ok = True
                break
            if ln is None or tag in ("본문",) or tag.startswith("FD 0"):
                break
            total += 2 + ln
        if ok and 6 <= total <= DISPLACED_MAX and (best is None or total < best[1]):
            best = (st, total)
    if best is None:
        raise SystemExit(f"MAP{mapno:03d} {ff42:#x}: 미리 싣기 자리를 못 찾았다")
    return best


def fd03_site(mapno, ff42):
    """`(off, 12)` — `FF 42` 앞이 **대기 루프 조건분기(`FD 03`, 12B)** 인 장면의 미리 싣기 자리(V02·V07·V09).

    `FD 03` 은 길이를 못 풀어(`script_ops`) 위 `preload_site` 가 실패한다. 하지만 이 셋은 모양이 같다 —
    `FD 03 · 목표 4B(절대, 바로 앞 FF 19) · 조건 `40 00 00 01` · 끝 `00 00`` = 12B 로 닫히고, 그 뒤 짧은 옵코드(`FF 36`·`FF 46`, 4B)
    하나만 거쳐 `FF 42` 에 닿는다. 목표가 절대주소라 칸 안에서 실행해도 같다. **모양이 안 맞거나 다른 곳에서 이 자리로 뛰는 참조가
    있으면 거부한다**(10-19 V07·V09 — V02 와 같은 근거).
    """
    with C.open_disc(1) as d:
        b = d.read(f"/MAP/MAP{mapno:03d}.BIN")
    for tail in (0, 4):
        fd = ff42 - tail - 12
        if b[fd : fd + 2] != b"\xfd\x03" or b[fd + 6 : fd + 12] != bytes.fromhex("400000010000"):
            continue
        if tail and b[fd + 12 : fd + 14] not in (b"\xff\x36", b"\xff\x46"):
            continue
        tgt = struct.unpack(">I", b[fd + 2 : fd + 6])[0] - 0x200000
        if b[tgt : tgt + 2] != b"\xff\x19" or tgt + 2 != fd:
            continue
        for a in range(fd, ff42 + 1, 2):
            pat = struct.pack(">I", 0x200000 + a)
            if pat in b:
                raise SystemExit(f"MAP{mapno:03d}: {a:#x} 로 뛰는 참조가 있다 — 칸 안에서 실행하면 달라진다")
        return fd, 12
    raise SystemExit(f"MAP{mapno:03d} {ff42:#x}: FD 03 모양이 아니다")


def add_preload(doc, vid):
    """voice.json 의 시계 장면 `vid` 에 `clock.preload` 를 달고 항목의 `face: null` 을 걷는다(`speaker` 가 얼굴을 정한다)."""
    mapno, ff42 = SCENES[vid]
    ent = doc[vid]
    try:
        off, ln = preload_site(mapno, ff42)
    except SystemExit:
        off, ln = fd03_site(mapno, ff42)
    faces = {it["speaker"] for it in ent["items"] if it.get("speaker") is not None and it["speaker"] < VS.GLOBAL_CAST}
    for it in ent["items"]:
        if it.get("face", 0) is None:
            del it["face"]
    ent["clock"]["preload"] = {
        "off": off,
        "len": ln,
        "wait": 20 * len(faces) + 10,  # 얼굴 한 장 ~20프레임(10-16 V18 실측)
        "_t": f"음성 앞 FF 42 직전 옵코드 묶음({ln}B) — 얼굴 {len(faces)}종을 싣고 간다",
        "_why": "얼굴은 음성 전에 미리 싣는다(음성 중엔 CD 가 음성 것). 한 장에 ~12프레임 + 여유 30 만큼 멈춘다. 정적 후보 — 에뮬로 실행 확인",
    }
    ent["_scene"] = ent["_scene"].replace("얼굴 없음", "얼굴 = speaker")
    return off, ln, len(faces)


def durations(items):
    """표시 초 — 글자 수 어림, 다음 항목 시작 +0.4초를 넘기지 않는다(마지막은 어림 그대로)."""
    out = []
    for i, it in enumerate(items):
        est = VS.DUR_BASE + VS.DUR_PER_CHAR * sum(len(t) for t in it["lines"])
        if i + 1 < len(items):
            est = min(est, items[i + 1]["t"] - it["t"] + 0.4)
        out.append(round(max(est, 1.0), 2))
    return out


def scene_entry(vid):
    mapno, ff42 = SCENES[vid]
    off, ln, skipped, unknown = arm_site(mapno, ff42)
    with open(os.path.join(KO_DIR, f"{vid}.json"), encoding="utf-8") as f:
        ko = json.load(f)
    items = ko["items"]
    durs = durations(items)
    out_items = []
    for it, du in zip(items, durs):
        e = {"t": it["t"], "who": it["who"], "lines": it["lines"], "dur": du, "face": None}
        if it.get("speaker") is not None:
            e["speaker"] = it["speaker"]
        out_items.append(e)
    return {
        "map": f"MAP{mapno:03d}",
        "_scene": f"{vid} — 시계 장면(음성 0초 기준 초, 얼굴 없음) · arm = FF 42({ff42:#x}) 바로 뒤"
        + (f" · 건너뛴 알 수 없는 옵코드 {unknown}" if unknown else ""),
        "clock": {"off": off, "len": ln, "origin": round(skipped / VS.CLOCK_FPS, 3)},
        "hooks": [],
        "items": out_items,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", action="store_true")
    ap.add_argument("--write", nargs="*")
    ap.add_argument("--preload", nargs="*", help="voice.json 의 시계 장면에 미리 싣기 자리를 단다(항목은 그대로)")
    a = ap.parse_args()
    if a.sites:
        for v, (m, o) in SCENES.items():
            off, ln, sk, unk = arm_site(m, o)
            print(f"{v} MAP{m:03d} FF42={o:#x} arm={off:#x} len={ln} 건너뛴 대기 {sk}프레임 ({sk / VS.CLOCK_FPS:.2f}초) {unk or ''}")
    if a.preload is not None:
        with open(VS.SCRIPT, encoding="utf-8") as f:
            doc = json.load(f)
        for v in a.preload or SCENES:
            try:
                off, ln, nf = add_preload(doc, v)
            except SystemExit as e:
                print(f"{v}: 건너뜀 — {e} (FF 42 앞이 조건분기라 묶음을 못 만든다 → 얼굴 없이 이름만)")
                continue
            print(f"{v}: 미리 싣기 {off:#x} len={ln} 얼굴 {nf}종")
        with open(VS.SCRIPT, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.write("\n")
    if a.write is not None:
        path = VS.SCRIPT
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        for v in a.write or SCENES:
            doc[v] = scene_entry(v)
            print(f"{v}: 항목 {len(doc[v]['items'])}")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.write("\n")


if __name__ == "__main__":
    main()
