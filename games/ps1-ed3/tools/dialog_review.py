"""대사 캡처 자동 1차 검수 — 하네스 캡처(`NNN.png`)와 줄 열쇠 색인(`labels.tsv`)으로 **화면에서만 보이는 결함 후보**를 가른다.

  python3 tools/dialog_review.py --dir <챕터 폴더> --labels <labels.tsv> [--out issues.tsv]

후보 사유: `창없음`·`미정지`(하네스 비고) · `잡음`(잉크 밀도가 글이라 하기엔 높다 = 데이터 조각을 대사로 읽은 것) · `줄많음`(본문이 4줄을 넘는다) · `빈창`(글이 없다).
⚠ 후보일 뿐이다 — 사람이 보고 가른다(잡음 부류는 대사가 아닌 조각이라 결함이 아니다).
"""

import argparse
import os
import pathlib
import sys

import numpy as np
from PIL import Image


def ink(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    white = a.min(axis=2) > 150
    orange = (a[:, :, 0] > 200) & (a[:, :, 1] > 100) & (a[:, :, 2] < 80)
    return white | orange


def runs(mask1d, gap=2):
    out, start, miss = [], None, 0
    for y, on in enumerate(list(mask1d) + [False] * (gap + 1)):
        if on:
            if start is None:
                start = y
            miss = 0
        elif start is not None:
            miss += 1
            if miss > gap:
                out.append((start, y - miss))
                start = None
    return out


def review(path, kr_lines):
    """[(사유…)] — 한 장."""
    im = Image.open(path)
    m = ink(im)
    _h, w = m.shape
    inner = m[:, 16 : w - 16]
    why = []
    if inner.mean() > 0.30:
        return ["잡음"]
    rows = runs(inner.sum(axis=1) > 2)
    rows = [r for r in rows if r[1] - r[0] >= 2]
    # 이름 줄은 주황, 본문은 흰색 — 본문 줄만 센다(이름 한 줄 + 본문 최대 4줄)
    a = np.asarray(im.convert("RGB")).astype(int)[:, 16 : w - 16]
    orange = (a[:, :, 0] > 200) & (a[:, :, 1] > 100) & (a[:, :, 2] < 80)
    rows = [r for r in rows if orange[r[0] : r[1] + 1].sum() < 0.5 * inner[r[0] : r[1] + 1].sum()]
    white = (np.asarray(im.convert("RGB")).astype(int).min(axis=2) > 150)[:, 16 : w - 16].sum()
    if not rows or white < 12:
        return ["빈창"]
    if len(rows) > 4:
        why.append("줄많음")
    return why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--index")
    ap.add_argument("--out")
    a = ap.parse_args()
    lab = {}
    for ln in pathlib.Path(a.labels).read_text(encoding="utf-8").splitlines()[1:]:
        c = ln.split("\t")
        lab[(c[0], int(c[1]))] = c[2:]
    notes = {}
    if a.index:
        for ln in pathlib.Path(a.index).read_text(encoding="utf-8").splitlines()[1:]:
            c = ln.split("\t")
            notes[(c[0], int(c[1]))] = [x for x in c[4:6] if x]
    out = []
    for (name, k), (key, first) in sorted(lab.items()):
        if key == "?":
            continue  # 줄 열쇠가 없다 = 대사가 아닌 조각(스크립트 밖에서 우연히 맞은 `0F 90`)
        p = os.path.join(a.dir, name, f"{k:03d}.png")
        if not os.path.exists(p):
            continue
        why = list(notes.get((name, k), [])) + review(p, 0)
        if why:
            out.append((name, k, key, ",".join(why), first))
    text = "".join("\t".join(map(str, r)) + "\n" for r in out)
    if a.out:
        pathlib.Path(a.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    print(f"후보 {len(out)}/{len(lab)}", file=sys.stderr)


if __name__ == "__main__":
    main()
