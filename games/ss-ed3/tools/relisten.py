"""재청취 — 마디 단위 받아쓰기(`transcribe.py --segs`)가 못 든 이름·뜻을 **문맥 창**으로 다시 듣는다.

    python3 tools/relisten.py V15 [V16 …]          # 장면 전체
    python3 tools/relisten.py V13 --range 120,127  # 그 구간만, 잘게 가른 마디까지 따로

왜 따로 있나 — `--segs` 는 에너지 구간 하나씩 받아쓰니 마디 안에 문맥이 없다. 그래서 「貴様」가
「しょも」, 「ディーネ」가 「いいね」 로 나왔다(2026-09-05). `--words`(whisper-small)는 환각이 돌아 못 쓴다.
셋으로 푼다 — **시각**은 잘게 가른 에너지 구간(FINE_*)에서, **뜻**은 그 구간을 이어 붙인 창(WIN_*)에서
같은 큰 모델로, 거기에 고유명사 프롬프트(NAMES)와 빔서치 3. 빔 5 는 79 초에 10 분을 넘긴다(CPU).

🔴 말이 쉬지 않고 이어지면 에너지 구간이 안 갈린다(V11 — 32초·51초 덩어리, V03 — BGM). 그러면
**창 하나에 문장 여럿**이라 시각이 없다. 둘로 받는다 — 구간이 WIN_MAX 를 넘으면 그 안의 가장 조용한
자리에서 잘라 창을 만들고(`split_long`), 창마다 Whisper 의 **문장 타임스탬프**(`chunks`)를 같이 받아
둔다. 어절(`--words`)보다 거칠지만 큰 모델 것이라 환각이 없고, 문장 시작 시각으론 충분하다.
⚠ 51초짜리를 한 번에 주면 뒷부분을 통째로 빼먹는다(V11 87.3~138 → 문장 넷만) — 그래서 자른다.

산출: work/review/movie/V**.fine.json
      {windows:[{start,end,jp,chunks:[{start,end,jp}]}], segs:[{start,end,jp}]}
      (`--range` 면 `.fine.part.json` — 마디마다 따로 받아쓴 `jp` 가 든다)
⚠ 원문이 들어 있으니 커밋하지 않는다(work/review/).
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import transcribe as T

# 고유명사 프롬프트 — 문장이 아니라 이름·용어 목록이다(저작권 대상 아님).
NAMES = (
    "ジュリオ、クリス、ラップ爺さん、デュルゼル、ジョアンナ、レバス、ルドルフ王、ゲルド、白き魔女、"
    "エスペランサ、テグラ、イグニス、シフール、オルドス、シャリネ、ラウアールの波、フォルティア、銀の短剣、"
    "聖人の儀式、巡礼、ラグピック、ラグーナ、ディーネ、ルデラ、アロザ、ルード城、ティラスイール、ギドナ、"
    "カジム、ガルガ、ネガル島、幻術使い、ロディ、ハック、グース、シャーラ、アルフ、ベラット、レッド、ルーレ、"
    "フィリー、ピュエンテ、ホルク、ハイゼン、ウドール、天儀室、天球儀、異界、聖剣、五千ピア、借金。"
)

FINE_GAP, FINE_RISE, FINE_MIN = 0.3, 2.0, 0.15  # 잘게 — 마디 시각용
WIN_GAP, WIN_MAX = 1.6, 18.0  # 이어 붙여 — 문맥 창용
BEAMS = 3


def envelope(a, sr=T.SR):
    hop = int(sr * T.SEG_HOP)
    return np.array([np.sqrt((a[i : i + hop] ** 2).mean()) for i in range(0, len(a) - hop, hop)])


def fine_segments(a, sr=T.SR):
    env = envelope(a, sr)
    on = env > np.percentile(env, 20) * FINE_RISE
    out, s, gap = [], None, 0
    for i, v in enumerate(on):
        if v:
            s, gap = (i if s is None else s), 0
        elif s is not None:
            gap += 1
            if gap * T.SEG_HOP >= FINE_GAP:
                out.append((s, i - gap))
                s = None
    if s is not None:
        out.append((s, len(on)))
    return [
        (round(x * T.SEG_HOP, 2), round(y * T.SEG_HOP, 2))
        for x, y in out
        if (y - x) * T.SEG_HOP >= FINE_MIN
    ]


def split_long(segs, env):
    """WIN_MAX 를 넘는 구간은 가운데 절반에서 가장 조용한 자리로 가른다(재귀)."""
    out = []
    for s, e in segs:
        if e - s <= WIN_MAX:
            out.append((s, e))
            continue
        i0, i1 = int((s + (e - s) * 0.25) / T.SEG_HOP), int((s + (e - s) * 0.75) / T.SEG_HOP)
        m = round((i0 + int(np.argmin(env[i0:i1]))) * T.SEG_HOP, 2)
        out += split_long([(s, m), (m, e)], env)
    return out


def windows(segs):
    out = []
    for s, e in segs:
        if out and s - out[-1][1] < WIN_GAP and e - out[-1][0] <= WIN_MAX:
            out[-1][1] = e
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+", help="V15 V16 …")
    ap.add_argument("--range", help="초 구간 a,b — 그 안만, 마디마다 따로 받아쓴다")
    args = ap.parse_args()
    rng = tuple(float(x) for x in args.range.split(",")) if args.range else None

    p = T.pipe()
    gk = {
        "language": "japanese",
        "task": "transcribe",
        "num_beams": BEAMS,
        "prompt_ids": p.tokenizer.get_prompt_ids(NAMES, return_tensors="pt"),
    }

    def hear(a, a0, a1, pad=0.2, stamps=False):
        i0, i1 = int(max(0.0, a0 - pad) * T.SR), int((a1 + pad) * T.SR)
        r = p(a[i0:i1], generate_kwargs=gk, return_timestamps=stamps)
        t = (r.get("text") or "").strip()
        return (t, T._chunks(r, max(0.0, a0 - pad))) if stamps else t

    for name in args.names:
        a, sr = T.load_wav(os.path.join(T.C.REVIEW_DIR, "sap", f"{name}.wav"))
        a = T.resample(a, sr)
        segs = split_long(fine_segments(a), envelope(a))
        if rng:
            segs = [(s, e) for s, e in segs if e > rng[0] and s < rng[1]]
        wins = windows(segs)
        print(f"── {name}: 구간 {len(segs)} · 창 {len(wins)}", flush=True)
        res = {"movie": name, "model": T.MODEL, "windows": [], "segs": []}
        for s, e in wins:
            t, ch = hear(a, s, e, 0.3, stamps=True)
            res["windows"].append({"start": s, "end": e, "jp": t, "chunks": ch})
            print(f"  ▣ [{s}~{e}] {t}", flush=True)
            for c in ch:
                print(f"      ┊ {c['start']:6.1f} {c['jp']}", flush=True)
            for fs, fe in [x for x in segs if x[0] >= s and x[1] <= e]:
                ft = hear(a, fs, fe) if rng else ""
                res["segs"].append({"start": fs, "end": fe, "jp": ft})
                print(f"      [{fs}~{fe}] {ft}", flush=True)
        out = os.path.join(T.OUT_DIR, f"{name}.fine{'.part' if rng else ''}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print(f"  → {out}", flush=True)


if __name__ == "__main__":
    main()
