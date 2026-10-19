"""「완성 미증명」 대사 캡처를 **두 번 찍어 글자 마스크를 비교**한다(ss-ed1+2 방식, 관리자 10-20).

  python3 tools/dialog_verify.py --map <맵> --rows <index.tsv> --ks 0,3,7 --out <폴더> [--cue …] [--state …]

그 맵으로 이동해 시퀀스를 하나씩 주입하고, 하네스와 같은 기준으로 멎은 뒤 한 번(A), 60프레임 더 두고 한 번(B) 찍는다.
**글자 마스크**(글자색 흰·화자색 주황 픽셀만, 오른쪽 24px(대기 커서 ▽)와 배경 제외)가 A·B 에서 같으면 「완성」이다.
산출: `<out>/<맵>.tsv` — `맵 · 번호 · 차이(A·B 마스크 다른 픽셀 수) · 글자수(A 마스크 픽셀)` , A 그림은 `<out>/<맵>/NNN.png`.
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dialog_harness as D
import headless_ps1 as H


FRAME = [(98, 16, 0), (172, 97, 49), (238, 170, 98), (8, 0, 0), (66, 8, 0)]


def windows(frame):
    """창 틀(위·아래 띠)로 창을 찾는다 — 배경 움직임에 흔들리는 `band()` 대신. [(위 띠 시작, 아래 띠 끝+1)] 목록(위에서 아래로)."""
    m = np.zeros(frame.shape[:2], bool)
    for c in FRAME:
        m |= (frame == np.array(c)).all(axis=2)
    rows = m.sum(axis=1) >= 200
    groups, cur = [], None
    for y, on in enumerate(list(rows) + [False]):
        if on and cur is None:
            cur = y
        elif not on and cur is not None:
            groups.append((cur, y))
            cur = None
    # 띠 사이에 틈(글 영역)이 ≥12행 있으면 한 창: 위 띠 묶음 끝 .. 아래 띠 묶음 시작
    merged = []
    for g in groups:
        if merged and g[0] - merged[-1][1] <= 3:
            merged[-1] = (merged[-1][0], g[1])
        else:
            merged.append(g)
    return [(merged[i][0], merged[i + 1][1], merged[i][1], merged[i + 1][0]) for i in range(0, len(merged) - 1, 2) if merged[i + 1][0] - merged[i][1] >= 12]


def pick(base, frame):
    """주입 전 화면과 가장 많이 달라진 창(없으면 None)."""
    best, bd = None, 0
    for w in windows(frame):
        t, bt = w[0], w[1]
        d = int(np.abs(base[t:bt].astype(int) - frame[t:bt].astype(int)).sum())
        if d > bd:
            best, bd = w, d
    return best


def mask(frame, b):
    """글자색 픽셀 — 흰(보통 글)·주황(화자 이름)·초록(지문·시스템 글, 10-20 FT3004 가 놓친 색)."""
    f = frame[b[2] : b[3], 10:-24].astype(int)
    white = f.min(axis=2) >= 200
    orange = (f[..., 0] >= 200) & (f[..., 1] >= 100) & (f[..., 1] <= 190) & (f[..., 2] <= 90)
    green = (f[..., 1] >= 180) & (f[..., 0] <= 150) & (f[..., 2] <= 150)
    return white | orange | green


def wait_text(emu, base, cap=1500):
    """창이 열린 뒤 **글자 픽셀이 처음 나타날 때까지** 기다리고, 그 뒤 30프레임 연속 같아질 때까지. 글자가 안 나오면 (None, 0)."""
    seen, same, last = False, 0, None
    for i in range(cap):
        emu.run(1)
        b = pick(base, emu.frame) if i >= 5 else None
        if b is None:
            same, last = 0, None
            continue
        m = mask(emu.frame, b)
        if not seen:
            if m.sum() < 4:
                continue
            seen = True
        cur = m.tobytes()
        same = same + 1 if cur == last else 0
        last = cur
        if same >= 30:
            return b, int(m.sum())
    return (pick(base, emu.frame), 0) if not seen else (None, -1)


def growth(ma, mb):
    """B 에만 있는 글자색 픽셀 가운데 **A 글자 줄의 오른쪽 끝 너머**나 **A 의 마지막 글자 줄 아래**에 생긴 것의 수 — 글이 더 찍혔다는 증거."""
    new = mb & ~ma
    rowsA = np.where(ma.sum(axis=1) >= 2)[0]
    if not len(rowsA):
        return int(new.sum())
    n = 0
    for y in range(ma.shape[0]):
        if y > rowsA[-1]:
            n += int(new[y].sum())
        elif y in set(rowsA):
            xs = np.where(ma[y])[0]
            n += int(new[y, xs.max() + 3 :].sum())
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--rows", required=True)
    ap.add_argument("--ks", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=D.DEFAULT_CUE)
    ap.add_argument("--state")
    a = ap.parse_args()
    ks = {int(x) for x in a.ks.split(",")}
    seqs = {}
    for ln in open(a.rows, encoding="utf-8").read().splitlines()[1:]:
        c = ln.split("\t")
        if c[0] == a.map and int(c[1]) in ks:
            seqs[int(c[1])] = bytes.fromhex(c[3])
    from warp_table import table

    ch = {n: c for n, c, _p, _a in table("ed3")}[a.map][0]
    emu = H.Emu(a.cue)
    D.boot(emu, a.state, a.cue)
    D.jump(emu, a.map, ch, 0)
    os.makedirs(os.path.join(a.out, a.map), exist_ok=True)
    snap = os.path.join(a.out, a.map, "_s.state")
    emu.save(snap)
    rows = []
    for k in sorted(seqs):
        emu.load(snap)
        emu.run(2)
        base = emu.frame.copy()
        D.inject(emu, seqs[k])
        b, n = wait_text(emu, base)
        if b is None or n <= 0:
            Image.fromarray(np.ascontiguousarray(emu.frame)).save(os.path.join(a.out, a.map, f"{k:03d}x.png"))  # 실패 쪽도 전체 화면을 남긴다
            rows.append((a.map, k, -3 if n == 0 else -1, 0, 0, ""))  # -3 = 창은 열렸는데 글자색 픽셀이 없음(지도 이름 조각 등) · -1 = 창 없음/안 멎음
            continue
        ma = mask(emu.frame, b)
        Image.fromarray(np.ascontiguousarray(emu.frame[b[0] : b[1]])).save(os.path.join(a.out, a.map, f"{k:03d}.png"))
        emu.run(60)
        b2 = pick(base, emu.frame)
        # 띠가 흔들려도 A 의 띠를 기준으로 고정해 비교한다(증분 재측정 — 관리자 10-20)
        mb = mask(emu.frame, b)
        Image.fromarray(np.ascontiguousarray(emu.frame[b[0] : b[1]])).save(os.path.join(a.out, a.map, f"{k:03d}b.png"))
        rows.append((a.map, k, int((ma != mb).sum()), int(ma.sum()), growth(ma, mb), "" if b2 == b else "띠변함"))
    os.remove(snap)
    with open(os.path.join(a.out, a.map + ".tsv"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write("\t".join(map(str, r)) + "\n")


if __name__ == "__main__":
    main()
