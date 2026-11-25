#!/usr/bin/env python3
"""배포 차분 — 원본 → 최종 이미지의 xdelta·BPS 를 `work/dist/` 에 만들고 적용 왕복을 검증한다.

  python3 tools/make_dist.py [버전]        # 기본 v0.1.0 → ps1-ed4-kr-v0.1.0.xdelta / .bps

⚠ 파일 이름에 공백을 두지 않는다 — GitHub 릴리스가 공백을 점으로 바꾼다.
⚠ 만든 직후 **원본에 각각 적용해 결과 sha1 이 빌드 이미지와 같은지** 확인한다(다르면 실패).
이 게임은 빌드 이미지가 원본보다 길다(섹터가 늘어난다) — BPS 는 같은 오프셋을 비교하고 **늘어난 꼬리는 TargetRead** 로 싣는다.
ps1-ed1+2 의 make_dist 를 본으로 했다(이 폴더는 독립 코드베이스라 import 하지 않는다 — 규약은 같고 이미지 크기만 다르다).
"""

import hashlib
import os
import subprocess
import sys
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

FINAL = common.build_bin()
MIN_EQ = 4  # 이보다 짧은 동일 구간은 TargetRead 에 흡수


def digests(path):
    """크기와 체크섬 넷 — 받는 사람이 손에 든 도구가 달라서 넷을 다 적는다."""
    crc, h = 0, {k: hashlib.new(k) for k in ("md5", "sha1", "sha256")}
    size = 0
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            size += len(chunk)
            crc = zlib.crc32(chunk, crc)
            for x in h.values():
                x.update(chunk)
    return {"size": size, "crc32": f"{crc:08X}", **{k: v.hexdigest() for k, v in h.items()}}


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
    """같은 오프셋 비교 BPS — 공통 앞부분은 SourceRead/TargetRead 런, 타깃이 더 길면 꼬리는 TargetRead."""
    n = min(len(src), len(tgt))
    a = np.frombuffer(src, np.uint8)[:n]
    b = np.frombuffer(tgt, np.uint8)[:n]
    diff = a != b
    edges = np.flatnonzero(np.diff(diff.astype(np.int8))) + 1
    starts = np.concatenate(([0], edges))
    ends = np.concatenate((edges, [n]))
    runs = [(int(s), int(e), bool(diff[s])) for s, e in zip(starts, ends, strict=True)]
    merged = []
    for s, e, d in runs:
        if not d and e - s < MIN_EQ and merged and merged[-1][2] and s != 0 and e != n:
            merged[-1] = (merged[-1][0], e, True)
        elif d and merged and merged[-1][2]:
            merged[-1] = (merged[-1][0], e, True)
        else:
            merged.append((s, e, d))
    if len(tgt) > n:  # 늘어난 꼬리 — 마지막 런이 TargetRead 면 잇는다
        if merged and merged[-1][2]:
            merged[-1] = (merged[-1][0], len(tgt), True)
        else:
            merged.append((n, len(tgt), True))
    out = bytearray(b"BPS1")
    out += _varint(len(src)) + _varint(len(tgt)) + _varint(0)
    for s, e, d in merged:
        k = e - s
        if d:
            out += _varint(((k - 1) << 2) | 1) + tgt[s:e]
        else:
            out += _varint(((k - 1) << 2) | 0)
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


def main(ver="v0.1.0"):
    os.makedirs(common.DIST_DIR, exist_ok=True)
    src_path, tgt_path = common.orig_bin(), FINAL
    base = os.path.join(common.DIST_DIR, f"ps1-ed4-kr-{ver}")
    want = digests(tgt_path)["sha1"]
    xd, bps = base + ".xdelta", base + ".bps"
    _xdelta(src_path, tgt_path, xd)
    src, tgt = _read(src_path), _read(tgt_path)
    p = make_bps(src, tgt)
    _write(bps, p)
    got = hashlib.sha1(apply_bps(src, p)).hexdigest()
    assert got == want, f"BPS 결과 sha1 불일치 {got} ≠ {want}"
    for f in (xd, bps):
        print(f"{os.path.basename(f)}  {os.path.getsize(f):,} bytes")
    print(f"결과 sha1 {want} (xdelta·BPS 둘 다 적용해 일치 확인)")


if __name__ == "__main__":
    main(*sys.argv[1:])
