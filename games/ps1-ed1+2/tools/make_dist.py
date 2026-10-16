#!/usr/bin/env python3
"""배포 차분 — 원본 → 최종 이미지의 xdelta·BPS 를 `work/dist/` 에 만들고 적용 왕복을 검증한다.

  python3 tools/make_dist.py [버전]        # 기본 v1.0.0 → ps1-ed1+2-kr-v1.0.0.xdelta / .bps
  python3 tools/make_dist.py v1.1.0 --from v1.0.0 <이전.xdelta> [이전 sha1]
      # 사슬 배포(마스터 10-11) — 위 원본→새 버전에 더해 직전→새 버전
      # ps1-ed1+2-kr-v1.0.0-to-v1.1.0.xdelta / .bps 를 만든다. 직전 이미지는 이전 패치를
      # 원본에 적용해 되살리고(sha1 을 주면 대조), 그 위로 왕복 검증한다.

⚠ 파일 이름에 공백을 두지 않는다 — GitHub 릴리스가 공백을 점으로 바꾼다.
⚠ 만든 직후 **원본에 각각 적용해 결과 sha1 이 빌드 이미지와 같은지** 확인한다(다르면 실패).
BPS 는 이미지가 제자리 갱신(섹터 단위)이라 같은 오프셋 비교로 충분하다 — 크기가 다르면 멈춘다.
"""

import os
import subprocess
import sys
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import BUILD_DIR, DIST_DIR, ORIG_BIN, digests

FINAL = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
MIN_EQ = 4  # 이보다 짧은 동일 구간은 TargetRead 에 흡수


def _varint(x: int) -> bytes:
    out = bytearray()
    while True:
        x7 = x & 0x7F
        x >>= 7
        if x == 0:
            out.append(0x80 | x7)
            return bytes(out)
        out.append(x7)
        x -= 1


def make_bps(src: bytes, tgt: bytes) -> bytes:
    if len(src) != len(tgt):
        raise SystemExit(
            f"크기가 다르다({len(src)} ≠ {len(tgt)}) — 제자리 BPS 인코더로는 못 만든다"
        )
    a = np.frombuffer(src, np.uint8)
    b = np.frombuffer(tgt, np.uint8)
    diff = a != b
    # 런 경계
    edges = np.flatnonzero(np.diff(diff.astype(np.int8))) + 1
    starts = np.concatenate(([0], edges))
    ends = np.concatenate((edges, [len(a)]))
    runs = [(int(s), int(e), bool(diff[s])) for s, e in zip(starts, ends, strict=True)]
    # 짧은 동일 구간(앞뒤가 다른 구간)을 이웃 다른 구간에 합친다
    merged = []
    for s, e, d in runs:
        if (
            not d
            and e - s < MIN_EQ
            and merged
            and merged[-1][2]
            and s != 0
            and e != len(a)
            or d
            and merged
            and merged[-1][2]
        ):
            merged[-1] = (merged[-1][0], e, True)
        else:
            merged.append((s, e, d))
    out = bytearray(b"BPS1")
    out += _varint(len(src)) + _varint(len(tgt)) + _varint(0)
    for s, e, d in merged:
        n = e - s
        if d:
            out += _varint(((n - 1) << 2) | 1) + tgt[s:e]
        else:
            out += _varint(((n - 1) << 2) | 0)
    out += zlib.crc32(src).to_bytes(4, "little") + zlib.crc32(tgt).to_bytes(4, "little")
    out += zlib.crc32(bytes(out)).to_bytes(4, "little")
    return bytes(out)


