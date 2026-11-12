#!/usr/bin/env python3
"""가운데 맞춤 전수(번역 규칙 2-8, 마스터 11-03) — 가운데 맞춘 줄의 **실제 픽셀 폭** 좌우 여백 차가 1px 을 넘는 줄을 센다.

    python3 tools/check_centered.py [--show]

줄 끝 문장부호(`.` `,` `…`)는 폭에서 뺀다(2-8 · 마스터 10-13). 잰 자리:
  내레이션   오프닝·엔딩 그림에 박는 글(`narration.draw_block` 과 같은 길 — 줄의 잉크 가로 범위로 잰다)
  장 끝 띠   서장~제6장 끝 항해 연출의 A·B 두 줄(`chapter_end.plan_chapter` 의 줄 폭·자리 — 띠 칸 범위의 가운데가 기준)
  장 카드    서장 카드 제목(`chapter_prologue.png` 의 제목 줄 잉크)
안 잰 자리(코드 칸 단위 가운데 — 시스템 메뉴 하위 창·데이터 창 제목·예/아니오·월드맵 지명 패널)는 6px 칸 단위라 1px 오차를 못 맞추는 것이
구조이고, 마스터가 화면으로 판정했다(10-09~10-25). 패널은 엔진 스텁이 줄마다 가운데를 계산한다.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

TOL = 1  # 좌우 여백 차(px)
# 알려진 한계 — 이 줄은 가운데를 못 맞춘다(사유가 풀리면 지운다). 기준: (자리, 줄) → 사유
EXEMPT = {
    ("장 끝 MR43V0", "A"): "가운데 0px 안은 시트 압축이 +393B 라 아카이브 여유 332B 를 넘는다(arcpack) — 한 칸 옮긴 안이 최선",
    ("장 끝 MR43V0", "B"): "같은 이유",
}


def margin_problems(items, tol=TOL):
    """items = [(자리, 줄, 왼쪽 여백, 오른쪽 여백)] → 여백 차가 tol 을 넘는 것 [(자리, 줄, 차)]."""
    return [(p, ln, abs(left - right)) for p, ln, left, right in items if abs(left - right) > tol]


def narration_items():
    import narration

    doc = narration.load()
    out = []
    for g in doc["groups"]:
        if g["align"] != "center":
            continue
        w = g["w"] - narration.SEAM_W * (g.get("seam") is not None)
        for ln in g["lines"]:
            if not ln:
                continue
            body = ln.rstrip(".,…")  # 줄 끝 부호는 폭에서 뺀다
            bm, cw = narration.render_line(body, g["font"]) if body else narration.render_line(ln, g["font"])
            x = (w - cw) // 2
            cs = np.nonzero(bm.any(0))[0]
            out.append((f"내레이션 {g['name']}", ln, int(x + cs.min()), int(w - 1 - (x + cs.max()))))
    return out


def chapter_items():
    import chapter_end as C

    L = C.load_layout()
    font = C.load_font(C.font_path())
    titles = C.chapter_titles()
    shapes = C.quote_shapes_from(C.pix_orig(L, "MT70V0"), L["MT70V0"]["transparent"], L)
    out = []
    for i, name in enumerate(C.CHAPTERS):
        v = L[name]
        lba0, size0 = common.iso_files("ed3")[v["pack"]]
        arc0 = common.read_lba("ed3", lba0, size0)
        _o0, n0 = common.arc_members(arc0)[f"..\\TIM\\C_{v['sheet']:03d}.TI3"]
        _raw, _anm, rep, _canv = C.plan_chapter(
            L, name, font, i, titles, shapes, "다음 장", 1, max_len=n0 + C.GROW_MAX
        )
        anm0, _key, base = C.read_anm(L, name)
        strips = v["strips"]
        claimed = {wi for st in "AB" for sp in strips[st] for wi in range(sp["lo"], sp["hi"] + 1, 2)}
        for st in "AB":
            cells = C.strip_cells(strips[st], anm0, base, claimed)
            lo = max(0, min(x for _w, x in cells))
            hi = min(C.SCREEN_W, max(x for _w, x in cells) + 16)
            x0, w = rep[f"{st}_x"]
            out.append((f"장 끝 {name}", st, x0 - lo, hi - (x0 + w)))
    return out


def card_items():
    from PIL import Image

    p = os.path.join(common.ROOT, "assets", "graphics", "ed3", "chapter_prologue.png")
    a = np.array(Image.open(p).convert("RGBA"))
    ink = (a[..., 3] > 0) & (a[..., :3].sum(-1) > 0)
    ys = np.nonzero(ink.any(1))[0]
    y1 = ys[0]
    while y1 + 1 in ys:
        y1 += 1
    xs = np.nonzero(ink[ys[0] : y1 + 1].any(0))[0]  # 첫 줄(제목)만 — 아래 줄은 원판 NOW LOADING
    return [("장 카드 서장", "제목", int(xs.min()), int(a.shape[1] - 1 - xs.max()))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    try:
        items = narration_items() + chapter_items() + card_items()
    except (OSError, SystemExit, KeyError) as e:
        print(f"가운데 맞춤 전수 — 안 쟀다(원판 디스크를 못 읽음: {e})")
        return 1
    bad = margin_problems(items)
    hard = [b for b in bad if (b[0], b[1]) not in EXEMPT]
    known = [b for b in bad if (b[0], b[1]) in EXEMPT]
    print(
        f"가운데 맞춤 전수 [ed3] — 줄 {len(items)} · 여백 차 > {TOL}px {len(bad)} (알려진 한계 {len(known)} · 위반 {len(hard)})"
    )
    for p, ln, d in known:
        print(f"  ⚠ {p} {ln!r} 차 {d}px — {EXEMPT[(p, ln)]}")
    for p, ln, d in hard:
        print(f"  🔴 {p} {ln!r} 차 {d}px")
    if a.show:
        for p, ln, left, right in items:
            print(f"    {p} {ln!r}: 왼쪽 {left} 오른쪽 {right}")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
