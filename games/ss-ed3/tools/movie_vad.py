"""무비 자막을 **목소리 트랙에 대고** 점검한다 — 빠진 대사 · 뜬 자막 · 어긋난 경계.

    python3 games/ss-ed3/tools/movie_vad.py --sep          # 목소리/반주 분리 (오래 걸린다)
    python3 games/ss-ed3/tools/movie_vad.py --check        # 전 편 점검
    python3 games/ss-ed3/tools/movie_vad.py --check M13    # 한 편

🔴 **왜 분리가 필요한가.** 이 게임 무비는 BGM 이 안 끊긴다. 그래서 원본 파형의 에너지로는
   발화를 못 가른다(devlog 2026-08-30 에 그 실패가 적혀 있다). `demucs` 로 목소리만 남기면
   문턱 하나로 발화 구간이 나온다 — 실측(M13, 유저 확정 34 줄): 구간 41 개에 재현율 ±0.5초 100%.

🔴 **그래도 싱크를 자동으로 못 맞춘다**(2026-09-02 실측). 붙어 있는 대사 여럿이 한 구간으로
   뭉치기 때문이다 — M13 에서 9.0·10.5·13.5 세 줄이 `9.09~15.34` 한 구간에 들어간다.
   구간 시작은 정확한데 **그 안에서 몇 번째 줄인지**를 모른다. 그건 강제정렬(forced alignment)
   문제고, 우리 받아쓰기는 환청이 섞여 그 조건을 못 맞춘다.
   ⇒ 실측: 침묵에 뜬 자막만 옮기는 규칙으로 채점하니 중앙값 1.15초 → 1.02초에 그쳤고
     34 줄 중 2 줄은 오히려 나빠졌다. **자동 보정은 포기하고 「점검」으로만 쓴다.**

✅ **대신 이 셋은 확실히 잡는다** — 사람이 놓치는 종류다:
   · 자막 없는 목소리 구간 = **빠진 대사** (M18 앞 18 초 · 122 초 뒤가 이렇게 나왔다)
   · 목소리 없는 자막 = 침묵에 떠 있는 줄
   · 시작·끝이 구간 경계에서 얼마나 어긋나나 — 확정된 편의 분포를 기준으로 이상치만 짚는다

⚠ **비명·웃음·노래도 「목소리」로 잡힌다** — demucs 가 뽑는 건 보컬이지 대사가 아니다.
  그래서 「자막 없는 목소리」는 오류 목록이 아니라 **확인 목록**이다. 실측 2026-09-02:
  후보 여섯을 유저가 확인하니 **여섯 다 비언어**였다(M08 괴물·비명 · M16 전투 · M14 폭발 ·
  M01 마을 사람들 박수). 그래도 값을 한다 — 같은 점검으로 **M18 의 빠진 대사 다섯 자리**를
  찾아냈다(앞 18 초 · 122 초 뒤).

✅ **우리 값이 얼마나 정확한지도 이걸로 쟀다** — 유저가 확정한 191 줄의 시작이 발화 구간
  머리에서 **중앙값 +0.02 초**였다. 사분위가 넓은 건(-0.16~+2.62) 오차가 아니라 **한 구간에
  여러 줄이 들어가서**다(붙은 대사를 우리가 여러 줄로 나눈다).

⚠ 산출물은 `work/review/` 다 — 원본 음성이라 **커밋하지 않는다.**
⚠ `demucs` 가 있어야 한다(`pip install demucs`). 없으면 `--check` 가 건너뛴다.
"""

import argparse
import json
import os
import subprocess
import sys
import wave

import numpy as np
from scipy.signal import stft

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

SCRIPT = os.path.join(C.GAME_DIR, "script", "movie.json")
CPK_DIR = os.path.join(C.REVIEW_DIR, "cpk")
VOC_DIR = os.path.join(C.REVIEW_DIR, "vocals")
BAND = (200, 4000)
FRAC = 0.30  # 바닥~봉우리 사이 어디를 문턱으로
GAP = 0.30  # 이보다 긴 침묵에서 구간을 끊는다
MINLEN = 0.20


def vocals(name):
    return os.path.join(VOC_DIR, name, "vocals.wav")


