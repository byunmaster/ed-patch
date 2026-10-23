#!/usr/bin/env python3
"""**글자 없는 쪽** 계수 — 촬영 묶음 폴더의 캡처에서 대사 창 안쪽 글자 잉크가 6px 미만인 장을 센다(manifest 의 「글자 없는 쪽 수」 열).

    python3 tools/empty_pages.py <묶음 폴더> --kind scene|battle

🔴 **잉크는 색을 안 가린다** — 창 바탕(가장 흔한 색)과 다른 밝은 픽셀이면 글자다. 흰·노랑만 세면 초록 서술(ED1 지문)·하늘색이 「빈 창」으로 잡힌다(실측 2026-10-20 22장 오탐).
이름·아이템 변수로 시작하는 대사는 변수 버퍼가 비면 창이 통째로 비어 찍힌다(sfc-ed2 실측 · 원판도 같음) — 그 단위를 가리는 데 쓴다(검은 화면 검사는 이런 빈 창을 못 잡는다).
"""

import argparse
import glob
import os

import numpy as np
from PIL import Image

BOX = {"scene": (20, 98, 20, 200), "battle": (152, 226, 20, 200)}  # 대사 창(위) · 전투 메시지 창(아래) 안쪽


def ink(path, box):
    a = np.array(Image.open(path).convert("RGB")).astype(int)
    y0, y1, x0, x1 = box
    c = a[y0:y1, x0:x1]
    vals, cnt = np.unique(c.reshape(-1, 3), axis=0, return_counts=True)
    bg = vals[cnt.argmax()]
    return int(((np.abs(c - bg).sum(2) > 150) & (c.max(2) > 120)).sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--kind", choices=sorted(BOX), required=True)
    a = ap.parse_args()
    fs = [f for f in glob.glob(os.path.join(a.folder, "**", "*.png"), recursive=True) if not os.path.basename(f).startswith(("sheet", "menu", "list"))]
    empty = [f for f in fs if ink(f, BOX[a.kind]) < 6]
    print(f"캡처 {len(fs)}장 · 글자 없는 쪽 {len(empty)}장")
    for f in empty:
        print("  ", os.path.relpath(f, a.folder))


if __name__ == "__main__":
    main()
