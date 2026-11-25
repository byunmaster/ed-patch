"""글자 없는 쪽 세기 — 촬영 폴더의 PNG 중 대사 창 안쪽 글자 잉크(흰색·노란 이름색)가 6px 미만인 장.

    .venv/bin/python games/sfc-ed1/tools/blank_pages.py <폴더 또는 glob> [--list]

대사 보기(`lua/msg_viewer.lua`)가 찍는 256×224 화면의 창 영역(y 14..100 × x 10..156)만 본다. 검은 화면 검사로는 안 잡히는 **빈 창**
(문맥 없는 호출 단위·타이밍으로 글자가 아직 안 찍힌 쪽 — devlog 「글자 없는 쪽」 574장)을 manifest 의 「글자 없는 쪽 수」로 센다.
원판도 같은 빈 창이면 롬 결함은 아니고 그 단위를 다시 찍는다(md-ed1·ss-ed3 도구와 같은 규약).
"""

import argparse
import glob
import os

import numpy as np
from PIL import Image

BOX = (14, 100, 10, 156)  # y0, y1, x0, x1


def ink(path: str) -> int:
    y0, y1, x0, x1 = BOX
    a = np.array(Image.open(path).convert("RGB")).astype(int)[y0:y1, x0:x1]
    white = a.min(axis=2) >= 200
    yellow = (a[:, :, 0] >= 200) & (a[:, :, 1] >= 150) & (a[:, :, 2] < 130)
    return int((white | yellow).sum())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    pat = a.pattern if any(c in a.pattern for c in "*?[") else os.path.join(a.pattern, "**", "*.png")
    fs = sorted(f for f in glob.glob(pat, recursive=True) if "/sheet_" not in f and "zoom" not in f)
    blank = [f for f in fs if ink(f) < 6]
    print(f"{len(fs)}장 중 글자 없는 쪽 {len(blank)}장")
    if a.list:
        print("\n".join(blank))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
