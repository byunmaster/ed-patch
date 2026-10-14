#!/usr/bin/env python3
"""음성 토막의 **구간 시각** — 로컬 Whisper 로 구간(문장)마다 (시작, 끝) 초를 뽑아 `work/review/voice/words_r<rel>.json` 에 둔다(원문이라 커밋 금지).
`voice_align.py` 가 이걸 대사 쪽 문안과 맞춰 쪽 끝 시각 초안을 만든다. 무거운 일 — `sh scripts/heavy.sh` 로 돈다.

    python3 tools/voice_words.py <rel> <섹터수> [...]
"""

import json
import os
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import voice

OUT = common.REVIEW_DIR / "voice"


_PIPE = None
CHUNK = float(os.environ.get("ED_CHUNK", "25"))  # 초 — 조각 하나. 🔴 단어 단위 시각은 어텐션을 모아 10초 조각에도 RSS 7GB 에 조각당 7분이라 버렸다(10-12) — 구간(문장) 단위 시각만 쓴다
OVERLAP = 1.0  # 앞뒤로 겹치는 초 — 조각 경계의 단어가 잘리지 않게


def _pipe():
    global _PIPE
    import torch
    from transformers import pipeline

    if _PIPE is None:  # 한 번만 적재한다
        torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
        _PIPE = pipeline(
            "automatic-speech-recognition",
            model=os.environ.get("ED_WHISPER", "openai/whisper-large-v3-turbo"),
            torch_dtype=torch.float32,
        )
    return _PIPE


def words(wav: Path) -> list[dict]:
    """wav → [{w, t:[시작,끝]}] — 25초 조각(겹침 1초)으로 나눠 받아쓰고 조각 시작을 더해 잇는다.
    겹친 구간은 **조각 안쪽(경계에서 0.5초 안)**의 단어를 버려 중복을 없앤다."""
    import numpy as np

    with wave.open(str(wav), "rb") as w:
        rate = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    total = len(a) / rate
    p = _pipe()
    out: list[dict] = []
    t0 = 0.0
    while t0 < total:
        t1 = min(total, t0 + CHUNK + OVERLAP)
        seg = a[int(t0 * rate) : int(t1 * rate)]
        res = p(
            {"raw": seg, "sampling_rate": rate},
            return_timestamps=True,
            generate_kwargs={"language": "japanese", "task": "transcribe"},
        )
        lo = t0 + (OVERLAP / 2 if t0 > 0 else 0.0)  # 앞 조각과 겹친 앞 0.5초는 앞 조각이 낸다
        hi = t1 - (OVERLAP / 2 if t1 < total else 0.0)
        for c in res.get("chunks", []):
            s, e = c["timestamp"]
            if s is None:
                continue
            s += t0
            e = (e + t0) if e is not None else s + 0.3
            if lo <= s < hi:
                out.append({"w": c["text"], "t": [round(s, 2), round(e, 2)]})
        t0 += CHUNK
        print(f"  {t0:.0f}/{total:.0f}s", flush=True)
    return out


def main() -> int:
    args = sys.argv[1:]
    for k in range(0, len(args), 2):
        rel, sec = int(args[k]), int(args[k + 1])
        wav = OUT / f"r{rel}.wav"
        if not wav.exists():
            voice.write_wav(wav, voice.clip(rel, sec))
        res = words(wav)
        (OUT / f"words_r{rel}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
        print(f"rel {rel}: 단어 {len(res)}개 → {OUT / f'words_r{rel}.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
