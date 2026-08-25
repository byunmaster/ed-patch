"""`/CPK/*.CPK` — 이벤트 애니메이션(**Sega FILM** 컨테이너 · Cinepak 영상 + PCM 음성).

    python3 games/ss-ed3/tools/cpk.py            # 목록·길이
    python3 games/ss-ed3/tools/cpk.py --wav M04  # 음성만 뽑는다 (STT 용)

실측(2026-08-25): 320×224 · `cvid`(Cinepak) · 오디오 2ch **8bit** 22,050Hz.
디스크1 M00~M08(5.4분) · 디스크2 M09~M18(11.4분) — **합계 19.8분**.

🔴 **오디오는 planar 다.** 한 블록이 `[왼쪽 전체][오른쪽 전체]` 로 저장되고, 표본은
**signed 8bit** 다. 인터리브로 읽거나 부호를 안 뒤집으면 「필터 씌운 소리」·잡음이 된다
(유저 청취로 확정). ⚠ **소리가 「이상하지만 들리는」 상태는 포맷 오해를 의심한다** —
완전히 깨지지 않아서 그냥 넘어가기 쉽다.

컨테이너 구조:

    'FILM' + 헤더크기(BE32) + 버전 + reserved
      'FDSC' 32B  — 코덱 · 크기 · 오디오 제원
      'STAB' …    — base_freq · sample_count · [offset, size, info1, info2] × N
                    ⚠ `info1 == 0xFFFFFFFF` 면 **오디오 샘플**, 아니면 영상 프레임
    (헤더 뒤부터 샘플 데이터. `offset` 은 헤더 끝 기준)
"""

import argparse
import os
import struct
import sys
import wave

sys.path.insert(0, os.path.dirname(__file__))
import common as C

AUDIO_FLAG = 0xFFFFFFFF


def _be32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def header(disc, name):
    """`(hdr_size, fdsc, [(off, size, info1, info2)…], freq)`."""
    with C.open_disc(disc) as d:
        for n, lba, size in d.files():
            if n != name:
                continue
            hdr = _be32(d.read_extent(lba, 0x40), 4)
            h = d.read_extent(lba, hdr + 64)
            o, fdsc, stab = 16, None, None
            while o < hdr:
                tag, sz = h[o : o + 4], _be32(h, o + 4)
                if tag == b"FDSC":
                    fdsc = {
                        "codec": h[o + 8 : o + 12].decode("ascii", "replace"),
                        "h": _be32(h, o + 12),
                        "w": _be32(h, o + 16),
                        "bpp": h[o + 20],
                        "ch": h[o + 21],
                        "bits": h[o + 22],
                        "rate": struct.unpack_from(">H", h, o + 24)[0],
                    }
                elif tag == b"STAB":
                    freq, cnt = _be32(h, o + 8), _be32(h, o + 12)
                    stab = (
                        freq,
                        [struct.unpack_from(">IIII", h, o + 16 + i * 16) for i in range(cnt)],
                    )
                if sz <= 0:
                    break
                o += sz
            return hdr, fdsc, stab[1], stab[0]
    raise SystemExit(f"없다: {name}")


def to_wav(disc, name, out):
    """음성만 뽑아 WAV 로. **planar → 인터리브** · **signed → unsigned** 변환이 핵심."""
    hdr, fdsc, ent, _ = header(disc, name)
    with C.open_disc(disc) as d:
        for n, lba, size in d.files():
            if n == name:
                data = d.read_extent(lba, size)
                break
    pcm = bytearray()
    for off, sz, i1, _ in ent:
        if i1 != AUDIO_FLAG:
            continue
        blk = data[hdr + off : hdr + off + sz]
        half = len(blk) // 2
        left, right = blk[:half], blk[half:]
        for i in range(half):
            pcm.append((left[i] + 128) & 0xFF)
            pcm.append((right[i] + 128) & 0xFF)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with wave.open(out, "wb") as w:
        w.setnchannels(fdsc["ch"])
        w.setsampwidth(1)
        w.setframerate(fdsc["rate"])
        w.writeframes(bytes(pcm))
    return len(pcm) / fdsc["ch"] / fdsc["rate"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", metavar="M04", help="그 무비의 음성을 뽑는다")
    a = ap.parse_args()
    if a.wav:
        name = f"/CPK/{a.wav}.CPK"
        disc = 1 if int(a.wav[1:]) <= 8 else 2
        out = os.path.join(C.REVIEW_DIR, "cpk", f"{a.wav}.wav")
        print(f"{name} → {out}  {to_wav(disc, name, out):.1f}초")
        return
    tot = 0.0
    for disc in C.DISCS:
        with C.open_disc(disc) as d:
            names = [n for n, _, _ in d.files() if n.startswith("/CPK/")]
        for name in names:
            hdr, fdsc, ent, freq = header(disc, name)
            sec = (ent[-1][2] & 0x7FFFFFFF) / freq
            tot += sec
            na = sum(1 for e in ent if e[2] == AUDIO_FLAG)
            print(
                f"  d{disc} {name:<16}{sec:6.1f}초  프레임 {len(ent) - na:>5} · 음성블록 {na:>4}"
                f"  {fdsc['w']}x{fdsc['h']} {fdsc['codec']}"
            )
    print(f"\n합계 {tot / 60:.1f}분")


if __name__ == "__main__":
    main()
