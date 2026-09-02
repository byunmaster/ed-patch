"""인게임 음성 `/SAP/V**.SAP` — 머리말을 읽어 WAV 로 꺼낸다.

    python3 games/ss-ed3/tools/sap.py --list        # 어느 맵에서 어느 번호가 도나
    python3 games/ss-ed3/tools/sap.py --wav V01     # work/review/sap/V01.wav

🔴 **이건 무비가 아니라 인게임 이벤트 음성이다.** 스크립트 옵코드 `FF 42 <BE16 번호>` 가
   `V%02d.SAP` 를 연다(`/0.BIN` 의 재생 함수 `0x060426dc`, 디스패치 표 `0x0600ce38` #66).
   실측으로 20 장면 41 분이고, 그 맵들이 곧 `/EVT/E<맵>00.FON`(이벤트 그림)을 가진 맵이다.

머리말 0x800 바이트 — `[BE32 프레임수][BE32 채널][BE32 비트][AIFF 80비트 표본율]`,
표본은 `0x800` 부터 빅엔디언 16bit 스테레오 22050Hz.

🔴 **표본은 인터리브가 아니라 「블록 평면」이다** — `[좌 4096][우 4096][좌 4096]…`.
   머리말은 처음부터 옳았고(2채널·74.0초) **배치만 내가 틀리게 읽었다.** 세 번을 헛짚었는데
   증상이 다 달라서 매번 다른 원인으로 보였다(2026-08-30):

     · 표본 단위 인터리브로 읽음 → **2배 빠름**(표본을 하나씩 걸러 쓴 셈)
     · 파일 통째 평면으로 읽음   → 앞·뒤 절반이 **동시에 나서 웅웅거림**
     · 모노 통째로 읽음          → 좌·우 블록이 번갈아 나와 **메아리** + 길이 2배

   ⇒ 가른 건 귀가 아니라 **자기상관**이다. 메아리 지연을 재니 4096 표본에 봉우리가
     섰고(상관 0.483), 제대로 풀자 그 봉우리가 사라졌다(0.258 · 291표본 = 목소리 기본
     주파수). 좌우 상관 0.971 로 거의 모노 — 음성 트랙의 전형이다.
   ⚠ 이걸 틀리면 **받아쓰기가 통째로 환각**이 된다. 「SAP 은 음악이다」로 두 번 오판했다.

⚠ 산출물은 `work/review/` 다 — **원음이라 커밋하지 않는다.**
"""

import argparse
import os
import re
import struct
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

OUT_DIR = os.path.join(C.REVIEW_DIR, "sap")
HDR = 0x800
BLK = 4096  # 채널당 블록 길이(표본) — 자기상관으로 실측
OPCODE = b"\xff\x42"  # FF 42 <BE16 번호> = 음성 재생


def deplanar(x, ch, blk=BLK):
    """블록 평면 → 인터리브. `x` 는 빅엔디언 16bit 표본열."""
    import numpy as np

    if ch == 1:
        return x
    whole = len(x) // (blk * ch) * (blk * ch)
    p = x[:whole].reshape(-1, ch, blk)
    outs = [p[:, c, :].reshape(-1) for c in range(ch)]
    #   꼬리(블록에 못 채운 나머지)는 순서대로 이어 붙인다
    tail = x[whole:]
    for c in range(ch):
        outs[c] = np.concatenate([outs[c], tail[c * blk : (c + 1) * blk]])
    m = min(len(o) for o in outs)
    return np.stack([o[:m] for o in outs], axis=1).reshape(-1)


def _hdr(b):
    """`(프레임수, 채널, 비트, 표본율)`."""
    nf, ch, bits = struct.unpack(">III", b[:12])
    #   AIFF 80비트 확장 부동소수 — 지수 15비트 + 가수 64비트
    exp = struct.unpack(">H", b[12:14])[0] & 0x7FFF
    man = struct.unpack(">Q", b[14:22])[0]
    sr = int(man * 2.0 ** (exp - 16383 - 63))
    return nf, ch, bits, sr


def to_wav(name, disc=None):
    """`V01` → `work/review/sap/V01.wav`. 디스크는 안 주면 있는 쪽에서 찾는다."""
    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, f"{name}.wav")
    for dc in [disc] if disc else (1, 2):
        with C.open_disc(dc) as d:
            for n, lba, size in d.files():
                if n != f"/SAP/{name}.SAP":
                    continue
                import numpy as np

                b = d.read_extent(lba, size)
                nf, ch, bits, sr = _hdr(b)
                x = np.frombuffer(b[HDR : HDR + nf * ch * bits // 8], dtype=">i2")
                with wave.open(dst, "wb") as w:
                    w.setnchannels(ch)
                    w.setsampwidth(bits // 8)
                    w.setframerate(sr)
                    w.writeframes(deplanar(x, ch).astype("<i2").tobytes())
                print(f"  {name}  {nf / sr:6.1f}초  {ch}ch {bits}bit {sr}Hz → {dst}")
                return dst
    raise SystemExit(f"{name}.SAP 를 못 찾았다")


def scan():
    """`[(맵, 오프셋, 번호)]` — 스크립트에서 음성을 부르는 자리."""
    out = []
    with C.open_disc(1) as d:
        for n, lba, size in d.files():
            if not (n.startswith("/MAP/") and n.endswith(".BIN")):
                continue
            b = d.read_extent(lba, size)
            for m in re.finditer(re.escape(OPCODE) + b"(..)", b, re.DOTALL):
                v = int.from_bytes(m.group(1), "big")
                if 1 <= v <= 53:  # 실재하는 번호만 (나머지는 우연 일치다)
                    out.append((os.path.basename(n)[:-4], m.start(), v))
    return sorted(out, key=lambda x: x[2])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--wav", metavar="V01")
    ap.add_argument("--all-wav", action="store_true")
    a = ap.parse_args()
    if a.list:
        for mp, off, v in scan():
            print(f"  V{v:02d}  {mp}  {off:#08x}")
    if a.wav:
        to_wav(a.wav)
    if a.all_wav:
        for _, _, v in scan():
            to_wav(f"V{v:02d}")
    if not (a.list or a.wav or a.all_wav):
        ap.error("--list · --wav · --all-wav 중 하나")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
