"""음성 자막 편집기 자료 — `voice.json` V01~V19 를 한 장의 JSON 으로 뽑는다.

    python3 games/ss-ed3/tools/voice_editor_data.py            # → .local/work/inbox/ss-ed3/voice-editor/data.json
    python3 games/ss-ed3/tools/voice_editor_data.py --check    # 쓰지 않고 요약만

항목마다 `scene`·`idx`(장면 안 자막 번호, 1부터)·`jp`(받아쓰기 원문)·`kr`(지금 자막)·`speaker_id`·`speaker_name`·
`expr`(표정 번호, 없으면 0)·`face_default`(기본 초상 = speaker, 전역 인물일 때)·`face_ok`(그 장면에 미리 싣기가 있어 얼굴이 뜨나)·`pos`(`top`/`bottom` — 기본 bottom)·`t_start`·`t_end`·`video`.

🔴 **산출물에 일본어 원문이 든다** — 커밋하지 않는다(`.local` 은 git 밖). 이 도구는 원문을 코드에 갖지 않고 `work/review/voice/V0N-draft.md`
(받아쓰기 초안표)에서 **시각이 가장 가까운 줄**을 붙인다. 없으면 `jp` 는 빈 문자열이다.
`idx` 는 `voice.json` 에서 자막이 있는 칸의 순서다(V01 은 `hooks` 중 `lines` 가 있는 것, 나머지는 `items`) —
`voice_editor_apply.py` 가 같은 순서로 되짚는다.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import voice_sub as VS

SCENES = [f"V{n:02d}" for n in range(1, 20)]
MATCH_WINDOW = 2.5  # 초 — 초안표 시각과 이만큼 안이면 같은 줄로 본다


def out_dir():
    """메인 트리 `.local/work/inbox/ss-ed3/voice-editor/` — 워크트리 안에 `.local` 을 만들지 않는다."""
    common = (
        os.popen(f"git -C {C.GAME_DIR} rev-parse --path-format=absolute --git-common-dir")
        .read()
        .strip()
    )
    return os.path.join(
        os.path.dirname(common), ".local", "work", "inbox", "ss-ed3", "voice-editor"
    )


def cast_names(doc):
    """`_speaker` 문구에서 `번호 이름` 쌍을 읽는다(16진 한 글자 번호)."""
    txt = doc["_speaker"].split("**0x14 이상")[0]
    return {
        int(k, 16): v
        for k, v in re.findall(r"(?:^|·|:)\s*([0-9a-f]{1,2}) ([가-힣 ]+?)(?= ·|\s*\)|,|$)", txt)
    }


def slots(ent):
    """자막이 있는 칸 목록 — V01 류는 `hooks`, 시계 장면은 `items`."""
    if ent.get("items"):
        return [dict(it) for it in ent["items"]]
    out = []
    for h in ent["hooks"]:
        if h.get("lines") and not h.get("preload"):
            e = dict(h)
            m = re.match(r"\s*([0-9.]+)", str(h.get("_t", "")))
            e["t"] = float(m.group(1)) if m else 0.0
            out.append(e)
    return out


def draft_rows(vid):
    """`[(시각 초, 원문)]` — 받아쓰기 초안표에서. 시각 칸에 숫자가 없는 줄은 건너뛴다."""
    p = os.path.join(C.GAME_DIR, "work", "review", "voice", f"{vid}-draft.md")
    rows = []
    if not os.path.exists(p):
        return rows
    for ln in open(p, encoding="utf-8"):
        if not ln.startswith("|"):
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) < 4:
            continue
        m = re.search(r"[0-9]+(?:\.[0-9]+)?", c[0])
        if m:
            rows.append((float(m.group()), c[2]))
    return rows


def match_rows(ts, rows):
    """`{칸 번호: 초안 줄 번호}` — 시각 차가 작은 쌍부터 하나씩 짝짓는다(1:1, `MATCH_WINDOW` 안).

    칸 순서대로 가까운 줄을 집으면 앞 칸이 뒷 칸의 줄을 가로채 이웃이 줄줄이 한 칸씩 밀린다(V08 #36·V04 #46~49 실측)."""
    pairs = sorted(
        (abs(rt - t), i, j)
        for i, t in enumerate(ts)
        for j, (rt, _) in enumerate(rows)
        if abs(rt - t) <= MATCH_WINDOW
    )
    ui, uj, res = set(), set(), {}
    for _, i, j in pairs:
        if i not in ui and j not in uj:
            ui.add(i)
            uj.add(j)
            res[i] = j
    return res


def face_exprs():
    """`{얼굴: [표정…]}` — 엔진이 그 얼굴로 실제로 그리는 표정(`voice_face_exprs.json`, 에뮬 캡처로 잰 것)."""
    with open(os.path.join(C.GAME_DIR, "voice_face_exprs.json"), encoding="utf-8") as f:
        return json.load(f)["faces"]


def build():
    doc = json.load(open(VS.SCRIPT, encoding="utf-8"))
    names = cast_names(doc)
    out, stat = [], {}
    for vid in SCENES:
        ent = doc[vid]
        has_pre = bool((ent.get("clock") or {}).get("preload")) or any(
            h.get("preload") for h in ent["hooks"]
        )
        sl = slots(ent)
        rows = draft_rows(vid)
        match = match_rows([float(it["t"]) for it in sl], rows)
        hit = 0
        for i, it in enumerate(sl):
            t = float(it["t"])
            jp = ""
            if i in match:
                jp = rows[match[i]][1]
                hit += 1
            sp = it.get("speaker")
            cast = sp is not None and sp < VS.GLOBAL_CAST
            dur = float(it.get("dur", 0))
            out.append(
                {
                    "scene": vid,
                    "idx": i + 1,
                    "jp": jp,
                    "kr": "\n".join(it["lines"]),
                    "speaker_id": sp,
                    "speaker_name": it.get("who") or names.get(sp, ""),
                    "face_default": sp if cast and has_pre else None,
                    "face_ok": bool(cast and has_pre),
                    "pos": VS.pos(it),
                    "expr": int(it.get("expr", 0)),
                    "t_start": round(t, 2),
                    "t_end": round(t + dur, 2),
                    "video": f"{vid}.mp4",
                }
            )
        stat[vid] = (len(sl), hit, has_pre)
    return out, stat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    items, stat = build()
    for v, (n, h, p) in stat.items():
        print(f"{v}: 자막 {n} · 원문 붙음 {h} · 미리 싣기 {'있음' if p else '없음(얼굴 불가)'}")
    print(
        f"합계 {len(items)}줄 · 원문 {sum(1 for x in items if x['jp'])} · 얼굴 가능 {sum(1 for x in items if x['face_ok'])}"
    )
    if a.check:
        return
    d = out_dir()
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "data.json"), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("→", os.path.join(d, "data.json"))
    with open(os.path.join(d, "exprs.json"), "w", encoding="utf-8") as f:
        json.dump(face_exprs(), f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("→", os.path.join(d, "exprs.json"))


if __name__ == "__main__":
    main()
