#!/usr/bin/env python3
"""배포 파일(work/dist)이 제품 롬보다 낡았나 — 알림만(마스터 11-06 「낡은 롬 막는 장치」).

왜: 문안을 한 줄 고치면 제품 롬은 다시 구워지는데 배포 차분(xdelta·BPS)은 손으로 다시 만들어야 한다.
11-06 하루에 대구 쉼표·「헤에～」가 열 게임에 동시에 들어가며 dist 가 하나씩 낡아졌고, 「대기 = 배포 가능」으로
읽힐 뻔했다. 형식(SHA1SUMS·manifest·RELEASE_NOTES)이 게임마다 달라 **BPS 꼬리의 대상 CRC32** 로 본다 — 제품 빌드 칸
(`test-*`·`*.failed` 제외, 가장 최근 칸)의 이미지 CRC 와 맞는 BPS 가 work/dist 나 .local/ship/release/<게임>-* 에
없으면 알린다. 시각으로 재면 게이트가 매번 다시 굽는 탓에 늘 낡음으로 나와 쓸모가 없다.

  python3 scripts/check/check_stale_dist.py --game pce-ed1

항상 0 으로 끝난다(알림).
"""

import argparse
import glob
import os
import struct
import subprocess
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKIP_EXT = (".cue", ".ccd", ".txt", ".json", ".md", ".log", ".state", ".sav", ".png")


def main_tree():
    """워크트리면 메인 트리 — .local 은 메인 트리에만 있다."""
    try:
        c = subprocess.run(
            ["git", "-C", ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return os.path.dirname(c)
    except (OSError, subprocess.CalledProcessError):
        return ROOT


def bps_target_crc(path):
    """BPS 꼬리 12바이트 = 원본 CRC32 · 대상 CRC32 · 패치 CRC32(작은 끝)."""
    with open(path, "rb") as f:
        f.seek(-12, 2)
        _, tgt, _ = struct.unpack("<III", f.read(12))
    return tgt


def crc32(path):
    c = 0
    with open(path, "rb") as f:
        while b := f.read(1 << 22):
            c = zlib.crc32(b, c)
    return c & 0xFFFFFFFF


def product_dir(build, game):
    """제품 빌드 칸 — 게임 이름 칸(`+`→`-` 꼴 포함)이 있으면 그것, 없으면 `test-*`·실패·원판 사본(`orig`)을
    뺀 칸 중 가장 최근에 구운 것(sfc-ed2 는 하네스용 원판 사본 `orig` 칸이 더 새로워 그쪽을 집었다)."""
    for n in (game, game.replace("+", "-")):
        if os.path.isdir(os.path.join(build, n)):
            return os.path.join(build, n)
    best = None
    for d in glob.glob(os.path.join(build, "*")):
        n = os.path.basename(d)
        if n.startswith("test-") or n.endswith(".failed") or n == "orig" or not os.path.isdir(d):
            continue
        t = os.path.getmtime(d)
        if best is None or t > best[0]:
            best = (t, d)
    return best and best[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    g = ap.parse_args().game
    build = os.path.join(ROOT, "games", g, "work", "build")
    pd = product_dir(build, g) if os.path.isdir(build) else None
    if not pd:
        print(f"⏭ [{g}] 제품 빌드 칸 없음 — 배포 파일 신선도 안 잼")
        return 0
    imgs = [
        p
        for p in glob.glob(os.path.join(pd, "**", "*"), recursive=True)
        if os.path.isfile(p)
        and not p.lower().endswith(SKIP_EXT)
        and os.path.getsize(p) >= 64 * 1024
    ]
    # 배포 패치 — 게임 work/dist 와 메인 트리 .local/ship/release/<게임>-* 둘 다. 판 사이 차분(-to-)은 뺀다.
    pats = glob.glob(os.path.join(ROOT, "games", g, "work", "dist", "**", "*.bps"), recursive=True)
    pats += glob.glob(os.path.join(main_tree(), ".local", "ship", "release", f"{g}-*", "*.bps"))
    pats = [p for p in pats if "-to-" not in os.path.basename(p)]
    if not imgs:
        print(f"⏭ [{g}] 제품 이미지 없음({os.path.basename(pd)}) — 배포 파일 신선도 안 잼")
        return 0
    if not pats:
        print(f"⚠ [{g}] 배포 BPS 없음 — work/dist · .local/ship/release/{g}-* 어디에도")
        return 0
    want = {crc32(p): p for p in imgs}
    hit = [p for p in pats if bps_target_crc(p) in want]
    rel = lambda p: os.path.relpath(p, main_tree()) if ".local" in p else os.path.relpath(p, ROOT)
    if hit:
        print(
            f"✅ [{g}] 배포 파일 = 제품 롬({os.path.basename(pd)}) — {', '.join(rel(p) for p in hit)}"
        )
    else:
        newest = max(pats, key=os.path.getmtime)
        print(
            f"⚠ [{g}] 배포 파일이 지금 제품 롬({os.path.basename(pd)})과 다르다 — "
            f"BPS 대상 CRC 불일치(가장 새 것 {rel(newest)}) · make_dist 다시"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
