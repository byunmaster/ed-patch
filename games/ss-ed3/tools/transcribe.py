"""무비 음성 받아쓰기 — 자막 대본의 **초벌**을 만든다.

    python3 games/ss-ed3/tools/transcribe.py M02        # 한 편
    python3 games/ss-ed3/tools/transcribe.py --all      # 19 편 전부
    python3 games/ss-ed3/tools/transcribe.py --list     # 이미 받아쓴 것
    python3 games/ss-ed3/tools/transcribe.py V02 --segs # 인게임 음성: 에너지 구간마다 따로

🔴 **인게임 음성(`V**`)은 `--segs` 로 받는다** — Whisper 의 마디 시각은 **못 쓴다**(2026-09-04
   실측, V01: 마디 여럿을 한 덩어리로 묶고 시작을 앞으로 당긴다 — 어절 모드도 마찬가지).
   대신 **에너지 포락선으로 발화 구간을 먼저 자르고** 구간마다 Whisper 를 따로 돌린다.
   구간 시작이 곧 자막 시각(`voice.json` 의 `_t`)이고, 스크립트의 `FF 42` 복귀 프레임이 0 초다.
   ⚠ 구간은 초벌이다 — 붙은 두 마디·긴 숨은 사람이 가른다(V01 은 21 구간 → 18 마디).

🔴 **초벌이다. 그대로 쓰지 않는다.** 1998년 게임의 **8bit 22kHz** 음성이고 BGM·효과음이
   같이 실려 있어, 사람 이름·고유명사는 거의 틀린다(`ジュリオ`→`ゆりを` 부류).
   사람이 들으며 고친 뒤에야 번역으로 넘어간다.

⚠ **음성을 밖으로 보내지 않는다** — 로컬 Whisper 로 돌린다. 원저작물이라 외부 API 에
   올리지 않는 쪽을 고른다(루트 CLAUDE.md 「저작권」).

⚠ 산출물은 `work/review/movie/` 다 — **원문이라 커밋하지 않는다.**
   커밋되는 것은 나중에 우리 번역만 담을 `script/movie.json` 이다.
"""

import argparse
import json
import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import cpk
import sap

MODEL = os.environ.get("ED_WHISPER", "openai/whisper-large-v3-turbo")
#   🔴 **어절 타임스탬프는 작은 모델로 뽑는다.** 큰 모델은 정렬용 교차어텐션을 들고 있어야 해서
#     **인코더 어텐션만 32층×20헤드×1500×1500×4B = 5.8GB** 이고, 생성 단계마다 쌓여 16GB 를
#     넘긴다(실측: cgroup `oom_kill 1`, 최대 16.0GiB). `small` 은 12×12 라 1.3GB 로 떨어진다.
#   ⓘ 글(문안)은 이미 큰 모델로 받아 뒀다 — 여기서 필요한 건 **말이 언제 시작하나**뿐이라
#     작은 모델로 충분하다.
WORDS_MODEL = os.environ.get("ED_WHISPER_WORDS", "openai/whisper-small")
SR = 16000  # Whisper 가 요구하는 표본율
OUT_DIR = os.path.join(C.REVIEW_DIR, "movie")
#   어절 타임스탬프를 뽑을 때 잘라 넣는 창 — 메모리를 길이와 무관하게 묶는다
WIN = 30.0
OVERLAP = 3.0