def separate(name):
    """`demucs` 로 목소리만 뽑는다 — 이미 있으면 건너뛴다."""
    if os.path.exists(vocals(name)):
        return True
    src = os.path.join(CPK_DIR, f"{name}.wav")
    if not os.path.exists(src):
        print(f"  {name} 건너뜀 — {src} 가 없다")
        return False
    os.makedirs(VOC_DIR, exist_ok=True)
    r = subprocess.run(
        [sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs",
         "-o", os.path.join(VOC_DIR, name), "--filename", "{stem}.wav", "-j", "4", src],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    if r.returncode:
        print(f"  {name} 분리 실패 — {r.stderr.strip().splitlines()[-1:]}")
        return False
    #   demucs 가 모델 이름 폴더를 하나 더 판다 — 걷어낸다
    inner = os.path.join(VOC_DIR, name, "htdemucs", "vocals.wav")
    if os.path.exists(inner):
        os.replace(inner, vocals(name))
    return os.path.exists(vocals(name))


def regions(path):
    """`[(시작, 끝)]` — 목소리가 이어지는 구간."""
    with wave.open(path) as w:
        n, ch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    a = np.frombuffer(raw, dtype={1: np.uint8, 2: np.int16, 4: np.int32}[sw])
    a = a.astype(np.float32)
    if sw == 1:
        a -= 128
    a = a.reshape(-1, ch).mean(1)
    f, t, Z = stft(a, sr, nperseg=2048, noverlap=2048 - 512)
    m = (f >= BAND[0]) & (f <= BAND[1])
    env = 20 * np.log10(np.abs(Z)[m].sum(0) + 1e-9)
    floor, peak = np.percentile(env, 20), np.percentile(env, 98)
    on = env > floor + (peak - floor) * FRAC
    dt = t[1] - t[0]
    g = max(1, int(GAP / dt))
    out, i = [], 0
    while i < len(on):
        if not on[i]:
            i += 1
            continue
        j = k = i
        while j < len(on):
            if on[j]:
                k = j
            elif j - k > g:
                break
            j += 1
        if t[k] - t[i] >= MINLEN:
            out.append((round(float(t[i]), 2), round(float(t[k]), 2)))
        i = j
    return out


def check(name, lines, pad=0.35):
    """`(빠진 구간, 뜬 자막, 경계 어긋남)`."""
    reg = regions(vocals(name))
    miss = [
        (a, b) for a, b in reg if b - a >= 0.6 and not any(x[0] < b and x[1] > a for x in lines)
    ]
    float_ = [x for x in lines if not any(a - pad <= x[0] <= b for a, b in reg)]
    off = []
    for x in lines:
        near = [(a, b) for a, b in reg if a - 1.5 <= x[0] <= b]
        if near:
            a, _ = min(near, key=lambda r: abs(r[0] - x[0]))
            off.append(round(x[0] - a, 2))
    return miss, float_, off


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--sep", action="store_true", help="목소리/반주 분리")
    ap.add_argument("--check", action="store_true", help="자막을 목소리에 대고 점검")
    a = ap.parse_args()
    with open(SCRIPT, encoding="utf-8") as f:
        sc = json.load(f)
    names = a.names or [k for k in sorted(sc) if not k.startswith("_") and sc[k]]
    if a.sep:
        for n in names:
            print(f"  {n} …", flush=True)
            separate(n)
    if not a.check:
        return 0
    allon = []
    for n in names:
        if not os.path.exists(vocals(n)):
            print(f"  {n} 건너뜀 — 목소리 트랙이 없다 (`--sep {n}`)")
            continue
        miss, float_, off = check(n, sc[n])
        allon += off
        tag = []
        if miss:
            tag.append(f"🔴 자막 없는 목소리 {len(miss)}")
        if float_:
            tag.append(f"🟡 침묵에 뜬 자막 {len(float_)}")
        print(f"  {n}  줄 {len(sc[n]):3}  " + (" · ".join(tag) if tag else "✅"))
        for x, y in miss[:4]:
            print(f"       🔴 {x:7.2f}~{y:7.2f} ({y - x:4.1f}s) 에 목소리가 있는데 자막이 없다")
        for x in float_[:4]:
            print(f"       🟡 {x[0]:7.2f} {x[2].splitlines()[0][:24]!r} — 그 자리에 목소리가 없다")
    if allon:
        v = np.array(allon)
        print(f"\n  시작이 발화 구간 머리에서 얼마나 떨어졌나 — {len(v)}줄")
        print(
            f"    중앙값 {np.median(v):+.2f}s · 사분위 {np.percentile(v, 25):+.2f}~{np.percentile(v, 75):+.2f}"
            f" · |0.5s| 넘는 줄 {(np.abs(v) > 0.5).sum()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
