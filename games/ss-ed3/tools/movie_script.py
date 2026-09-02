"""무비 자막 대본 — 받아쓰기 초벌을 **걸러서** 사람이 볼 수 있게 만든다.

    python3 games/ss-ed3/tools/movie_script.py --clean   # 환각을 걸러 정리한다
    python3 games/ss-ed3/tools/movie_script.py --sheet   # 검수표(마크다운)
    python3 games/ss-ed3/tools/movie_script.py --stat    # 편별 요약

🔴 **Whisper 는 대사가 없는 구간에서 그럴듯한 문장을 지어낸다.** 이 게임은 무비의 절반이
   음악·효과음뿐이라 그 증상이 심하다. 실측으로 유형이 넷이었다(2026-08-29):

     ① 정형구      `ご視聴ありがとうございました` · `作詞・作曲・編曲` · `初音ミク` · `次回予告`
     ② 글자 반복    `編曲編曲編曲…` · `んんんん…` · `ううう…` · `はっはっはっ…`
     ③ 마디 되풀이  같은 문장이 2 초 간격으로 열네 번(`M07` 의 `お疲れ様でした`)
     ④ 겹침 찌꺼기  `[48.4~46.0]` 처럼 **끝이 시작보다 앞**인 마디 — 30초 조각 이음매의 중복

⚠ 거르고 남은 것도 **초벌이다.** 고유명사는 거의 틀린다(실측: `銀の短剣`→`銀の探検`,
   `ジュリオ`→`ジュリア`). 사람이 영상을 보며 고친 뒤에 번역으로 넘긴다.

⚠ 산출물은 `work/review/` 다 — **원문이라 커밋하지 않는다.**
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

IN_DIR = os.path.join(C.REVIEW_DIR, "movie")

#   ① 정형구 — 들어 있으면 그 마디를 통째로 버린다(부분이라도 섞이면 신뢰할 수 없다)
FILLER = (
    "ご視聴ありがとうございました",
    "ご清聴ありがとうございました",
    "チャンネル登録",
    "作詞",
    "作曲",
    "編曲",
    "初音ミク",
    "次回予告",
    "字幕視聴者",
    "エンディング",
)
#   ③ 되풀이 — 같은 문장이 이만큼 이상 이어지면 전부 버린다
REPEAT_MIN = 3
#   ② 글자 반복 — 같은 글자가 이만큼 이어지면 그 마디를 버린다
RUN_MIN = 8


def has_run(s):
    """같은 글자가 `RUN_MIN` 번 이상 이어지나 — `んんんん…` 부류."""
    return re.search(r"(.)\1{%d,}" % (RUN_MIN - 1), s) is not None


def dedupe_phrase(s):
    """같은 **구절**이 잇달아 되풀이되면 지운다 — `第1話 第1話 第1話…` · `ゲルトゲルト…`.

    ⚠ 글자 반복(`んんん`)과 다른 유형이라 자를 따로 둔다. 실측: `M18` 이 한 마디 안에서
      `第1話 ` 를 115 번, `あ、` 를 200 번 되풀이했다.
    """
    for n in range(2, 21):
        #   `(단위)\1{2,}` — 단위가 세 번 이상 이어지면 **한 번만** 남긴다
        pat = re.compile(r"(.{%d})\1{2,}" % n, re.S)
        while True:
            m = pat.search(s)
            if not m:
                break
            s = s[: m.start()] + m.group(1) + s[m.end() :]
    return s.strip()


#   문장을 가르는 자 — 긴 마디를 나눌 때 쓴다
_SENT = re.compile(r"(?<=[。！？!?])")


def split_long(seg, max_sec=12.0, min_sec=1.2):
    """30 초 조각에 뭉쳐 나온 긴 마디를 문장으로 가르고 **글자 수에 비례해** 시각을 나눈다.

    🔴 어림값이다 — 정확한 싱크는 사람이 영상을 보며 맞춘다. 그래도 105 초가 한 덩어리인
      것보다는 훨씬 낫다(그 상태로는 화면에 다 안 들어간다).
    """
    a, b, t = seg["start"], seg["end"], seg["jp"]
    if b - a <= max_sec:
        return [seg]
    parts = [p for p in _SENT.split(t) if p.strip()]
    if len(parts) < 2:
        return [seg]
    total = sum(len(p) for p in parts)
    out, cur = [], a
    for p in parts:
        d = max(min_sec, (b - a) * len(p) / total)
        out.append({"start": round(cur, 2), "end": round(min(b, cur + d), 2), "jp": p.strip()})
        cur += d
        if cur >= b:
            break
    return out


def clean(segs):
    """`(남은 마디, 버린 마디)`."""
    keep, drop = [], []

    def toss(s, why):
        drop.append({**s, "why": why})

    #   ④ 시각이 뒤집힌 것 · 끝이 없는 것
    step1 = []
    for s in segs:
        a, b = s.get("start"), s.get("end")
        if a is None or b is None:
            toss(s, "시각 없음")
        elif b <= a:
            toss(s, "끝<시작 (이음매 중복)")
        else:
            step1.append(s)

    #   ③ 같은 문장 되풀이
    step2, i = [], 0
    while i < len(step1):
        j = i
        while j + 1 < len(step1) and step1[j + 1]["jp"] == step1[i]["jp"]:
            j += 1
        n = j - i + 1
        if n >= REPEAT_MIN:
            for k in range(i, j + 1):
                toss(step1[k], f"같은 문장 {n}회 되풀이")
        else:
            step2.extend(step1[i : j + 1])
        i = j + 1

    #   ①② 정형구 · 글자 반복
    for s in step2:
        t = dedupe_phrase(s["jp"])
        s = {**s, "jp": t}
        if not t:
            toss(s, "구절 반복뿐")
            continue
        #   🔴 정형구는 **도려내고 나머지를 살린다.** 마디를 통째로 버렸더니 끝에 환각이
        #     붙은 진짜 대사까지 같이 날아갔다(M01 의 「ここに銀の短剣を授与する」).
        if any(f in t for f in FILLER):
            for f in FILLER:
                t = t.replace(f, "")
            t = dedupe_phrase(t)
            s = {**s, "jp": t}
            if len(t) < 2:
                toss(s, "환각 정형구뿐")
                continue
        if has_run(t):
            toss(s, "글자 반복")
        else:
            keep.extend(split_long(s))
    return keep, drop


def load_all():
    out = {}
    for f in sorted(os.listdir(IN_DIR)):
        if not (f.startswith("M") and f.endswith(".json")):
            continue
        d = json.load(open(os.path.join(IN_DIR, f), encoding="utf-8"))
        out[d["movie"]] = d["segments"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--stat", action="store_true")
    a = ap.parse_args()
    if not (a.clean or a.sheet or a.stat):
        ap.error("--clean · --sheet · --stat 중 하나")

    raw = load_all()
    cleaned = {m: clean(s) for m, s in raw.items()}

    if a.stat or a.clean:
        n_in = n_out = 0
        for m, (keep, drop) in cleaned.items():
            n_in += len(keep) + len(drop)
            n_out += len(keep)
            mark = "🔇 대사 없음" if not keep else f"마디 {len(keep):2}"
            print(f"  {m}  {mark:12} (버림 {len(drop)})")
        print(f"\n초벌 {n_in} 마디 → 남은 것 {n_out} · 버린 것 {n_in - n_out}")

    if a.clean:
        p = os.path.join(IN_DIR, "_clean.json")
        json.dump(
            {m: k for m, (k, _) in cleaned.items()},
            open(p, "w", encoding="utf-8"),
            ensure_ascii=False,
            indent=1,
        )
        print(f"→ {p}")

    if a.sheet:
        lines = ["# 무비 자막 검수표 (초벌)", ""]
        lines.append("⚠ **받아쓰기 초벌이다.** 고유명사는 거의 틀린다 — 영상을 보며 고친다.")
        lines.append("")
        for m, (keep, drop) in sorted(cleaned.items()):
            lines.append(f"## {m}" + ("  — 🔇 대사 없음(전부 환각)" if not keep else ""))
            lines.append("")
            if keep:
                lines.append("| 시각 | 받아쓴 것 |")
                lines.append("| ---- | --------- |")
                for s in keep:
                    lines.append(f"| {s['start']:.1f}–{s['end']:.1f} | {s['jp']} |")
                lines.append("")
        p = os.path.join(IN_DIR, "_sheet.md")
        open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print(f"→ {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
