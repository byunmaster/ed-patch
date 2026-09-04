"""오프닝·엔딩 내레이션 그림을 **글자부터 그린다** (ED3).

    python3 tools/narration.py --list     # 자리와 규격
    python3 tools/narration.py --check    # 줄이 칸을 넘나 · 커밋된 PNG 와 같나
    python3 tools/narration.py            # 굽는다 → assets/graphics/ed3/

원본이 **1비트 순백**이라(색 1개) 팔레트 고민이 없다 — 같은 자리에 같은 크기로 다시 찍으면
그만이다. 정본은 `narration_ed3.json`(우리 한국어만 — 원문은 `work/review/` 에만 둔다).

## 🔴 두루마리는 **글 하나에 창 둘**이다

`DATA2_3`↔`4`, `DATA2_6`↔`7` 은 **272px 어긋난 같은 글**이다(일치율 99.99%/100% 실측).
긴 글 하나를 512px 창 둘로 오려 낸 것 ⇒ **글은 한 번 그리고 창을 둘 오린다.**
따로 그리면 이음매에서 어긋난다.

## ⚠ 폰트는 자리마다 다르다 — 원본 잉크 높이에 맞춘다

| 자리 | 원본 잉크 | 우리 |
| --- | --- | --- |
| 두루마리 `DATA2_*` | 11px | **Galmuri11**(11, 정확) |
| 카드 `DATA3_0·1` | 13px | **neodgm 16**(13, 정확) |
| 엔딩 `ENDDATA1_*` | 17px | **neodgm 16**(13) — 17은 제 크기가 없다 |

🔴 **제 크기가 아닌 픽셀 폰트를 쓰지 않는다.** neodgm 21 은 잉크 17 로 딱 맞지만 계조가
105단이라 획이 무너진다(타이틀 버튼에서 14px 로 물렸다). 조금 작아도 온전한 쪽을 고른다.
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ),
        "shared",
    ),
)
import common
from fonts import galmuri

CANON = os.path.join(common.ROOT, "narration_ed3.json")
ASSETS = os.path.join(common.ROOT, "assets", "graphics", "ed3")
NEODGM = os.path.join(common.REPO, "shared", "fonts", "neodgm.ttf")


# ── 글자 찍기 ───────────────────────────────────────────────────────────────
def _ttf_line(txt, size):
    """(마스크, 폭) — neodgm 은 **제 크기(16px)** 로만 쓴다."""
    f = ImageFont.truetype(NEODGM, size)
    w = int(ImageDraw.Draw(Image.new("L", (8, 8))).textlength(txt, font=f)) + 4
    img = Image.new("L", (max(w, 8), size * 3), 0)
    ImageDraw.Draw(img).text((0, size // 2), txt, font=f, fill=255)
    m = np.asarray(img) > 100
    if not m.any():
        return np.zeros((1, 1), bool), 0
    xs = np.nonzero(m.any(axis=0))[0]
    return m[:, xs.min() : xs.max() + 1], int(xs.max() - xs.min() + 1)


def _bdf_line(txt, name):
    """BDF 는 도트가 파일에 박혀 있어 크기를 안 탄다 — 칸 폭(이름의 숫자)으로 흘린다."""
    f = galmuri(name)
    cell = int("".join(ch for ch in name if ch.isdigit()))
    cols = []
    for ch in txt:
        if ch == " ":
            cols.append(np.zeros((cell * 3, cell // 2 + 1), bool))
            continue
        if not f.has(ch):
            raise SystemExit(f"🔴 글리프 없음: {ch!r} ({name})")
        cols.append(f.bits(ch, dy=cell, rows=cell * 3, width=cell + 8)[:, :cell].astype(bool))
    m = np.concatenate(cols, axis=1) if cols else np.zeros((cell * 3, 1), bool)
    return m, m.shape[1]


def thicken_h(m):
    """**가로획만** 한 픽셀 굵힌다 (아래로).

    🔴 게임 오프닝은 **512×240 모드**라 픽셀이 가로로 절반이다 — 13×13 글자가 화면에선
       13 높이 × 6.5 폭으로 보이고, **1px 짜리 가로획이 먼저 뭉갠다**(「는」의 ㄴ, 실측).
       원본 일본어도 같은 조건이지만 한글은 획이 많아 먼저 드러난다.
    ⚠ 세로 기둥은 안 건드린다 — 좌우 이웃이 **둘 다** 있는 픽셀만 가로획으로 본다.
       2px 세로 기둥은 왼쪽 칸에 왼 이웃이 없어 걸리지 않는다.
    """
    left = np.zeros_like(m)
    right = np.zeros_like(m)
    left[:, 1:] = m[:, :-1]
    right[:, :-1] = m[:, 1:]
    horiz = m & left & right
    out = m.copy()
    out[1:] |= horiz[:-1]
    return out


def render_line(txt, font):
    if font.startswith("Galmuri"):
        return _bdf_line(txt, font)
    return _ttf_line(txt, int(font.split()[-1]))


def _ink_top(m):
    ys = np.nonzero(m.any(axis=1))[0]
    return int(ys.min()) if len(ys) else 0


def draw_block(lines, w, h, font, align, left, top, pitch, gap, bold_h=False):
    """줄들을 판에 앉힌다 — 빈 줄은 **문단 사이**(gap)로 친다."""
    out = np.zeros((h, w), bool)
    y, over = top, []
    for ln in lines:
        if not ln:
            y += gap - pitch
            continue
        m, wid = render_line(ln, font)
        if bold_h:
            m = thicken_h(m)
        m = m[_ink_top(m) :]
        x = (w - wid) // 2 if align == "center" else left
        if x < 0 or x + wid > w:
            over.append((ln, wid))
        hh = min(m.shape[0], h - y)
        if hh > 0:
            xs, xe = max(0, x), min(w, x + wid)
            out[y : y + hh, xs:xe] |= m[:hh, : xe - xs]
        y += pitch
    ys = np.nonzero(out.any(axis=1))[0]  # ⚠ 「쓴 높이」는 **잉크 바닥**이다 — 다음 줄 자리가 아니다
    return out, (int(ys.max()) + 1 if len(ys) else 0), over


# ── 굽기 ────────────────────────────────────────────────────────────────────
def load():
    with open(CANON, encoding="utf-8") as f:
        return json.load(f)


def build_group(g):
    """(파일이름 → RGBA 배열, 넘친 줄, 쓴 높이)."""
    canvas_h = g.get("canvas_h", g["h"])
    ink, used, over = draw_block(
        g["lines"],
        g["w"],
        canvas_h,
        g["font"],
        g["align"],
        g.get("left", 0),
        g["top"],
        g["pitch"],
        g["gap"],
        g.get("bold_h", False),
    )
    outs = {}
    for t in g["targets"]:
        off = t.get("offset", 0)
        win = ink[off : off + g["h"]]
        a = np.zeros((g["h"], g["w"], 4), np.uint8)
        a[win] = (255, 255, 255, 255)
        if g.get("opaque"):  # 두루마리는 배경이 검정으로 **칠해져** 있다
            a[..., 3] = 255
        outs[t["file"]] = a
    return outs, over, used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    doc = load()
    bad = 0
    for g in doc["groups"]:
        outs, over, used = build_group(g)
        room = g.get("canvas_h", g["h"])
        note = f"{g['name']:20} {g['font']:10} 줄 {sum(1 for x in g['lines'] if x):3} · 높이 {used}/{room}"
        if a.list:
            print(f"  {note} · {[t['file'] for t in g['targets']]}")
            continue
        if over or used > room:
            bad += 1
            print(f"  🔴 {note}")
            for ln, wid in over:
                print(f"       칸을 넘는다({wid}px + 왼쪽 {g.get('left', 0)} > {g['w']}): {ln}")
            if used > room:
                print(f"       줄이 판을 넘는다: {used} > {room}")
            continue
        for name, arr in outs.items():
            dst = os.path.join(ASSETS, name)
            if a.check:
                same = os.path.exists(dst) and np.array_equal(
                    arr, np.asarray(Image.open(dst).convert("RGBA"))
                )
                print(f"  {'✅' if same else '🔴'} {name:34} {note}")
                bad += not same
            else:
                Image.fromarray(arr, "RGBA").save(dst)
                print(f"  → {name:34} {note}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
