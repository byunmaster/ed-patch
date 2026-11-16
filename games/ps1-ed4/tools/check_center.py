"""가운데 맞춤 게이트(공통 번역 규칙 2-8) — **실제 픽셀 폭**으로 재고, 줄 끝 문장부호(`.` `,` `…`)는 폭에서 뺀다. 좌우 여백 차가 1px 넘으면 결함.

    python3 tools/check_center.py

자리 둘 (ED4 에서 가운데 맞춤인 곳):
  ① 오프닝·엔딩 그림 글(`narration_ed4.json` 의 `align: c` 그림) — 그린 줄마다 몸통 폭(줄 끝 부호 뺌)의 가운데가 이미지 축에서 0.5px 안인가(= 좌우 여백 차 ≤ 1px).
  ② 아이템 사용 결과 메시지 창 둘(`halfwidth.ITEM_MSG_PATCH`) — 창 가운데 x 는 원판 그대로, 글자는 창 안 좌우 여백(8px)에 같게 놓여야 한다.
     글자 폭은 반각 단위(6px)·열은 12px 라 몸통이 홀수 반 열이면 6px 차가 남는다 — 그 한계(`best_diff`)보다 나쁘면 결함.
  (전리품 창의 「n 피스카를 얻었다.」는 n 의 자릿수가 달라 폭이 변한다 — 정적으로 못 센다. 필드 지명·장 제목 띠는 원판 그림이라 손대지 않는다.)
양성 대조(`selftest`)가 가짜 값에서 결함을 잡는지 먼저 확인한다.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))
import common
import halfwidth
import linefont
import narration
import typeset

PAD = 8  # 창 안쪽 여백(px) — 창 폭 = 열×12 + 16
TRIM = ".,…"
# 🔴 엔진이 창 열 수로 **그릴 수 있는 글자 수도 정한다**(11-05 헤드리스 실측 — 코드 명령을 꽂아): 열 13 → 반각 칸 23 · 14 → 25 · 15 → 27, 곧 `열×12px − 18px` 까지만 그린다(창 폭은 안 모자라도 끝이 잘린다).
ENGINE_CLIP_PX = 18

# 창 둘: (이름, x 주소들, 열 주소들, 문안 UI 오프셋, 원판 가운데 x)
WINDOWS = (
    ("A", (0x80026578, 0x800265A8), (0x80026580,), "0x000A7A", 158),
    ("B", (0x800265AC, 0x800265DC), (0x800265B4,), "0x000A64", 152),
)


def text_px(txt):
    return typeset.px_width(txt)


def margins(txt, cols):
    """창 안 좌 여백, 우 여백(줄 끝 부호를 뺀 몸통 기준) — 앞 반각 공백은 글자 앞 여백으로 친다."""
    body = txt.rstrip(TRIM)
    lead = len(body) - len(body.lstrip(" "))
    left = PAD + text_px(" " * lead)
    right = PAD + cols * typeset.CELL_PX - text_px(body)
    return left, right


def best_diff(txt, ncols=range(4, 30), lead_max=3):
    """열 수·앞 반각 공백 수를 어떻게 골라도 줄일 수 없는 최소 여백 차(글이 창 안에 들어가는 조합만)."""
    base = txt.lstrip(" ")
    best = None
    for c in ncols:
        for lead in range(lead_max + 1):
            t = " " * lead + base
            if text_px(t) > c * typeset.CELL_PX - ENGINE_CLIP_PX:
                continue
            l, r = margins(t, c)
            d = abs(l - r)
            best = d if best is None or d < best else best
    return best


def window_cells():
    """[(이름, 열, x 픽셀, 문안, 가운데 x)] — 굽는 값(`ITEM_MSG_PATCH` 새 명령 + `ui_ed4.json`)."""
    import json

    new = {a: w & 0xFFFF for a, _old, w in halfwidth.ITEM_MSG_PATCH}
    ui = json.load(open(os.path.join(common.ROOT, "ui_ed4.json"), encoding="utf-8"))["strings"]
    out = []
    for name, xs, cs, off, cen in WINDOWS:
        xv = {new[a] for a in xs}
        cv = {new[a] for a in cs}
        if len(xv) != 1 or len(cv) != 1:
            raise SystemExit(f"🔴 창 {name} x·열 명령이 자리마다 다르다: {xv} {cv}")
        out.append((name, cv.pop(), xv.pop(), ui[off]["kr"], cen))
    return out


def check_window(name, cols, x, txt, cen):
    """결함 문장 목록 — 창 가운데가 원판과 같고, 여백 차가 최선보다 나쁘지 않아야 한다."""
    bad = []
    width = cols * typeset.CELL_PX + 2 * PAD
    if x + width / 2 != cen:
        bad.append(f"창 {name}: 가운데 {x + width / 2} ≠ 원판 {cen}")
    if text_px(txt) > cols * typeset.CELL_PX - ENGINE_CLIP_PX:
        bad.append(
            f"창 {name}: 글 {text_px(txt)}px 가 엔진이 그리는 폭 {cols * typeset.CELL_PX - ENGINE_CLIP_PX}px 를 넘는다(끝이 잘린다)"
        )
    l, r = margins(txt, cols)
    d, bd = abs(l - r), best_diff(txt)
    if bd is not None and d > bd:
        bad.append(f"창 {name}: 좌 {l} · 우 {r} 여백 차 {d}px (최선 {bd}px)")
    return bad, (l, r, bd)


def narration_defects():
    """[(그림, 슬롯, 문안, 가운데 오차 px)] — 가운데 맞춤 줄 중 오차가 0.5px(좌우 여백 차 1px) 넘는 것, 그리고 센 줄 수."""
    common.verify_source()
    bad, n = [], 0
    for base, (_o, _new, rep, _lim) in narration.render_all().items():
        spec = narration.load()[base]
        lefts = set(spec.get("left", []))
        for k, text, x, _mw, _axis in rep:
            if spec.get("align") == "l" or k in lefts:
                continue
            n += 1
            axis = _axis_of(base, spec)
            body = linefont.width_of(text, narration.FONT)  # 줄 끝 부호 뺀 폭
            off = x + body / 2 - axis
            if abs(off) > 0.5 + 1e-9:
                bad.append((base, k, text, off))
    return bad, n


def _axis_of(base, spec):
    import numpy as np

    orig, _blk, _raw, _t = narration.original(base, spec["arc"])
    alpha = np.array(orig)[:, :, 3] > 0
    h, w = alpha.shape
    ext = {}
    for k in range(len(spec["slots"])):
        top, bot = narration.slot_band(base, k)
        e = narration.ink_extent(alpha, top, min(bot, h - 1))
        if e:
            ext[k] = e
    cs = [(a + b) / 2 for a, b in ext.values()]
    return float(np.median(cs)) if cs else w / 2


def selftest():
    assert margins(" 가나다.", 3)[0] == PAD + 6
    # 열이 모자라면 잡는다 · 가운데가 어긋나면 잡는다 · 열이 너무 넓으면 잡는다
    assert check_window("T", 2, 100, "가나다", 100 + (2 * 12 + 16) / 2)[0]
    assert check_window("T", 3, 100, "가나다", 999)[0]
    assert check_window("T", 9, 100, "가나다", 100 + (9 * 12 + 16) / 2)[0]
    # 최선 조합(열·앞 공백)은 통과해야 한다
    for c in range(4, 30):
        for lead in range(4):
            t = " " * lead + "가나다"
            if text_px(t) <= c * 12 - ENGINE_CLIP_PX and abs(
                margins(t, c)[0] - margins(t, c)[1]
            ) == best_diff("가나다"):
                assert not check_window("T", c, 100, t, 100 + (c * 12 + 16) / 2)[0]
                return


def main():
    selftest()
    bad = []
    for cell in window_cells():
        b, (l, r, bd) = check_window(*cell)
        print(f"  창 {cell[0]}: {cell[1]}열 x {cell[2]:#x} 좌 {l} · 우 {r} (최선 차 {bd}px)")
        bad += b
    nb, n = narration_defects()
    bad += [f"{b} 슬롯 {k} 「{t}」 가운데 오차 {o:+.1f}px" for b, k, t, o in nb]
    print(
        f"가운데 맞춤 전수 — 그림 글 {n}줄 · 창 {len(WINDOWS)}곳 · 양성 대조 ✓ · "
        + (f"결함 {len(bad)}" if bad else "결함 0")
    )
    for s in bad:
        print("  ✗", s)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
