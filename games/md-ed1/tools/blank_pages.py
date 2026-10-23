"""글자 없는 쪽 세기 — 촬영 폴더의 PNG 중 창 안쪽 글자 잉크(흰색·노란 이름색)가 6px 미만인 장.

    python3 tools/blank_pages.py <폴더 또는 glob> [--kind dialog|battle] [--list]

kind=dialog(필드 대사: 창 없는 지도 위 글 148..206 × 48..290, 흰 잉크) · battle(전투 창 178..212 × 8..312, 흰+노란 이름색).
검은 화면 검사로는 안 잡히는 빈 창(이름·품목 변수 버퍼가 비어 변수로 시작하는 대사가 통째로 비는 부류 — sfc-ed2 10-20)을 manifest 의
「글자 없는 쪽 수」 열로 센다. 원판도 같은 빈 창이면 롬 결함은 아니고 그 단위를 대표값을 넣어 다시 찍는다.
"""

import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image

BOX = {"dialog": (148, 206, 48, 290), "battle": (178, 212, 8, 312)}


def ink(path: str, kind: str) -> int:
    y0, y1, x0, x1 = BOX[kind]
    a = np.array(Image.open(path).convert("RGB")).astype(int)[y0:y1, x0:x1]
    white = a.min(axis=2) >= (235 if kind == "dialog" else 200)
    if kind == "battle":
        white |= (a[:, :, 0] >= 200) & (a[:, :, 1] >= 150) & (a[:, :, 2] < 130)
    return int(white.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern")
    ap.add_argument("--kind", choices=BOX, default="dialog")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    pat = a.pattern if any(c in a.pattern for c in "*?[") else os.path.join(a.pattern, "**", "*.png")
    fs = [f for f in glob.glob(pat, recursive=True) if "field" not in os.path.basename(f)]
    blank = [f for f in fs if ink(f, a.kind) < 6]
    print(f"{len(fs)}장 중 글자 없는 쪽 {len(blank)}장")
    if a.list:
        print("\n".join(blank))
    return 0


if __name__ == "__main__":
    sys.exit(main())
