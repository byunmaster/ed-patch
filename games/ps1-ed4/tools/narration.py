"""오프닝·엔딩·스태프롤 그림 글 — **우리가 한국어로 다시 그린다**(마스터 10-24 「번역해서 넣자, 폰트는 ps1 ed3 처럼」).

    python3 tools/narration.py preview [<출력폴더>]   # 어두운 바탕에 원본 | 우리 나란히 (마스터 확인용 — 굽지 않는다)
    python3 tools/narration.py check                  # 줄이 그림 안인가 · 압축 뒤 크기가 원 멤버 한도 안인가
    python3 tools/narration.py build <출력폴더>       # 새 멤버(TIZ) 바이트를 파일로 저장

정본은 `narration_ed4.json`(**우리 한국어만** — 원문 금지). 슬롯 k = 원본 줄 k(위 1행부터 피치 12 · C_846 은 0행부터 피치 13).
새 글을 지울 때는 **그 슬롯의 잉크 띠만** 지우고 슬롯이 `null` 이면 원본(영문 줄 등)을 그대로 둔다.
- 정렬 `c` = 이미지 안 원본 줄 가운데들의 **중앙값** 축에 맞춘다(줄 끝 `.` `,` `…` 는 폭에서 뺀다 — 번역 규칙 2-8). `left` 로 지정한 슬롯은 그 묶음 원본의 왼쪽 가장자리에 맞춘다.
- 글꼴 Galmuri11(원본 잉크 높이 11px 와 같다 — ED3 두루마리와 같은 길). 흰 글씨 + 투명(원본이 1비트 순백). C_846 은 원본이 (+1,+1) 어두운 그림자(8,8,8)를 둬서 같이 그린다.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import linefont
import title_img
from PIL import Image

from shared.ps1 import tim

CANON = os.path.join(common.ROOT, "narration_ed4.json")
FONT = "Galmuri11"
INK = (255, 255, 255, 255)
SHADOW = (8, 8, 8, 255)


def load():
    with open(CANON, encoding="utf-8") as f:
        return json.load(f)["images"]


def geometry(base):
    """(첫 슬롯 윗줄, 피치) — C_846 만 다르다."""
    return (0, 13) if base == "C_846.TIZ" else (1, 12)


def slot_band(base, k):
    y0, pitch = geometry(base)
    top = y0 + pitch * k
    return top, top + 10  # 잉크 11행(그림자 행은 아래 +1)


def ink_extent(alpha, top, bot):
    xs = np.nonzero(alpha[top : bot + 2].any(axis=0))[0]
    return (int(xs.min()), int(xs.max())) if len(xs) else None


def draw(base, spec, orig):
    """원본 RGBA(`orig`) → (새 RGBA, 보고 목록). 칸 밖이면 `ValueError`."""
    arr = np.array(orig)
    alpha = arr[:, :, 3] > 0
    h, w = alpha.shape
    shadow = bool(spec.get("shadow"))
    slots = spec["slots"]
    ext = {}
    for k in range(len(slots)):
        top, bot = slot_band(base, k)
        if bot + 1 >= h + 1:
            raise ValueError(f"{base}: 슬롯 {k} 가 그림 밖이다")
        e = ink_extent(alpha, top, min(bot, h - 1))
        if e:
            ext[k] = e
    centers = [(a + b) / 2 for a, b in ext.values()]
    axis = float(np.median(centers)) if centers else w / 2
    left_x = {}
    if spec.get("align") == "l":
        lefts = [ext[k][0] for k, t in enumerate(slots) if t and k in ext]
        lx = min(lefts)
        left_x = {k: lx for k in range(len(slots))}
    for k in spec.get("left", []):
        if k in ext:
            left_x[k] = min(ext[j][0] for j in spec["left"] if j in ext)
    report = []
    pitch = geometry(base)[1]
    # 🔴 먼저 **띠를 전부 지운 다음** 그린다 — 줄마다 지우며 그리면 다음 줄 지우기가 앞 줄 맨 아래 행(받침·밑획)을 깎는다(10-24 관리자 검토)
    for k, text in enumerate(slots):
        if text:
            top, _ = slot_band(base, k)
            arr[top : min(h, top + pitch), :, :] = 0
    limit = pitch - (1 if shadow else 0)  # 그림자는 잉크 아래 한 행
    placed = []
    for k, text in enumerate(slots):
        if not text:
            continue
        top, _ = slot_band(base, k)
        m = linefont.render(text, FONT)
        m = m[: int(np.nonzero(m.any(axis=1))[0].max()) + 1]  # 아래 빈 행 버림
        mh, mw = m.shape
        body = linefont.width_of(text, FONT)
        x = left_x[k] if k in left_x else round(axis - body / 2)
        if x < 0 or x + mw > w:
            raise ValueError(f"{base} 슬롯 {k}: 「{text}」 폭 {mw}px 가 그림 밖이다(x={x})")
        if mh > limit + 1:
            raise ValueError(f"{base} 슬롯 {k}: 줄 높이 {mh} 가 띠({limit}행)보다 둘 이상 크다")
        if (
            mh > limit
        ):  # 로마자 내림획(j p g y)이 띠를 한 행 넘는다 → 줄 전체를 한 행 올린다(앞 줄 맨 아래 틈 행을 쓴다)
            top -= 1
        if top < 0 or top + mh + (1 if shadow else 0) > h:
            raise ValueError(f"{base} 슬롯 {k}: 줄이 그림 밖이다")
        for r in range(mh):
            for c in range(mw):
                if m[r, c]:
                    if arr[top + r, x + c, 3]:
                        raise ValueError(
                            f"{base} 슬롯 {k}: 「{text}」 가 다른 줄 잉크와 겹친다({top + r},{x + c})"
                        )
                    arr[top + r, x + c] = INK
        if shadow:
            ink = np.zeros((h, w), bool)
            ink[top : top + mh, x : x + mw] = m
            sh = np.zeros_like(ink)
            sh[1:, 1:] = ink[:-1, :-1]
            sh &= ~ink
            arr[sh] = SHADOW
        placed.append((k, text, top, x, m))
        report.append((k, text, x, mw, round(axis)))
    # 🔴 잘린 픽셀 0 — 그린 줄의 잉크가 **최종 그림에 그대로** 남았는가(뒤 줄이 앞 줄을 깎지 않았나)
    for k, text, top, x, m in placed:
        mh, mw = m.shape
        got = (arr[top : top + mh, x : x + mw, 0] == 255) & (
            arr[top : top + mh, x : x + mw, 3] == 255
        )
        lost = int((m & ~got).sum())
        if lost:
            raise ValueError(f"{base} 슬롯 {k}: 「{text}」 잉크 {lost}픽셀이 잘렸다")
    return Image.fromarray(arr, "RGBA"), report


def original(base, arc):
    _n, blk, raw, t = title_img.load(base, arc)
    row = tim.best_palette(t)
    return tim.to_image(t, row), blk, raw, t


def render_all():
    out = {}
    for base, spec in load().items():
        orig, blk, _raw, _t = original(base, spec["arc"])
        new, rep = draw(base, spec, orig)
        out[base] = (orig, new, rep, len(blk))
    return out


def preview(outdir):
    os.makedirs(outdir, exist_ok=True)
    for base, (orig, new, rep, _lim) in render_all().items():
        w, h = orig.size
        sheet = Image.new("RGBA", (w * 2 + 12, h), (30, 30, 60, 255))
        for i, im in enumerate((orig, new)):
            bg = Image.new("RGBA", (w, h), (30, 30, 60, 255))
            bg.alpha_composite(im.convert("RGBA"))
            sheet.paste(bg, (i * (w + 12), 0))
        sheet.convert("RGB").resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(
            os.path.join(outdir, base.split(".")[0] + "_orig_vs_kr.png")
        )
        new.save(os.path.join(outdir, base.split(".")[0] + "_kr.png"))
        print(f"{base}: 줄 {len(rep)} 개 · 폭 최대 {max(r[3] for r in rep)}px")


def member_edits():
    """`build.build` 의 `edits["members"]` — {(아카이브, 멤버 이름): 새 TIZ 바이트}. 검산(`title_img.check`)을 통과한 것만, 못 넘으면 멈춘다."""
    import tempfile

    out = {}
    with tempfile.TemporaryDirectory() as td:
        for base, (_orig, new, _rep, _lim) in render_all().items():
            arc = load()[base]["arc"]
            png = os.path.join(td, base.split(".")[0] + ".png")
            new.save(png)
            ok, msg, blk = title_img.check(png, base, arc=arc)
            if not ok:
                raise SystemExit(f"🔴 {msg}")
            out[(arc, title_img.member(base, arc=arc)[0])] = blk
    return out


def check(outdir):
    os.makedirs(outdir, exist_ok=True)
    bad = 0
    for base, (_orig, new, _rep, _lim) in render_all().items():
        png = os.path.join(outdir, base.split(".")[0] + "_kr.png")
        new.save(png)
        ok, msg, _blk = title_img.check(png, base, arc=load()[base]["arc"])
        print(msg)
        bad += not ok
    return 1 if bad else 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    common.verify_source()
    if cmd == "preview":
        preview(argv[2] if len(argv) > 2 else os.path.join(common.REVIEW_DIR, "narration"))
        return 0
    if cmd == "check":
        return check(argv[2] if len(argv) > 2 else os.path.join(common.REVIEW_DIR, "narration"))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
