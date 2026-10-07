"""씬 음성(ADPCM) 꺼내기 · 받아쓰기 초벌 — 대본이 없는 음성 자리(status.md 「나레이션 자막 — 남은 자리」 ⓑ).

음성은 데이터 트랙 안 **OKI MSM5205 4비트 ADPCM**(하위 니블 먼저, 16kHz — devlog 09-16/17 (31) 확정)이고,
씬 코드가 `JSR $5815` + 인라인 4B(섹터 오프셋 lo·hi, 섹터 수 lo·hi)로 AD_CPLAY 스트리밍을 건다.
시작 섹터 = `0x06C2 + 오프셋`(rel, `$5815` 가 `$FD:$FE` 에 `$06:$C2` 를 더한다). 1섹터 ≈ 0.256초.

    python3 games/pce-ed1/tools/voice.py --check        # 확정 표본(rel 1762, 마스터가 알아들은 라이아스 첫 음성)으로 디코더 검산
    python3 games/pce-ed1/tools/voice.py --wav           # 받아쓰기 대상 여섯 → work/review/voice/*.wav
    python3 games/pce-ed1/tools/voice.py --stt           # + 로컬 Whisper 초벌 → work/review/voice/stt.json

⚠ 산출물(음성·받아쓰기)은 **원문이라 커밋하지 않는다**(`work/review/`). 음성은 밖으로 안 보낸다 — 로컬 Whisper.
⚠ 받아쓰기는 **초벌**이다 — 고유명사는 거의 틀린다. 사람이 고친 뒤에야 번역으로 넘어간다.
"""

import argparse
import json
import os
import sys
import wave

import common

VOICE_BASE = 0x06C2  # `$5815`: 시작 섹터 = 이 값 + 인라인 오프셋
RATE = 16000  # 주파수 레지스터 14 → 32000/(16-14)
OUT = common.REVIEW_DIR / "voice"

# 받아쓰기 대상 — OFF 경로에도 메시지가 없는 음성 게이트 여섯(씬, 게이트 자리, 인라인 오프셋, 섹터 수)
TARGETS = {
    "s006": (6, 0x142, 0x00B9, 0x0121),
    "s017": (17, 0x135, 0x01DA, 0x018F),
    "s057": (57, 0x178, 0x0949, 0x0066),
    "s098": (98, 0x148, 0x0E1E, 0x011C),
    "s168": (168, 0x136, 0x121B, 0x0020),
    "s177": (177, 0x1F2, 0x1478, 0x00B0),
}
CHECK = (1762, 32)  # 라이아스 첫 음성 — 마스터가 알아들은 확정본(devlog 09-16/17 (31))

_STEP = [
    16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
    130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658,
    724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552,
]  # fmt: skip
_ADJ = [-1, -1, -1, -1, 2, 4, 6, 8]


def decode(data: bytes) -> list[int]:
    """OKI ADPCM → 12비트 표본(하위 니블 먼저)."""
    out, s, idx = [], 0, 0
    for byte in data:
        for nib in (byte & 0x0F, byte >> 4):
            step = _STEP[idx]
            d = step >> 3
            if nib & 1:
                d += step >> 2
            if nib & 2:
                d += step >> 1
            if nib & 4:
                d += step
            s = s - d if nib & 8 else s + d
            s = max(-2048, min(2047, s))
            idx = max(0, min(48, idx + _ADJ[nib & 7]))
            out.append(s)
    return out


def clip(rel: int, sectors: int) -> list[int]:
    return decode(common.track_data(rel, sectors))


def write_wav(path, samples: list[int]) -> None:
    import struct

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(struct.pack(f"<{len(samples)}h", *(v << 4 for v in samples)))


def stt(path) -> list[dict]:
    """로컬 Whisper(large-v3-turbo) 초벌 — 구간 시각과 함께."""
    import numpy as np
    import torch
    from transformers import pipeline

    torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
    p = pipeline(
        "automatic-speech-recognition",
        model=os.environ.get("ED_WHISPER", "openai/whisper-large-v3-turbo"),
        chunk_length_s=30,
        stride_length_s=(5, 5),
        torch_dtype=torch.float32,
    )
    with wave.open(str(path), "rb") as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    out = p(a, return_timestamps=True, generate_kwargs={"language": "japanese", "task": "transcribe"})
    return [{"t": c["timestamp"], "jp": c["text"]} for c in out.get("chunks", [])]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--wav", action="store_true")
    ap.add_argument("--stt", action="store_true")
    a = ap.parse_args()
    if a.check:
        p = OUT / "check-rel1762.wav"
        write_wav(p, clip(*CHECK))
        print(p, json.dumps(stt(p), ensure_ascii=False) if a.stt else "")
        return
    res = {}
    for name, (sid, at, off, n) in TARGETS.items():
        p = OUT / f"{name}.wav"
        write_wav(p, clip(VOICE_BASE + off, n))
        print(f"{name}: scn{sid:03d} +{at:#x} rel {VOICE_BASE + off} · {n}섹터 ≈ {n * 0.256:.1f}초 → {p}")
        if a.stt:
            res[name] = stt(p)
            print("   ", json.dumps(res[name], ensure_ascii=False)[:400])
    if a.stt:
        (OUT / "stt.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
