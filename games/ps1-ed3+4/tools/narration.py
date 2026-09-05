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
ELLIPSIS = {"…": 3, "‥": 2}  # 말줄임표는 **바닥에** 찍는다 (아래 `_dots`)


def _ttf_rows(size):
    return size * 3


def _ttf_text(txt, size):
    """(마스크, 폭) — neodgm 은 **제 크기(16px)** 로만 쓴다. 행 기하는 고정(size*3)."""
    f = ImageFont.truetype(NEODGM, size)
    w = int(ImageDraw.Draw(Image.new("L", (8, 8))).textlength(txt, font=f)) + 4
    img = Image.new("L", (max(w, 8), _ttf_rows(size)), 0)
    ImageDraw.Draw(img).text((0, size // 2), txt, font=f, fill=255)
    m = np.asarray(img) > 100
    if not m.any():
        return np.zeros((_ttf_rows(size), max(1, int(w))), bool), max(1, int(w))
    xs = np.nonzero(m.any(axis=0))[0]
    return m[:, xs.min() : xs.max() + 1], int(xs.max() - xs.min() + 1)


def _baseline(font):
    """말줄임표를 앉힐 줄 — **온점(`.`)의 아랫줄**이다.

    ⚠ 「가」의 아랫줄이 아니다 — neodgm 은 받침이 온점보다 2줄 더 내려간다(실측).
       그걸 기준으로 삼으면 점이 바닥 **아래로** 빠진다.
    """
    if font.startswith("Galmuri"):
        f = galmuri(font)
        cell = _cell(font)
        b = f.bits(".", dy=cell, rows=cell * 3, width=cell + 8)
        return int(np.nonzero(b.any(axis=1))[0].max())
    m, _ = _ttf_text(".", int(font.split()[-1]))
    return int(np.nonzero(m.any(axis=1))[0].max())


def _cell(font):
    if font.startswith("Galmuri"):
        return int("".join(c for c in font if c.isdigit()))
    return int(font.split()[-1])


def _dots(chars, font):
    """말줄임표를 **직접 찍는다** — 이어진 말줄임표 전체를 한 판에, 점 간격을 **일정하게**.

    🔴 폰트의 `…` 는 **글자 가운데 높이**에 있다(일본식). 한국어는 바닥이다.
       Galmuri11 실측: `…` 은 바닥에서 5줄 위, `.` 은 바닥.
    🔴 칸마다 따로 찍으면 간격이 어긋난다 — 11px 칸에 점 셋을 `round(11·(k+½)/3)` 로 놓으면
       2·6·9 라 4·3, 다음 칸과는 4 — 「……」 여섯 점이 4·3·4·4·3(유저 지적 2026-09-06).
       ⇒ 이어진 말줄임표를 **한 덩어리**로, 피치 `round(칸/3)` 으로 고르게 놓고 가운데 맞춘다.
    """
    cell, rows = (
        _cell(font),
        (_cell(font) * 3 if font.startswith("Galmuri") else _ttf_rows(_cell(font))),
    )
    base = _baseline(font)
    n = sum(ELLIPSIS[c] for c in chars)
    width = cell * len(chars)
    thick = 1 if cell <= 12 else 2
    pitch = max(2, round(cell / 3))
    span = pitch * (n - 1) + thick
    x0 = (width - span) // 2
    m = np.zeros((rows, width), bool)
    for k in range(n):
        x = x0 + k * pitch
        m[base - thick + 1 : base + 1, x : x + thick] = True
    return m, width


_ADV = {}


def _advance(name):
    """BDF 의 `DWIDTH` — 코드포인트 → 보내는 폭.

    🔴 **Galmuri 의 아스키는 비례폭이다.** 「반각 = 칸의 절반」으로 흘렸더니 숫자(DWIDTH 8)가
       5px 로 잘렸다 — 「20」이 뭉갰다(유저 지적 2026-09-05). 쉼표·온점은 4, 공백은 5다.
    ⚠ `shared/fonts` 의 BDF 로더가 BBX 만 들고 DWIDTH 를 버려서 여기서 한 번 더 읽는다.
       **제자리는 `shared/` 다** — 공용 코드는 main 에서만 고치므로(루트 CLAUDE.md) 미뤘다.
    """
    if name not in _ADV:
        adv, cp = {}, None
        path = os.path.join(common.REPO, "shared", "fonts", f"{name}.bdf")
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                t = line.split()
                if not t:
                    continue
                if t[0] == "ENCODING":
                    cp = int(t[1])
                elif t[0] == "DWIDTH" and cp is not None:
                    adv[cp] = int(t[1])
        _ADV[name] = adv
    return _ADV[name]


def _bdf_line(txt, name):
    """BDF 는 도트가 파일에 박혀 있어 크기를 안 탄다 — 한글은 칸 폭(이름의 숫자)으로 흘린다.

    ⚠ **아스키는 전각이 아니다** — 쉼표·온점·공백을 전각 칸에 넣으면 문장이 헐거워진다.
    🔴 그렇다고 「칸의 절반」도 아니다 — Galmuri 의 아스키는 **비례폭**이라 글자마다 다르다
       (숫자 8 · 쉼표 4 · 공백 5). 절반으로 흘렸더니 「20」이 잘렸다. `_advance` 를 쓴다.
    """
    f = galmuri(name)
    cell = _cell(name)
    adv = _advance(name)
    cols = []
    for ch in txt:
        # 한글은 칸 폭, 아스키는 **폰트가 정한 폭**(비례폭이다 — `_advance` 참조)
        wide = cell if ord(ch) >= 0x80 else adv.get(ord(ch), cell // 2)
        if ch == " ":
            cols.append(np.zeros((cell * 3, wide), bool))
            continue
        if not f.has(ch):
            raise SystemExit(f"🔴 글리프 없음: {ch!r} ({name})")
        cols.append(f.bits(ch, dy=cell, rows=cell * 3, width=cell + 8)[:, :wide].astype(bool))
    m = np.concatenate(cols, axis=1) if cols else np.zeros((cell * 3, 1), bool)
    return m, m.shape[1]


def render_line(txt, font):
    """말줄임표만 따로 찍어 이어 붙인다 — 나머지는 폰트가 그대로 흘린다."""
    segs, buf = [], ""
    for ch in txt:
        if ch in ELLIPSIS:
            if buf:
                segs.append(("t", buf))
                buf = ""
            if segs and segs[-1][0] == "e":  # 이어진 말줄임표는 한 덩어리 — 점 간격을 고르게
                segs[-1] = ("e", segs[-1][1] + ch)
            else:
                segs.append(("e", ch))
        else:
            buf += ch
    if buf:
        segs.append(("t", buf))
    parts = []
    for kind, seg in segs:
        if kind == "e":
            parts.append(_dots(seg, font))
        elif font.startswith("Galmuri"):
            parts.append(_bdf_line(seg, font))
        else:
            parts.append(_ttf_text(seg, _cell(font)))
    if not parts:
        return np.zeros((1, 1), bool), 0
    h = max(p[0].shape[0] for p in parts)
    m = np.concatenate([np.pad(p[0], ((0, h - p[0].shape[0]), (0, 0))) for p in parts], axis=1)
    return m, m.shape[1]


def _ink_top(m):
    ys = np.nonzero(m.any(axis=1))[0]
    return int(ys.min()) if len(ys) else 0


def draw_block(lines, w, h, font, align, left, top, pitch, gap):
    """줄들을 판에 앉힌다 — 빈 줄은 **문단 사이**(gap)로 친다."""
    out = np.zeros((h, w), bool)
    y, over = top, []
    for ln in lines:
        if not ln:
            y += gap - pitch
            continue
        m, wid = render_line(ln, font)
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


# 🔴 **화면이 안 그리는 열이 있다.** 512폭 오프닝 카드는 **254·255** 를 버린다 —
#    게임이 반씩 두 번 찍는데 오른쪽 반이 2px 왼쪽에 얹힌다. 그 열에 걸친 획은
#    **조용히 사라진다**(「무」의 ㅁ 왼쪽 세로획이 없어져 ㄱ 으로 읽혔다 — 유저 지적).
#    ⇒ 글자를 **510폭으로 짜고** 그 자리에 **빈 열 둘을 끼워** 512로 늘린다.
#    근거 둘 — ① 에뮬 화면과 대조해 254 에서 어긋남이 최소(26px, 전부 별)
#              ② **원본 일본어 두 장 다 254·255 가 정확히 비어 있다**(원작도 피해 그렸다).
#    ⚠ 자리마다 다르므로 **잰 곳만** 정본에 `seam` 을 적는다 — 432폭 엔딩은 원본에
#      그런 빈 열이 없어 아직 모른다(건드리지 않는다).
SEAM_W = 2


def build_group(g):
    """(파일이름 → RGBA 배열, 넘친 줄, 쓴 높이)."""
    canvas_h = g.get("canvas_h", g["h"])
    seam = g.get("seam")
    ink, used, over = draw_block(
        g["lines"],
        g["w"] - SEAM_W * (seam is not None),
        canvas_h,
        g["font"],
        g["align"],
        g.get("left", 0),
        g["top"],
        g["pitch"],
        g["gap"],
    )
    if seam is not None:  # 안 그려지는 열 둘을 끼워 넣는다
        ink = np.insert(ink, [seam] * SEAM_W, False, axis=1)
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
                w = g["w"] - SEAM_W * (g.get("seam") is not None)
                print(f"       칸을 넘는다({wid}px + 왼쪽 {g.get('left', 0)} > {w}): {ln}")
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
