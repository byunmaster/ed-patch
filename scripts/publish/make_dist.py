#!/usr/bin/env python3
"""배포 차분(공용) — 원본 → 최종 롬/이미지의 xdelta·BPS 를 만들고 원본에 적용해 왕복 검증한다.

    .venv/bin/python scripts/publish/make_dist.py --orig <원본> --final <제품 롬> --name sfc-ed1-kr-v0.1.0 --out <폴더>
    python3 scripts/publish/make_dist.py ... --from-ver v0.1.0 --prev-patch <이전.xdelta> [--prev-sha <sha1>]
        # 사슬 배포 — 위에 더해 「직전 판 → 새 판」 한 쌍(<게임>-kr-v0.1.0-to-v0.2.0.*)

- 둘째 소비자가 생겨 PS1 `games/ps1-ed1+2/tools/make_dist.py` 에서 뽑았다(10-24 sfc-ed1 배포 점검 「make_dist 가 없다」).
  PS1 쪽은 배포판이라 그대로 둔다 — 새 게임은 이것을 쓴다.
- PS1 판과 달리 **크기가 달라도** BPS 를 만든다(카트리지 롬 확장). 원본보다 긴 꼬리는 TargetRead 로 싣는다.
- 만든 직후 **원본에 각각 적용해 결과 sha1 이 최종 롬과 같은지** 본다(다르면 실패) — BPS 적용기는 인코더와 코드를 공유하지 않는다.
- BPS 인코더가 numpy 를 쓴다 — 시스템 python3 엔 없을 수 있으니 `.venv/bin/python` 으로 돌린다(10-24 sfc-ed1 실측).
- 파일 이름에 공백을 두지 않는다 — GitHub 릴리스가 공백을 점으로 바꾼다. 끝에 SHA1SUMS 를 쓴다.
"""

import argparse
import hashlib
import os
import subprocess
import zlib

MIN_EQ = 4  # 이보다 짧은 동일 구간(앞뒤가 다른 구간)은 TargetRead 에 흡수


def sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


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
    """SourceRead(같은 오프셋 동일) · TargetRead(그 밖) 두 명령만 쓰는 BPS. 크기가 달라도 된다."""
    import numpy as np

    n_cmp = min(len(src), len(tgt))
    runs = []  # (시작, 끝, 다름?)
    if n_cmp:
        diff = np.frombuffer(src, np.uint8, n_cmp) != np.frombuffer(tgt, np.uint8, n_cmp)
        edges = np.flatnonzero(np.diff(diff.astype(np.int8))) + 1
        starts = np.concatenate(([0], edges))
        ends = np.concatenate((edges, [n_cmp]))
        runs = [(int(a), int(b), bool(diff[a])) for a, b in zip(starts, ends, strict=True)]
    if len(tgt) > n_cmp:
        runs.append((n_cmp, len(tgt), True))  # 원본보다 긴 꼬리
    merged = []
    for s, e, d in runs:
        short_eq = not d and e - s < MIN_EQ and merged and merged[-1][2] and e != len(tgt)
        if (d or short_eq) and merged and merged[-1][2]:
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
    """독립 검증용 적용기 — 인코더와 코드를 공유하지 않는다(네 명령 전부 해석)."""
    if patch[:4] != b"BPS1":
        raise SystemExit("BPS 머리 아님")
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
    if ssz != len(src):
        raise SystemExit(f"원본 크기 불일치 {ssz} ≠ {len(src)}")
    if zlib.crc32(patch[:-4]) != int.from_bytes(patch[-4:], "little"):
        raise SystemExit("BPS 패치 CRC 불일치")
    end = len(patch) - 12
    tgt = bytearray()
    s_rel = t_rel = 0
    while pos < end:
        v = rd()
        mode, n = v & 3, (v >> 2) + 1
        if mode == 0:
            tgt += src[len(tgt) : len(tgt) + n]
        elif mode == 1:
            tgt += patch[pos : pos + n]
            pos += n
        else:
            off = rd()
            off = -(off >> 1) if off & 1 else off >> 1
            if mode == 2:
                s_rel += off
                tgt += src[s_rel : s_rel + n]
                s_rel += n
            else:
                t_rel += off
                for _ in range(n):
                    tgt.append(tgt[t_rel])
                    t_rel += 1
    if len(tgt) != tsz:
        raise SystemExit(f"결과 크기 불일치 {len(tgt)} ≠ {tsz}")
    if zlib.crc32(src) != int.from_bytes(patch[-12:-8], "little"):
        raise SystemExit("원본 CRC 불일치")
    if zlib.crc32(bytes(tgt)) != int.from_bytes(patch[-8:-4], "little"):
        raise SystemExit("결과 CRC 불일치")
    return bytes(tgt)