def load_wav(path):
    """WAV → `(모노 float32 [-1,1], 표본율)`. 표준 라이브러리만 쓴다(ffmpeg 없다)."""
    import numpy as np

    with wave.open(path, "rb") as w:
        ch, width, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 1:
        a = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    else:
        raise SystemExit(f"{path}: {width}바이트 표본은 아직 안 읽는다")
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def resample(a, src, dst=SR):
    """`scipy.signal.resample_poly` — 정수비로 줄여 잡음을 안 만든다."""
    if src == dst:
        return a
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(src, dst)
    return resample_poly(a, dst // g, src // g).astype("float32")


_PIPE = {}


def pipe(short=False):
    global _PIPE
    key = "short" if short else "long"
    if key not in _PIPE:
        import torch
        from transformers import pipeline

        torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
        m = WORDS_MODEL if short else MODEL
        print(f"  모델 {m} 여는 중 (처음 한 번은 내려받는다)…", flush=True)
        _PIPE[key] = pipeline(
            "automatic-speech-recognition",
            model=m,
            chunk_length_s=15 if short else 30,
            #   ⚠ 겹침을 준다 — 30초 경계에서 말이 잘리면 그 문장을 통째로 놓친다
            stride_length_s=(3, 3) if short else (5, 5),
            torch_dtype=torch.float32,
        )
    return _PIPE[key]


def transcribe(name, disc=None, words=False):
    """`M04` 한 편 → `[{start, end, jp}]`.

    ⚠ `words=True` 면 **단어 단위 타임스탬프**를 받는다. 일본어는 토큰이 어절로 묶여서
      사실상 **어절 단위**로 나오는데, 이게 싱크에 결정적이다 — 마디 단위로 받으면
      30 초 조각이 통째로 한 덩어리가 되어(`M01` 앞 26 초) 시각을 **글자 수 비례로
      어림**할 수밖에 없고, 그러면 화면과 어긋난다(유저 지적 2026-08-29).
    """
    #   `M**` 는 무비(CPK), `V**` 는 인게임 음성(SAP) — 꺼내는 도구가 다르다
    if name.startswith("V"):
        wav = os.path.join(C.REVIEW_DIR, "sap", f"{name}.wav")
        if not os.path.exists(wav):
            sap.to_wav(name)
    else:
        wav = os.path.join(C.REVIEW_DIR, "cpk", f"{name}.wav")
        if not os.path.exists(wav):
            cpk.to_wav(name) if hasattr(cpk, "to_wav") else None
    if not os.path.exists(wav):
        raise SystemExit(f"{wav} 가 없다 — 먼저 `cpk.py --wav {name}` · `sap.py --wav {name}`")
    a, sr = load_wav(wav)
    a = resample(a, sr)
    if not words:
        out = pipe()(
            a,
            return_timestamps=True,
            generate_kwargs={"language": "japanese", "task": "transcribe"},
        )
        return _chunks(out, 0.0)

    #   🔴 **어절 타임스탬프는 메모리가 편 길이에 비례해 는다.** 교차어텐션 가중치를 조각마다
    #     들고 있다가 마지막에 한꺼번에 푸는 구조라서다. 실측: 12GB 에서 189 초짜리(`M01`)가
    #     OOM(exit 137), 16GB 에서도 RSS 13.8GB 까지 올라 스왑을 때렸다.
    #     ⇒ **우리가 창으로 잘라 돌리고 시각을 더한다.** 그러면 길이와 무관하게 일정하다.
    #   ⚠ 창 경계에서 말이 잘리지 않게 겹침을 준다. 겹친 구간에서 나온 어절은
    #     **앞 창 것을 남긴다**(앞 창은 그 말을 온전히 들었다).
    segs, t0 = [], 0.0
    step = WIN - OVERLAP
    while t0 < len(a) / SR:
        i0, i1 = int(t0 * SR), int(min(len(a), (t0 + WIN) * SR))
        if i1 - i0 < SR // 2:  # 0.5초 미만 꼬리는 버린다
            break
        out = pipe(short=True)(
            a[i0:i1],
            return_timestamps="word",
            batch_size=1,
            generate_kwargs={"language": "japanese", "task": "transcribe"},
        )
        for s in _chunks(out, t0):
            if not segs or s["start"] >= segs[-1]["end"] - 0.05:
                segs.append(s)
        t0 += step
    return segs


#   ── 에너지 구간 (인게임 음성) ──────────────────────────────────────────────
#   50ms RMS 포락선 → 바닥(하위 20%)의 2.5 배를 넘는 자리가 「말」, 0.5 초 이상 조용하면 끊는다.
#   V01 로 맞췄다(발화 18 중 16 이 ±0.3 초, 나머지 둘은 여리게 시작하는 마디라 0.4~0.8 초 늦다).
#   ⚠ 앞 7 초의 환경음(새·바람)이 1.6 배에선 통째로 한 구간이 됐다 — BGM 이 깔린 편은 다시 잰다.
SEG_HOP, SEG_RISE, SEG_GAP, SEG_MIN = 0.05, 2.5, 0.5, 0.2
SEG_PAD = 0.15  # Whisper 에 줄 때 앞뒤로 더 주는 여유(초) — 첫 자음이 잘리지 않게


def segments(a, sr=SR):
    """`[(시작, 끝)]` 초 — 에너지 포락선으로 자른 발화 구간."""
    import numpy as np

    hop = int(sr * SEG_HOP)
    env = np.array([np.sqrt((a[i : i + hop] ** 2).mean()) for i in range(0, len(a) - hop, hop)])
    on = env > np.percentile(env, 20) * SEG_RISE
    out, s, gap = [], None, 0
    for i, v in enumerate(on):
        if v:
            s, gap = (i if s is None else s), 0
        elif s is not None:
            gap += 1
            if gap * SEG_HOP >= SEG_GAP:
                out.append((s, i - gap))
                s = None
    if s is not None:
        out.append((s, len(on)))
    return [
        (round(x * SEG_HOP, 2), round(y * SEG_HOP, 2))
        for x, y in out
        if (y - x) * SEG_HOP >= SEG_MIN
    ]


def transcribe_segments(name):
    """`V01` → `[{start, end, jp}]` — 구간마다 Whisper 를 따로 돌린다(시각은 구간 것)."""
    if not name.startswith("V"):
        raise SystemExit("--segs 는 인게임 음성(V**) 용이다")
    wav = os.path.join(C.REVIEW_DIR, "sap", f"{name}.wav")
    if not os.path.exists(wav):
        sap.to_wav(name)
    a, sr = load_wav(wav)
    a = resample(a, sr)
    segs = []
    for s, e in segments(a):
        i0, i1 = int(max(0.0, s - SEG_PAD) * SR), int((e + SEG_PAD) * SR)
        out = pipe()(a[i0:i1], generate_kwargs={"language": "japanese", "task": "transcribe"})
        segs.append({"start": s, "end": e, "jp": (out.get("text") or "").strip()})
    return segs


def _chunks(out, off):
    """파이프라인 결과 → `[{start, end, jp}]`. `off` 만큼 시각을 민다."""
    segs = []
    for c in out.get("chunks", []):
        s, e = c.get("timestamp", (None, None))
        t = (c.get("text") or "").strip()
        if t and s is not None:
            segs.append({"start": round(s + off, 2), "end": round((e or s) + off, 2), "jp": t})
    return segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", help="M00 M04 … (없으면 --all 필요)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--words", action="store_true", help="어절 단위 타임스탬프 (싱크용)")
    ap.add_argument("--segs", action="store_true", help="인게임 음성: 에너지 구간마다 따로 받는다")
    a = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    if a.list:
        for f in sorted(os.listdir(OUT_DIR)):
            if f.endswith(".json"):
                d = json.load(open(os.path.join(OUT_DIR, f), encoding="utf-8"))
                print(f"  {f[:-5]}  마디 {len(d['segments']):3}  {d.get('model', '')}")
        return 0

    names = a.names
    if a.all:
        names = [f"M{i:02d}" for i in range(19)]
    if not names:
        ap.error("편 이름을 주거나 --all")

    for n in names:
        kind = "segs" if a.segs else "words" if a.words else None
        p = os.path.join(OUT_DIR, f"{n}.{kind}.json" if kind else f"{n}.json")
        if os.path.exists(p):
            print(f"  {n} 건너뜀 (이미 있다 — 다시 하려면 지운다)")
            continue
        print(f"── {n}", flush=True)
        segs = transcribe_segments(n) if a.segs else transcribe(n, words=a.words)
        json.dump(
            {"movie": n, "model": WORDS_MODEL if a.words else MODEL, "segments": segs},
            open(p, "w", encoding="utf-8"),
            ensure_ascii=False,
            indent=1,
        )
        print(f"  마디 {len(segs)} → {p}")
        for s in segs[:4]:
            print(f"    [{s['start']}~{s['end']}] {s['jp']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
