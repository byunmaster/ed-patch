#!/usr/bin/env python3
"""음성 토막 받아쓰기(감사 입력 만들기) — `voice_audit.py` 가 읽는 두 가지를 낸다.

    wds/<토막>.json      소형(whisper-small) 20초 창(15초 걸음) — 구절(ph)과 구절 시각. RSS ≈ 4GB
    chunks20/<토막>.json 대형(whisper-large-v3-turbo) 20초 창(10초 걸음) — 텍스트만(교차 판정)

    sh scripts/heavy.sh python3 games/pce-ed1/tools/voice_transcribe.py <wav 폴더> <토막> [...]   # 🔴 무거운 일 — 줄 서기

산출은 메인 트리 `.local/work/inbox/pce-ed1/voice-audit/`(원문 일본어 받아쓰기라 커밋 금지). 이미 있는 파일은 건너뛴다(--force 로 다시).
"""

import json
import os
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import voice_audit as VA

AUD = Path(VA.AUD)


def load(wav: Path):
    with wave.open(str(wav), "rb") as w:
        rate = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    return a, rate


def pipe(model: str):
    import torch
    from transformers import pipeline

    torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
    return pipeline("automatic-speech-recognition", model=model, torch_dtype=torch.float32)


def windows(total: float, win: float, step: float):
    t = 0.0
    while True:
        yield t, min(total, t + win)
        if t + win >= total:
            break
        t += step


def main() -> int:
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--force"]
    wavdir, clips = Path(args[0]), args[1:]
    (AUD / "wds").mkdir(parents=True, exist_ok=True)
    (AUD / "chunks20").mkdir(parents=True, exist_ok=True)
    small = large = None
    for c in clips:
        a, rate = load(wavdir / f"{c}.wav")
        total = len(a) / rate
        f1, f2 = AUD / "wds" / f"{c}.json", AUD / "chunks20" / f"{c}.json"
        gen = {"language": "japanese", "task": "transcribe"}
        if force or not f1.exists():
            small = small or pipe("openai/whisper-small")
            ch = []
            for t0, t1 in windows(total, 20.0, 15.0):
                r = small({"raw": a[int(t0 * rate) : int(t1 * rate)], "sampling_rate": rate}, return_timestamps=True, generate_kwargs=gen)
                ph = []
                for x in r.get("chunks", []):
                    s, e = x["timestamp"]
                    if s is None:
                        continue
                    ph.append({"text": x["text"], "ts": [t0 + s, t0 + (e if e is not None else s + 0.3)]})
                ch.append({"t0": t0, "t1": t1, "text": r["text"], "ph": ph})
            f1.write_text(json.dumps({"clip": c, "dur": round(total, 3), "chunks": ch}, ensure_ascii=False), "utf-8")
        if force or not f2.exists():
            large = large or pipe("openai/whisper-large-v3-turbo")
            ch = []
            for t0, t1 in windows(total, 20.0, 10.0):
                r = large({"raw": a[int(t0 * rate) : int(t1 * rate)], "sampling_rate": rate}, generate_kwargs=gen)
                ch.append({"t0": t0, "t1": t1, "text": r["text"]})
            f2.write_text(json.dumps({"clip": c, "dur": round(total, 3), "chunks": ch}, ensure_ascii=False), "utf-8")
        print("done", c, round(total, 1), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