def _read(p):
    with open(p, "rb") as f:
        return f.read()


def _xdelta(src, tgt, out):
    subprocess.run(["xdelta3", "-e", "-9", "-S", "none", "-f", "-s", src, tgt, out], check=True)
    chk = out + ".check"
    subprocess.run(["xdelta3", "-d", "-f", "-s", src, out, chk], check=True)
    got = sha1(_read(chk))
    os.remove(chk)
    want = sha1(_read(tgt))
    if got != want:
        raise SystemExit(f"xdelta 결과 sha1 불일치 {got} ≠ {want}")


def pair(src_path, tgt_path, base):
    """src → tgt 의 xdelta·BPS 한 쌍 + 왕복 검증. 만든 두 파일 경로를 돌려준다."""
    xd, bps = base + ".xdelta", base + ".bps"
    _xdelta(src_path, tgt_path, xd)
    src, tgt = _read(src_path), _read(tgt_path)
    p = make_bps(src, tgt)
    with open(bps, "wb") as f:
        f.write(p)
    got, want = sha1(apply_bps(src, p)), sha1(tgt)
    if got != want:
        raise SystemExit(f"BPS 결과 sha1 불일치 {got} ≠ {want}")
    for f in (xd, bps):
        print(f"{os.path.basename(f)}  {os.path.getsize(f):,} bytes")
    print(f"결과 sha1 {want} (xdelta·BPS 둘 다 원본에 적용해 일치 확인)")
    return xd, bps


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", required=True)
    ap.add_argument("--final", required=True)
    ap.add_argument("--name", required=True, help="예: sfc-ed1-kr-v0.1.0")
    ap.add_argument("--out", required=True)
    ap.add_argument("--from-ver")
    ap.add_argument("--prev-patch")
    ap.add_argument("--prev-sha")
    a = ap.parse_args(argv)
    if " " in a.name:
        raise SystemExit("이름에 공백 금지(GitHub 릴리스가 점으로 바꾼다)")
    os.makedirs(a.out, exist_ok=True)
    made = list(pair(a.orig, a.final, os.path.join(a.out, a.name)))
    if a.from_ver:
        if not a.prev_patch:
            raise SystemExit("--from-ver 에는 --prev-patch 가 필요하다")
        prev_img = os.path.join(a.out, f"prev-{a.from_ver}.img")
        subprocess.run(["xdelta3", "-d", "-f", "-s", a.orig, a.prev_patch, prev_img], check=True)
        got = sha1(_read(prev_img))
        print(f"{a.from_ver} 이미지 복원 sha1 {got}")
        if a.prev_sha and not got.startswith(a.prev_sha.rstrip(".…")):
            os.remove(prev_img)
            raise SystemExit(f"{a.from_ver} 복원 sha1 불일치 {got} ≠ {a.prev_sha}")
        game, _, ver = a.name.rpartition("-v")
        try:
            made += pair(prev_img, a.final, os.path.join(a.out, f"{game}-{a.from_ver}-to-v{ver}"))
        finally:
            os.remove(prev_img)
    with open(os.path.join(a.out, "SHA1SUMS"), "w") as f:
        f.writelines(f"{sha1(_read(p))}  {os.path.basename(p)}\n" for p in made)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