def apply_bps(src: bytes, patch: bytes) -> bytes:
    """독립 검증용 적용기 — 인코더와 코드를 공유하지 않는다."""
    assert patch[:4] == b"BPS1"
    pos = 4

    def rd():
        nonlocal pos
        x, shift = 0, 1
        while True:
            c = patch[pos]
            pos += 1
            x += (c & 0x7F) * shift
            if c & 0x80:
                return x
            shift <<= 7
            x += shift

    ssz, tsz, msz = rd(), rd(), rd()
    pos += msz
    assert ssz == len(src)
    if zlib.crc32(patch[:-4]) != int.from_bytes(patch[-4:], "little"):
        raise SystemExit("BPS 패치 CRC 불일치")
    end = len(patch) - 12
    tgt = bytearray()
    while pos < end:
        v = rd()
        mode, n = v & 3, (v >> 2) + 1
        if mode == 0:
            tgt += src[len(tgt) : len(tgt) + n]
        elif mode == 1:
            tgt += patch[pos : pos + n]
            pos += n
        else:
            raise SystemExit("이 인코더는 SourceCopy/TargetCopy 를 안 쓴다")
    assert len(tgt) == tsz
    if zlib.crc32(src) != int.from_bytes(patch[-12:-8], "little"):
        raise SystemExit("원본 CRC 불일치")
    if zlib.crc32(bytes(tgt)) != int.from_bytes(patch[-8:-4], "little"):
        raise SystemExit("결과 CRC 불일치")
    return bytes(tgt)


def _read(p):
    with open(p, "rb") as f:
        return f.read()


def _write(p, b):
    with open(p, "wb") as f:
        f.write(b)


def _xdelta(src, tgt, out):
    """xdelta3 -e -9 -S none 으로 src → tgt 차분을 만들고 되풀어 tgt 와 sha1 이 같은지 본다."""
    subprocess.run(["xdelta3", "-e", "-9", "-S", "none", "-f", "-s", src, tgt, out], check=True)
    chk = out + ".check"
    subprocess.run(["xdelta3", "-d", "-f", "-s", src, out, chk], check=True)
    got = digests(chk)["sha1"]
    os.remove(chk)
    want = digests(tgt)["sha1"]
    assert got == want, f"xdelta 결과 sha1 불일치 {got} ≠ {want}"


def _pair(src_path, tgt_path, base):
    """src → tgt 의 xdelta·BPS 한 쌍 + 왕복 검증. 만든 두 파일 경로를 돌려준다."""
    want = digests(tgt_path)["sha1"]
    xd = base + ".xdelta"
    _xdelta(src_path, tgt_path, xd)
    src, tgt = _read(src_path), _read(tgt_path)
    bps = base + ".bps"
    p = make_bps(src, tgt)
    _write(bps, p)
    got = digests_bytes(apply_bps(src, p))
    assert got == want, f"BPS 결과 sha1 불일치 {got} ≠ {want}"
    for f in (xd, bps):
        print(f"{os.path.basename(f)}  {os.path.getsize(f):,} bytes")
    print(f"결과 sha1 {want} (xdelta·BPS 둘 다 적용해 일치 확인)")
    return xd, bps


def main(ver="v1.0.0", *rest):
    os.makedirs(DIST_DIR, exist_ok=True)
    _pair(ORIG_BIN, FINAL, os.path.join(DIST_DIR, f"ps1-ed1+2-kr-{ver}"))
    if not rest:
        return
    if rest[0] != "--from" or len(rest) < 3:
        raise SystemExit("사용법: make_dist.py <버전> --from <이전버전> <이전.xdelta> [이전 sha1]")
    prev_ver, prev_patch = rest[1], rest[2]
    prev_img = os.path.join(DIST_DIR, f"prev-{prev_ver}.bin")
    subprocess.run(["xdelta3", "-d", "-f", "-s", ORIG_BIN, prev_patch, prev_img], check=True)
    got = digests(prev_img)["sha1"]
    print(f"{prev_ver} 이미지 복원: {os.path.getsize(prev_img):,} bytes sha1 {got}")
    if len(rest) > 3 and not got.startswith(rest[3].rstrip(".…")):
        raise SystemExit(f"{prev_ver} 복원 sha1 불일치 {got} ≠ {rest[3]}")
    try:
        _pair(prev_img, FINAL, os.path.join(DIST_DIR, f"ps1-ed1+2-kr-{prev_ver}-to-{ver}"))
    finally:
        os.remove(prev_img)


def digests_bytes(b: bytes) -> str:
    import hashlib

    return hashlib.sha1(b).hexdigest()


if __name__ == "__main__":
    main(*sys.argv[1:])
