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

🔴 **V20(디스크2 트랙2, 크레딧)은 섹터가 끼워진 스트림이다 — 이어 읽으면 버벅거린다**(마스터 귀로 발견 2026-09-27).
   MODE2 서브헤더를 보면 **「파일 1 섹터 2개 + 빈 섹터 4개」**가 되풀이되고, 사이사이에 엔딩 그림
   `END01~16.GRP`(파일 2~, 각 131 섹터)가 끼어 있다. 빈 섹터는 데이터·EDC 까지 전부 0 이다(2 배속 읽기를 음성
   속도 88.2KB/s 에 맞춘 조절 — 6 중 2 = 50 섹터/초). ⇒ **서브헤더 파일 번호가 1 인 섹터만**, 머리말이 말하는
   크기(`0x800 + 표본수×4`)만큼 이어 붙인다(`to_wav_v20`) — **520 초**, 좌우 상관 0.9~1.0 · 시간차 0.
   🔑 ISO 디렉터리의 크기(45.9MB)는 **소리 데이터 크기**지 섹터가 퍼진 범위가 아니다 — 스트림은 그 세 배 남짓
      (LBA 201161~ 트랙 끝 가까이)에 퍼져 있다. **ISO 범위에서 끊으면 177 초에서 편지가 잘린다**(두 번째 판이 그랬다).
   ⚠ 세 번 틀렸다: ① 전부 이어 읽음(빈 섹터가 끼어 버벅 · 「오른쪽이 블록 둘 앞선다」는 그 착시) →
     ② ISO 범위에서 끊음(177 초, 편지 중간 절단 — 「머리말 520 초는 빈 칸까지 센 값」이라고 **틀리게** 적었다) →
     ③ 머리말 크기만큼 파일 1 을 모음(이것). 머리말이 처음부터 옳았다. ⚠ 파일 번호는 **디스크 전체에서 따로** 매긴다
     (그림은 2~17) — 「구간마다 새로 매긴다」도 오진이었다.
   ⇒ **뽑은 뒤 좌우 시간차를 잰다** — 음성 트랙은 0 이어야 한다. **머리말 길이와 뽑은 길이가 같은지도** 본다.
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


V20_LBA = 201161  # disc2 ISO 가 적은 V20.SAP 시작 — 트랙2(MODE2) 안이다
TRACK2_LBA = 200805  # disc2 트랙1 섹터 수 = 트랙2 파일의 0 번 섹터(INDEX 00 부터 파일에 들어 있다)


def to_wav_v20():
    """`V20` → `work/review/sap/V20.wav` — 트랙2 에서 **서브헤더 파일 1 섹터만** 이어 붙인다(위 🔴)."""
    import numpy as np

    path = next(p for n, _m, p in C.disc_tracks(2) if n == 2)
    buf = bytearray()
    with open(path, "rb") as f:
        f.seek((V20_LBA - TRACK2_LBA) * 2352)
        need = None
        while len(s := f.read(2352)) == 2352:
            if s[16] == 1:
                buf += s[24 : 24 + 2048]
            if need is None and len(buf) >= HDR:
                nf, ch, bits, _sr = _hdr(bytes(buf[:HDR]))
                need = HDR + nf * ch * bits // 8
            if need is not None and len(buf) >= need:
                break
    if need is None or len(buf) < need:
        raise SystemExit(f"V20 이 모자란다: {len(buf)} < {need} — 트랙2 가 잘렸나")
    buf = buf[:need]
    _nf, ch, bits, sr = _hdr(bytes(buf[:HDR]))
    x = np.frombuffer(bytes(buf[HDR : len(buf) // 2 * 2]), dtype=">i2")
    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, "V20.wav")
    with wave.open(dst, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(bits // 8)
        w.setframerate(sr)
        w.writeframes(deplanar(x, ch).astype("<i2").tobytes())
    print(f"  V20  {len(x) / ch / sr:6.1f}초  {ch}ch {bits}bit {sr}Hz (트랙2 파일1 섹터만) → {dst}")
    return dst


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
