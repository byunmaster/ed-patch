"""타이틀 화면 그림 셋을 굽는다 — 로고(260×76) · 버튼 둘(174×24).

    python3 tools/title_art.py            # 셋 다 → assets/graphics/ed3/
    python3 tools/title_art.py --check    # 지금 커밋된 PNG 와 같은 바이트가 나오나

⚠ **정본은 만들어진 PNG 다**(`assets/graphics/ed3/*.png`) — 빌드는 그걸 읽는다.
   이 파일은 「그 PNG 를 어떻게 만들었나」의 기록이고, 손질할 때 다시 돌리는 자리다.
🔴 **로고는 이 머신에서만 다시 구울 수 있다** — 큰 글자를 `.local/ed3_title.png`
   (유저가 이미지 AI 로 만든 그림, 머신 전용·gitignore)에서 떼어 오기 때문이다.
   없으면 로고는 건너뛰고 버튼만 굽는다. 그래서 PNG 를 정본으로 둔다.

## 왜 이렇게까지 하나 — 실측으로 밟은 함정들

- **AI 그림엔 투명이 없다.** 체커무늬가 **그림으로 박혀** 있고 그림자까지 그 위에 드리워져
  있다. 칸 크기도 위아래가 달라 격자 모델이 안 통한다 ⇒ **질감으로 가른다**(`_segment`).
- **버튼은 판을 살려야 한다.** 원본 판의 조각을 되접어 깔면 **거울 대칭**이 눈에 띄고,
  픽셀 단위 무작위는 **소금·후추**가 된다 ⇒ 조각의 **진폭 스펙트럼만** 빌려 위상을 새로
  뽑는다(`_synth`). 결은 **곱으로** 얹는다 — 더하면 채널마다 세기가 달라 **초록끼**가 돈다.
- **원본 판엔 투명 점이 박혀 있다**(버튼당 60~76). 일본어 획 안에 숨어 있던 것이라
  우리 글자로 바꾸면 **판 위의 검은 구멍**으로 드러난다 ⇒ 갇힌 것만 메운다.
- **작은 글자에 아웃라인 폰트를 쓰지 않는다.** neodgm 14px 은 「처」의 ㅊ 이 무너진다.
  15px 이 가장 작으면서 온전하다(도트로 확인).
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common


def _local(*parts):
    """`.local` 은 **머신 전용**(gitignore)이라 워크트리엔 없다 — 위로 올라가며 찾는다."""
    d = common.REPO
    for _ in range(5):
        f = os.path.join(d, ".local", *parts)
        if os.path.exists(f):
            return f
        d = os.path.dirname(d)
    return os.path.join(common.REPO, ".local", *parts)


SPEC = os.path.join(common.ROOT, "work", "review", "tim", "ed3", "_spec")
ASSETS = os.path.join(common.ROOT, "assets", "graphics", "ed3")
AI_SRC = _local("ed3_title.png")
NEODGM = os.path.join(common.REPO, "shared", "fonts", "neodgm.ttf")
SUB_FONT = _local("fonts", "YeonSung-Regular.ttf")

W, H, TOP = 260, 76, 25  # 금판 0~24 는 **원본 픽셀 그대로** 쓴다
BIG_W, BIG_H = 252, 34  # 큰 글자 칸 (원본 258×34)
# ⚠ 로고가 **둘**이다 — 타이틀 화면(260×76)과 **오프닝 끝(400×118)**. 오프닝 쪽을 놓쳐서
#   번역이 안 된 채로 떴다(유저 지적 2026-09-04). 자리 값은 원본에서 잰 것이다.
OP = {
    "src": "title_DATA5_3_260x76_8bpp.png",
    "w": 400,
    "h": 118,
    "top": 35,
    "big_w": 392,
    "big_h": 67,
    # 🔴 글자가 띠를 꽉 채우면 **흰 테의 위아래가 잘린다**(유저 지적 2026-09-05) ⇒
    #    글자를 이만큼 눌러 넣고 위아래로 여백을 남긴다. 옆은 원래 여유가 있다.
    # 위는 0 — JP 원본이 글자 알파를 띠 첫 행(35)에 붙였고 우리는 4행 아래 떠 있었다(유저 지적).
    # 아래 2 — 부제와 붙지 않게. 그만큼 글자도 커진다(JP 몸통 63행, 우리 55행이었다).
    "pad_top": 0,
    "pad_bot": 0,  # JP 는 큰 글자 알파가 101행까지 내려와 부제와 3행 뜬다 — 우리는 98 로 6행 떴다(유저 지적)
    "margin": 4,
    # 🔴 테 두께(400 기준 px). **JP 원본 실측 1.4**(1~2) — 업스케일 실루엣을 빌렸을 땐 4.5(3~7)로
    #    세 배 두껍고 들쭉날쭉했다(유저 지적 2026-09-05). 매끈한 몸통을 **한 반지름으로**
    #    부풀리므로 두께가 구조적으로 균일하다.
    "rim": 1.6,
    "smooth": 1.0,  # 실루엣 흐림(3배 기준 σ 의 배수) — 클수록 매끈, 1.2 면 ㅎ·ㅁ 이 뭉갠다
    "edge": 0.85,  # 1비트 알파 계단을 색으로 눅이는 강도
    "aa": 1.0,
    "sharpen": 1.3,  # 몸통 언샤프 세기 — 흐림·중앙값 뒤에 되살린다. JP 선명도 31.9, 0 이면 22.0(유저: 흐릿하다)  # 가장자리 커버리지 어둡히기 지수 — 클수록 진하게
    "tex_med": 3,  # 질감 비율의 중앙값 필터 크기 — 잡티만 지우고 띠·고리는 남긴다
    "tex_clip": 0.6,  # 질감 비율 폭(±) — 좁히면 원천의 어두운 윤곽 구조까지 죽는다
    "band_blur": 0.8,  # 깊이 단계 색을 잇는 흐림 — 1.2 면 2px 띠가 녹아 없어진다
    "sub_rows": 16,
    "sub_ink": 12,
    "sub_bottom": 117,
}
SUB_TEXT = "또 하나의 영웅들의 이야기"
# 🔴 부제는 세로로 1.85배 눌리므로 **가로로 뚫린 속**이 먼저 메워진다.
#    「들」의 ㄷ 이 그래서 덩어리로 보였다(유저 지적 2026-09-05) ⇒ 그 글자만 속을 넓힌다.
#    값은 눌리기 **전** 해상도로 (속을 위·아래로 몇 줄 넓힐지, 윗획·아랫획을 오른쪽으로
#    몇 칸 늘일지)다. 속만 트면 획이 짧아 여전히 아리송하다 ⇒ **획도 같이 늘인다.**
#    ⚠ **속을 위로 넓히지 않는다** — ㄷ 의 윗획을 깎으면 **ㄴ 으로 보인다**(유저 지적).
#    ⚠ 아랫획을 더 늘이면 바로 아래 ㅡ 와 붙어 다시 덩어리가 된다.
SUB_OPEN = {"들": (0, 4, 16, 24)}
SUB_BOTTOM = 69  # 부제 아래를 원본(68행)에 맞춘다
SS = 8  # 글자는 8배로 찍고 줄인다

# 값은 전부 유저가 그림으로 골랐다(2026-09-04) — 수치가 아니라 눈이 기준인 자리들이다.
SUB_ROWS, SUB_INK, SUB_SQUASH, SUB_TRACK, SUB_HALO = 14, 10, 1.85, 0, 12
SOFT, EDGE = 0.5, 0.7  # 테 안쪽 번짐 · 곡선 계단 눅이기
NAVY = (0, 0, 24)  # 원본이 쓰는 가장 어두운 색
INK_TOP, INK_BOT = (247, 198, 140), (181, 132, 90)  # 버튼 글자 위/아래
BTN_SIZE, BTN_CENTER = 15, 10  # 🔴 14px 은 「처」가 무너진다 · 잉크 13줄이라 중심은 10
BTN_DIM = {1: 1.0, 2: 0.86}  # 원본은 아래 판이 밝아 글씨가 묻힌다 — 위와 맞춘다
BUTTONS = [
    (1, "모험을 이어서 한다", "title_btn_continue.png"),
    (2, "모험을 처음부터 한다", "title_btn_new.png"),
]
EDGE_CUT = 4  # 판 양끝의 세로 테는 표본에서 뺀다


# ── 공통 ────────────────────────────────────────────────────────────────────
def _disk(r):
    r = round(r)
    yy, xx = np.ogrid[-r : r + 1, -r : r + 1]
    return (xx * xx + yy * yy) <= r * r


def _to15(a):
    """PS1 은 15비트 색이다 — 미리 줄여 두면 시안이 곧 화면이다."""
    q = np.clip(np.round(np.asarray(a, dtype=np.float32) / 255 * 31), 0, 31)
    return np.round(q * 255 / 31).astype(np.uint8)


def _colors(a):
    return len({tuple(p) for p in a[a[..., 3] > 0].reshape(-1, 4)})


def _fit_palette(rgba, first=250, plate=None):
    """8bpp = **불투명 255색 + 투명 1**. 넘으면 한 단계 낮춰 다시 줄인다."""
    op = rgba[..., 3] >= 128
    for maxc in (first, 220, 200, 185, 175, 165, 150, 140):
        q = _to15(
            np.asarray(
                Image.fromarray(rgba[..., :3])
                .quantize(colors=maxc, method=Image.MEDIANCUT, dither=Image.NONE)
                .convert("RGB")
            )
        )
        out = np.dstack([q, (op * 255).astype(np.uint8)])
        out[~op] = 0
        if plate is not None:
            out[:TOP] = plate  # 금판은 색 줄이기 **뒤에** 붙인다
        if _colors(out) <= 255:
            return out, _colors(out)
    raise SystemExit(f"🔴 색이 안 줄어든다: {_colors(out)}")


def _soften_edge(rgb, m, strength, knee=0.80, span=0.40):
    """1비트 알파의 **계단**을 색으로 눅인다.

    곡선은 알파가 1비트인 한 반드시 계단이 진다 — 없앨 수는 없다. 다만 그 계단이
    **순백 대 남색**으로 붙어 있으면 대비가 최대라 유독 거칠어 보인다.
    ⇒ 계단인 자리(이웃 중 불투명이 적은 자리)만 주변색과 섞는다. 곧은 변은 순백 그대로다.
    """
    wgt = m.astype(np.float32)
    cov = ndimage.uniform_filter(wgt, size=3, mode="nearest")
    num = np.stack(
        [ndimage.uniform_filter(rgb[..., c] * wgt, 3, mode="nearest") for c in range(3)], 2
    )
    den = ndimage.uniform_filter(wgt, 3, mode="nearest")[..., None]
    blur = num / np.maximum(den, 1e-6)
    ring = m & ~ndimage.binary_erosion(m, np.ones((3, 3)))
    w = np.clip((knee - cov) / span, 0, 1) * strength
    w[~ring] = 0
    return rgb * (1 - w[..., None]) + blur * w[..., None]


# ── AI 그림에서 큰 글자만 떼어 오기 ──────────────────────────────────────────
def _segment(rgb, vmax=150, tol=14, tex_min=8, win=25, cell=38):
    """체커 배경을 **질감으로** 가른다 — 격자 모델은 안 통한다(칸 크기가 위아래로 다르다).

    배경 = 중성색(r≈g≈b) · 어둡거나 중간(v≤vmax) · **체커 결이 있다**(국소 고주파).
    글자는 은색·흰색(밝다)이거나 남색(중성이 아니다)이라 다 살아남는다.
    """
    v = rgb.mean(axis=2)
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    d = np.minimum(np.abs(v - np.roll(v, cell, axis=1)), np.abs(v - np.roll(v, -cell, axis=1)))
    tex = ndimage.uniform_filter(d, size=21, mode="nearest")
    cand = (spread <= tol) & (v <= vmax) & (tex >= tex_min)
    cand = ndimage.binary_closing(cand, np.ones((5, 5)))
    lab, _ = ndimage.label(cand)
    sizes = np.bincount(lab.ravel())
    keep = sizes >= 400
    keep[0] = False
    return keep[lab]


def _drop_specks(mask, min_fg=800, min_bg_hole=800):
    lab, _ = ndimage.label(~mask)
    sizes = np.bincount(lab.ravel())
    mask = mask | np.isin(lab, np.flatnonzero((sizes < min_fg) & (np.arange(len(sizes)) > 0)))
    lab, _ = ndimage.label(mask)
    sizes = np.bincount(lab.ravel())
    return mask & ~np.isin(lab, np.flatnonzero((sizes < min_bg_hole) & (np.arange(len(sizes)) > 0)))


def _bleed(rgb, fg, iters=60):
    """배경 자리를 이웃 전경색으로 메운다 — 축소할 때 회색이 배어들지 않게."""
    out = rgb.copy()
    m = fg.copy()
    k = np.ones((3, 3), np.float32)
    for _ in range(iters):
        if m.all():
            break
        nxt = ndimage.binary_dilation(m, np.ones((3, 3), bool))
        need = nxt & ~m
        cnt = ndimage.convolve(m.astype(np.float32), k, mode="nearest")
        for c in range(3):
            acc = ndimage.convolve(out[..., c] * m, k, mode="nearest")
            out[..., c][need] = (acc / np.maximum(cnt, 1))[need]
        m = nxt
    return out


def ai_big_title(src=AI_SRC, band=(92, 309)):
    """AI 그림 → 「하얀마녀」만 (RGBA, 원본 해상도).

    🔴 글자 둘레에 **그림자 얼룩**이 붙어 온다 — AI 가 체커 바닥에 드리운 그림자다.
       글자는 「흰 테 + 남색 테 + 은색 속」뿐이므로 그 셋만 몸통으로 잡고 둘레만 남긴다.
    ⚠ `band` 는 금판 아래 ~ 부제 위. 행 프로파일의 골에서 잡았다.
    """
    rgb = np.asarray(Image.open(src).convert("RGB"), dtype=np.float32)
    bg = _drop_specks(_segment(rgb))
    bg[:4, :] = bg[-4:, :] = True
    bg[:, :4] = bg[:, -4:] = True
    fg = ~_drop_specks(bg)
    v = rgb.mean(axis=2)
    navy = (rgb[..., 2] - rgb[..., 0] > 15) & (v < 190)
    body = ndimage.binary_fill_holes(
        ndimage.binary_closing(fg & ((v > 120) | navy), np.ones((7, 7)))
    )
    lab, _ = ndimage.label(body)
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    body = np.isin(lab, np.flatnonzero(sizes > 3000))
    keep = fg & ndimage.binary_dilation(body, np.ones((5, 5)))
    filled = _bleed(rgb, keep)
    m = keep[band[0] : band[1]]
    ys, xs = np.nonzero(m)
    img = np.dstack(
        [np.clip(filled[band[0] : band[1]], 0, 255).astype(np.uint8), (m * 255).astype(np.uint8)]
    )
    return Image.fromarray(img, "RGBA").crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


# ── 부제 ────────────────────────────────────────────────────────────────────
def _fit_font(txt, path, rows, width, track):
    d0 = ImageDraw.Draw(Image.new("L", (8, 8)))
    lo, hi, best = 6, rows * SS * 3, None
    while lo <= hi:
        mid = (lo + hi) // 2
        f = ImageFont.truetype(path, mid)
        a, b, c, e = d0.textbbox((0, 0), txt, font=f)
        if (e - b) <= rows * SS and (c - a) + track * SS * (len(txt) - 1) <= width * SS:
            best, lo = f, mid + 1
        else:
            hi = mid - 1
    return best


def _open_counter(big, x0, x1, up, dn, ext_up, ext_dn):
    """글자의 **가로로 뚫린 속**을 위로 up · 아래로 dn 줄 넓히고, 위아래 획을 오른쪽으로
    ext_up · ext_dn 칸 늘인다 (제자리 수정).

    🔴 부제는 세로로 1.85배 눌리므로 가로 속이 먼저 메워진다 — 「들」의 ㄷ 이 그랬다.
    첫 덩어리(글자 맨 위 = 초성)에서 **획이 가장 얇은 줄들**을 속으로 보고, 그 위아래로
    넓히되 **기둥 오른쪽만** 지운다. 바깥 실루엣은 그대로 두려는 것이다.
    """
    g = big[:, x0:x1] > 128
    if not g.any():
        return
    lab, _ = ndimage.label(g)
    top = np.nonzero(g.any(axis=1))[0].min()
    row = np.nonzero(g[top + 2])[0]
    if not len(row):
        return
    dm = lab == lab[top + 2, row[0]]
    ys = np.nonzero(dm.any(axis=1))[0]
    cnt = dm.sum(axis=1)
    thin = [y for y in range(ys.min(), ys.max() + 1) if 0 < cnt[y] <= cnt[ys].max() * 0.30]
    # 🔴 **이어진 줄로 묶어야 한다.** 얇은 줄은 획의 뾰족한 끝에도 있어서, 그냥 min/max 를
    #    잡으면 **ㄷ 통째**가 속이 되고 오른쪽이 다 지워져 **ㄴ 이 된다**(실측 2026-09-05).
    runs = []
    for y in thin:
        if runs and y == runs[-1][-1] + 1:
            runs[-1].append(y)
        else:
            runs.append([y])
    runs = [r for r in runs if ys.min() not in r and ys.max() not in r]  # 끝에 닿은 건 획이다
    if not runs:
        return
    hole = max(runs, key=len)
    y0, y1 = hole[0], hole[-1]
    stem_r = np.nonzero(dm[(y0 + y1) // 2])[0].max() + 2
    sl = slice(max(0, y0 - up), y1 + 1 + dn)
    big[sl, x0 + stem_r : x1] = np.where(dm[sl, stem_r:], 0, big[sl, x0 + stem_r : x1])
    # 획을 오른쪽으로 늘인다 — 짧으면 속을 터도 무슨 자음인지 안 읽힌다.
    # 🔴 **줄마다 잉크 폭에 비례해서** 늘인다. 통째로 늘이면 획의 **뾰족한 첫 줄**까지 넓어져
    #    그 위 후광이 솟는다 — 「들」 위에 흰 혹이 생겼다(유저 지적 2026-09-05).
    for (ra, rb), ext in (((ys.min(), y0 - up), ext_up), ((y1 + 1 + dn, ys.max() + 1), ext_dn)):
        if not ext:
            continue
        wide = [int(np.count_nonzero(big[y, x0:x1] > 128)) for y in range(ra, rb)]
        top = max(wide) or 1
        for y, wd in zip(range(ra, rb), wide, strict=True):
            xr = np.nonzero(big[y, x0:x1] > 128)[0]
            if len(xr):
                e = round(ext * wd / top)
                big[y, x0 + xr.max() : min(x1, x0 + xr.max() + e)] = 255


def subtitle(
    txt=SUB_TEXT,
    path=SUB_FONT,
    rows=SUB_ROWS,
    ink_rows=SUB_INK,
    width=252,
    ink=NAVY,
    edge=(255, 255, 255),
    lo=0.25,
    hi=1.0,
    cut=0.30,
    halo=SUB_HALO,
    squash=SUB_SQUASH,
    track=SUB_TRACK,
):
    """부제 띠.

    🔴 원본 부제는 「까만 글자 + 흰 테」가 아니라 **거의 흰 글자에 어두운 심**이다
       (흰 935 : 어둠 310 = 3:1). 1비트로 자르면 대비가 두 배라 **지글거린다** ⇒ 계조를 남긴다.
    ⚠ `squash` 는 세로로 눌러 가로를 벌린다 — 원본 부제가 246×11 로 아주 납작해서다.
    ⚠ `ink_rows < rows` 로 두는 이유: 판이 글자와 같은 높이면 **테가 잘려** 받침 아래가
       뭉툭해진다. 글자는 10줄, 판은 14줄.
    🔴 테를 **네모 커널**로 부풀리면 아래가 일자로 각진다 ⇒ **타원**(눌린 원)으로.
    """
    tall = max(1, round(rows * squash))
    inkh = max(1, round((ink_rows or rows) * squash))
    f = _fit_font(txt, path, inkh, width, track)
    img = Image.new("L", (width * SS, tall * SS), 0)
    d = ImageDraw.Draw(img)
    ws = [d.textlength(c, font=f) for c in txt]
    _, b, _, e = d.textbbox((0, 0), txt, font=f)
    x = (img.width - (sum(ws) + track * SS * (len(txt) - 1))) / 2
    y = (img.height - (e - b)) / 2 - b
    boxes = {}
    for ch, cw in zip(txt, ws, strict=True):
        d.text((x, y), ch, font=f, fill=255)
        boxes[ch] = (int(x), int(x + cw) + 4)
        x += cw + track * SS
    big = np.asarray(img).copy()
    for ch, k in SUB_OPEN.items():
        if ch in boxes:
            _open_counter(big, *boxes[ch], *k)
    ry, rx = max(1, round((SS + halo) * squash / 2)), max(1, round((SS + halo) / 2))
    yy, xx = np.ogrid[-ry : ry + 1, -rx : rx + 1]
    ringbig = ndimage.grey_dilation(big, footprint=(yy / ry) ** 2 + (xx / rx) ** 2 <= 1.0)

    def down(z):
        return np.clip(
            np.asarray(Image.fromarray(z).resize((width, rows), Image.LANCZOS)).astype(np.float32)
            / 255,
            0,
            1,
        )

    cov, ring = down(big), down(ringbig)
    t = np.clip((cov - lo) / (hi - lo), 0, 1)
    col = np.stack([edge[i] + (ink[i] - edge[i]) * t for i in range(3)], axis=2)
    al = ring >= cut
    out = np.dstack([np.clip(col, 0, 255).astype(np.uint8), (al * 255).astype(np.uint8)])
    out[~al] = 0
    ys, xs = np.nonzero(al.any(axis=1))[0], np.nonzero(al.any(axis=0))[0]
    out = out[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    # ⚠ 맨 윗줄에 **외딴 후광**이 남는다 — 「하」「영」「들」 꼭대기가 1px 솟아 혹처럼 보인다
    #    (유저 지적 2026-09-05, 8px). 글줄 전체에 비해 성긴 윗줄은 걷는다.
    while out.shape[0] > 2 and (out[0, :, 3] > 0).sum() < 12:
        out = out[1:]
    out[..., :3] = _soften_edge(out[..., :3].astype(np.float32), out[..., 3] > 0, 1.0)
    return Image.fromarray(out, "RGBA")


# ── 로고 ────────────────────────────────────────────────────────────────────
def _runs(mask):
    col = mask.any(axis=0)
    out, s = [], None
    for x, v in enumerate(col):
        if v and s is None:
            s = x
        if not v and s is not None:
            out.append((s, x))
            s = None
    if s is not None:
        out.append((s, len(col)))
    return out


def make_logo():
    orig = Image.open(f"{SPEC}/title_DATA5_3_260x76_8bpp.png").convert("RGBA")
    src = np.asarray(ai_big_title())
    a = src[..., 3] > 0
    col = src[..., :3].copy()
    a2 = ndimage.binary_dilation(a, _disk(src.shape[1] / BIG_W))  # 흰 테 +1px
    col[a2 & ~a] = 255  # ⚠ **원본 해상도에서** 부풀린다
    b = Image.fromarray(np.dstack([col, (a2 * 255).astype(np.uint8)]), "RGBA").resize(
        (BIG_W, BIG_H), Image.LANCZOS
    )
    arr = np.asarray(b).astype(np.float32)
    cov = arr[..., 3] / 255
    m = arr[..., 3] >= 128
    # 오프닝 로고와 **같은 색 손질**(유저: 「타이틀은 둘 다 맞춰줘」 2026-09-06) — JP 타이틀 로고에서
    # 잰 깊이별 색·세로 곡선을 입히고 중앙값으로 잡티를 지운다. 기하(테 1px·자간·자리)는 그대로.
    _metal_shade(
        arr,
        m & (ndimage.distance_transform_edt(m) > 1),
        blur=SMALL["blur"],
        table=JP_SMALL_RGB,
        vert=JP_SMALL_VERT,
        cfg=SMALL,
    )
    # 🔴 줄인 **뒤에** 바깥 1겹을 순백으로 못 박는다 — 안 그러면 가장자리가 회색으로
    #    내려앉아 테가 **이빨 빠진** 것처럼 끊긴다.
    arr[m & ~ndimage.binary_erosion(m, np.ones((3, 3)))] = (255, 255, 255, 255)
    if SOFT:
        # 흰 테와 남색이 한 칸에 255→30 으로 떨어져 곡선이 계단졌다 ⇒ **둘째·셋째 겹만** 흐린다.
        # ⚠ 알파를 가중치로 흐린다 — 안 그러면 투명이 섞여 테가 어두워진다.
        wgt = m.astype(np.float32)
        num = np.stack(
            [ndimage.uniform_filter(arr[..., c] * wgt, 3, mode="nearest") for c in range(3)], 2
        )
        blur = num / np.maximum(ndimage.uniform_filter(wgt, 3, mode="nearest")[..., None], 1e-6)
        dist = ndimage.distance_transform_edt(m)
        wm = np.zeros_like(wgt)
        wm[(dist > 1) & (dist <= 2)] = SOFT
        wm[(dist > 2) & (dist <= 3)] = SOFT * 0.5
        arr[..., :3] = arr[..., :3] * (1 - wm[..., None]) + blur * wm[..., None]
    arr[..., :3] = _soften_edge(arr[..., :3], m, EDGE)
    edge = m & (cov < 0.98)  # 가장자리를 커버리지만큼 어둡게 — 오프닝과 같은 AA
    arr[edge, :3] *= np.clip(cov[edge], 0.35, 1.0)[:, None] ** SMALL["aa"]
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    arr[~m] = 0
    arr[..., 3] = m * 255

    # ⚠ 자간은 **줄인 뒤에** 고르게 맞춘다 — 원본 해상도에서 고르게 놓아도 4.3배 축소의
    #    소수점 때문에 2·2·1 이 된다.
    rr = _runs(arr[..., 3] > 0)
    widths = [e - s for s, e in rr]
    gap = max(1, round((BIG_W - sum(widths)) / (len(rr) - 1)))
    big_w = sum(widths) + gap * (len(rr) - 1)
    laid = np.zeros((BIG_H, big_w, 4), np.uint8)
    x = 0
    for s, e in rr:
        laid[:, x : x + (e - s)] = arr[:, s:e]
        x += (e - s) + gap

    sub = subtitle()
    cv = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cv.alpha_composite(Image.fromarray(laid, "RGBA"), ((W - big_w) // 2, TOP))
    cv.alpha_composite(sub, ((W - sub.width) // 2, SUB_BOTTOM - sub.height))
    out, n = _fit_palette(np.asarray(cv), first=185, plate=np.asarray(orig)[:TOP])
    return Image.fromarray(
        out, "RGBA"
    ), f"자간 {gap} · 큰 글자 폭 {big_w} · 부제 폭 {sub.width} · 색 {n}"


# JP 원본(OP_MAIN.BIN[19]) 몸통의 명도 실측 — 가장자리에서 안쪽으로 깊이별 · 글자 세로 위치별.
# 우리 원천은 「밝은 속 + 짙은 남색 윤곽」이라 경계가 딱딱했다(유저 지적 2026-09-05):
# 깊이 2~3 이 41~49(JP 87~97), 속이 145~157(JP 135). 곡선을 통째로 옮겨 붙인다.
# 🔴 **색까지** 옮긴다. 명도만 맞추고 우리 남색 (0,0,24) 에 비율을 곱했더니 (0,0,87) — 어두운 띠가
#    **파랗게** 됐다(유저 지적 2026-09-05 — B-R 이 JP +30 인데 우리는 +80). JP 띠는 거의 무채색이다.
# ⚠ 표는 **기하로** 잰 것이다 — 알파의 바깥 2px 만 테, 나머지 전부 몸통. 「흰색이 아닌 픽셀」로
#    재면 JP 의 밝은 하이라이트가 테로 빠져 곡선이 납작해진다(띠 63→76, 속 170→139 로 잘못 봤다).
JP_DEPTH_RGB = {
    1: (91, 95, 119),
    2: (50, 54, 85),
    3: (78, 82, 108),
    4: (125, 128, 144),
    5: (151, 152, 162),
    6: (168, 169, 174),
    7: (161, 162, 168),
    8: (150, 153, 167),
}
# 타이틀 화면 로고(DATA5[3], 260×76) 의 JP 실측 — 기하(바깥 1px 테)로 잰 깊이별 RGB · 세로 곡선.
# 오프닝(400×118)과 **다른 그림**이라 표도 따로 잰다. 깊이 1 이 밝은 건 1px 테 안쪽 첫 줄이 아직
# 흰빛을 띠기 때문 — JP 가 그렇다.
JP_SMALL_RGB = {
    1: (182, 184, 196),
    2: (71, 76, 105),
    3: (114, 116, 134),
    4: (141, 142, 153),
    5: (151, 152, 162),
    6: (155, 157, 166),
    7: (156, 158, 168),
    8: (154, 156, 169),
}
JP_SMALL_VERT = [140, 154, 158, 160, 128, 127, 108, 100]
# ⚠ 흐림 둘(첫 흐림 · 띠 흐림)은 0.4 — 오프닝 값(0.7·0.8)을 그대로 쓰면 1px 띠가 녹아 121 이 된다
#    (JP 84). 0.4 면 97. 오프닝에서 파란 선을 만든 건 「띠 흐림 빼기 + 속 흐림 + 구멍 테」의 합이었고,
#    여기선 속 흐림·구멍 뚫기를 안 하므로 검정 배경에서도 선이 안 뜬다(실측 2026-09-06).
SMALL = {
    "blur": 0.4,
    "tex_med": 3,
    "tex_clip": 0.6,
    "band_blur": 0.4,
    "band_med": False,
    "inner_blur": 0.0,
    "sharpen": 0.6,  # JP 타이틀 선명도 44.2, 0 이면 33.7
    "aa": 1.0,
}
JP_VERT = [153, 163, 171, 160, 136, 121, 119, 147]  # 위→아래 8구간, 금속 반사의 어두운 띠가 가운데


def _metal_shade(arr, body, blur=0.7, cap=235, table=None, vert=None, cfg=None):
    """몸통 색을 JP 의 깊이별 **색**·세로 명도 곡선에 맞추고 살짝 흐려 경계를 눅인다 (제자리).

    깊이마다 **색은 JP 평균 RGB 를 쓰고**, 우리 픽셀은 그 깊이 평균 대비 밝기 비율(질감)만
    남긴다. 순서: **흐림 → 세로 곡선 → 깊이 색(두 번)**. 흐림을 뒤에 두면 어두운 띠가
    속으로 번져 맞춰 둔 속이 다시 어두워진다(실측 95~122).
    """
    table = table or JP_DEPTH_RGB
    vert = vert or JP_VERT
    cfg = cfg or OP
    if blur:
        w = ndimage.gaussian_filter(body.astype(np.float32), blur)
        for c in range(3):
            ch = np.where(body, arr[..., c], 0).astype(np.float32)
            arr[body, c] = (ndimage.gaussian_filter(ch, blur) / np.maximum(w, 1e-6))[body]
    ys = np.nonzero(body.any(axis=1))[0]
    if len(ys) > 1:
        yf = np.clip((np.arange(arr.shape[0]) - ys.min()) / (ys.max() - ys.min()), 0, 1)
        prof = np.interp(yf, np.linspace(0, 1, len(vert)), vert) / np.mean(vert)
        arr[body, :3] *= prof[:, None].repeat(arr.shape[1], 1)[body, None]
    d = np.round(ndimage.distance_transform_edt(body)).astype(int)
    kmax = max(table)
    for _ in range(2):
        # 🔴 질감 비율을 **픽셀 그대로** 쓰면 원천의 노이즈가 곱해져 띠 안쪽이 지글거린다
        #    (유저 지적 2026-09-06 「잡티」). 흐린 명도로 비율을 구하고 폭을 묶어 **결이 넓은
        #    그라데이션만** 남긴다.
        # 🔴 흐림(gaussian)으로 잡티를 지우면 **원천의 어두운 윤곽·ㅇ 속 고리까지 같이 사라져**
        #    글자가 납작한 회색 덩어리가 된다(실측 2026-09-06). 잡티는 지우고 구조는 남기는 건
        #    **중앙값 필터**다 — 외딴 점만 없어지고 띠·고리는 그대로다.
        raw = arr[..., :3].mean(axis=2)
        fill = np.where(body, raw, raw[body].mean())
        lum = ndimage.median_filter(fill, size=cfg["tex_med"])
        target = np.zeros_like(arr[..., :3])
        ratio = np.ones(arr.shape[:2], np.float32)
        for k, rgb in table.items():
            sel = body & ((d == k) if k < kmax else (d >= k))
            if sel.any():
                # 🔴 JP 표의 어두운 띠는 남색 기운(B-R +25~35)이 있는데 화면에선 **파랗게** 읽힌다
                #    (유저 지적 2026-09-07). 명도만 두고 색을 `chroma` 만큼만 남긴다 — 0 이면 무채색.
                g = sum(rgb) / 3.0
                target[sel] = [g + (v - g) * cfg.get("chroma", 0.0) for v in rgb]
                ratio[sel] = lum[sel] / max(1.0, lum[sel].mean())
        ratio = np.clip(ratio, 1 - cfg["tex_clip"], 1 + cfg["tex_clip"])
        # 깊이 단계 사이가 계단지지 않게 목표색을 흐린다(몸통 안에서만)
        w = ndimage.gaussian_filter(body.astype(np.float32), cfg["band_blur"])
        for c in range(3):
            target[..., c] = ndimage.gaussian_filter(
                np.where(body, target[..., c], 0), cfg["band_blur"]
            ) / np.maximum(w, 1e-6)
        arr[body, :3] = np.clip(target[body] * ratio[body, None], 0, cap)
    if cfg.get("sharpen"):
        # 흐림·중앙값을 거치면 은색이 물러진다(유저: 「조금 흐릿하다」) ⇒ 몸통 안에서만 언샤프.
        # 잡티를 지운 **뒤에** 세우므로 노이즈는 안 되살아난다. 테(바깥 2px)는 건드리지 않는다.
        r = cfg.get("sharpen_r", 1.0)
        w = ndimage.gaussian_filter(body.astype(np.float32), r)
        for c in range(3):
            ch = np.where(body, arr[..., c], 0).astype(np.float32)
            low = ndimage.gaussian_filter(ch, r) / np.maximum(w, 1e-6)
            arr[body, c] = np.clip(
                arr[body, c] + cfg["sharpen"] * (arr[body, c] - low[body]), 0, 255
            )


def make_logo_op():
    """오프닝 끝의 큰 로고(400×118) — 금판은 **그 그림 것**을 그대로 쓴다."""
    src = np.asarray(ai_big_title())
    a = src[..., 3] > 0
    col = src[..., :3].copy()
    # 🔴 AI 원천엔 **흰 테가 이미 그려져 있고 두께가 고르지 않다.** 그 위에 또 두르면 테가
    #    「AI 것 + 내 것」이 돼 두껍고 들쭉날쭉해진다(실측 3.0, 2~4 — 유저 지적 2026-09-05).
    #    ⇒ **어두운 몸통**(흰색이 아닌 자리; 속의 은색 하이라이트는 메워서 되살린다)에서부터
    #      한 반지름으로 두른다. 그러면 두께 = 반지름이고 균일하다. 원천의 흰 테는 버린다.
    white = a & (src[..., :3].min(axis=2) >= 200)
    a = ndimage.binary_fill_holes(a & ~white) & a
    col[white] = 255
    k = src.shape[1] / OP["big_w"]
    up = 3
    f = (
        np.asarray(
            Image.fromarray((a * 255).astype(np.uint8)).resize(
                (a.shape[1] * up, a.shape[0] * up), Image.LANCZOS
            )
        ).astype(np.float32)
        / 255
    )
    sil = ndimage.binary_closing(
        ndimage.gaussian_filter(f, OP["smooth"] * up) >= 0.5, _disk(k * 2.5 * up)
    )
    # 열기 — 원천 그림의 **가시**(「녀」의 ㄴ 위에 몇 px 튀어나온 것, 유저 지적 2026-09-06)를 깎는다.
    # 반지름은 획 두께보다 훨씬 작아야 한다 — 획은 그대로, 가시만 없어진다.
    sil = ndimage.binary_opening(sil, _disk(k * 0.9 * up))
    rim = ndimage.binary_dilation(sil, _disk(k * OP["rim"] * up))
    a2 = (
        np.asarray(
            Image.fromarray((rim * 255).astype(np.uint8)).resize(a.shape[1::-1], Image.LANCZOS)
        )
        >= 128
    )
    col[a2 & ~a] = 255
    # 🔴 원천은 AI 의 흰 테까지 잡은 상자라 내 테(더 얇다)로 갈면 **위아래에 빈 줄이 남는다** —
    #    알파가 36~100 에 그쳐 JP(35~101)보다 위아래 한 줄씩 모자라고 부제와 4행 떴다(유저 지적
    #    2026-09-06). 새 테의 상자로 다시 잘라 띠 67행을 꽉 쓴다.
    ys = np.nonzero(a2.any(axis=1))[0]
    col, a2 = col[ys.min() : ys.max() + 1], a2[ys.min() : ys.max() + 1]
    b = Image.fromarray(np.dstack([col, (a2 * 255).astype(np.uint8)]), "RGBA").resize(
        (OP["big_w"], OP["big_h"] - OP["pad_top"] - OP["pad_bot"]), Image.LANCZOS
    )
    P = OP["margin"]  # 테가 몸통 상자 밖으로 나갈 여백 — 좌우는 캔버스의 (400-392)/2 = 4 가 상한
    arr = np.pad(np.asarray(b).astype(np.float32), ((P, P), (P, P), (0, 0)))
    cov = arr[..., 3] / 255  # LANCZOS 축소가 남긴 **진짜 커버리지** — 아래 가장자리 눅이기에 쓴다
    m = arr[..., 3] >= 128
    a = a[ys.min() : ys.max() + 1]
    body = np.pad(
        np.asarray(
            Image.fromarray((a * 255).astype(np.uint8)).resize(
                (OP["big_w"], OP["big_h"] - OP["pad_top"] - OP["pad_bot"]), Image.LANCZOS
            )
        )
        >= 128,
        P,
    )
    _metal_shade(arr, m & (ndimage.distance_transform_edt(m) > 2))  # 테 안쪽 몸통만
    arr[m & (ndimage.distance_transform_edt(m) <= 2)] = (255, 255, 255, 255)  # 바깥 2겹 순백
    # 0.4 로는 「마」의 ㅁ·ㅏ 테에 계단이 남았다(유저 지적 2026-09-06) — 작은 로고(0.7)보다 더 눅인다
    arr[..., :3] = _soften_edge(arr[..., :3], m, OP["edge"])
    # 🔴 1비트 알파의 계단은 σ 나 눅임 강도로는 안 사라진다(실측: 넷 다 같았다). JP 가 쓰는
    #    수법 — **가장자리 픽셀을 커버리지만큼 어둡게**(JP 경계에도 회색 픽셀이 281개다). 배경이
    #    검정·주황이라 어두운 쪽으로 섞이면 계단이 녹아 보인다(유저 요청 2026-09-06).
    edge = m & (cov < 0.98)
    arr[edge, :3] *= np.clip(cov[edge], 0.35, 1.0)[:, None] ** OP["aa"]
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    arr[~m] = 0
    arr[..., 3] = m * 255
    # 🔴 자간은 **몸통** 기준이다 — 테까지 재면 테가 두꺼워질수록 글자가 벌어진다.
    #    테는 옆 글자 쪽으로 P 만큼 삐져나가고, 겹치면 서로 얹힌다(원본도 그렇다).
    rr = [(s_, e_) for s_, e_ in _runs(body) if e_ - s_ > 10]
    widths = [e - s for s, e in rr]
    gap = max(1, round((OP["big_w"] - sum(widths)) / (len(rr) - 1)))
    big_w = sum(widths) + gap * (len(rr) - 1)
    laid = np.zeros((arr.shape[0], big_w + 2 * P, 4), np.uint8)
    x = P
    for s_, e_ in rr:
        crop = arr[:, s_ - P : e_ + P]
        dst = laid[:, x - P : x - P + crop.shape[1]]
        sel = crop[..., 3] > 0
        dst[sel] = crop[sel]
        x += (e_ - s_) + gap
    sub = subtitle(rows=OP["sub_rows"], ink_rows=OP["sub_ink"], width=OP["w"] - 8)
    plate = np.asarray(op_plate())
    cv = Image.new("RGBA", (OP["w"], OP["h"]), (0, 0, 0, 0))
    cv.alpha_composite(
        Image.fromarray(laid, "RGBA"), ((OP["w"] - big_w) // 2 - P, OP["top"] + OP["pad_top"] - P)
    )
    cv.alpha_composite(sub, ((OP["w"] - sub.width) // 2, OP["sub_bottom"] - sub.height))
    a2 = np.asarray(cv).copy()
    a2[: OP["top"]] = plate[: OP["top"]]  # 금판은 색 줄이기 **전에** 붙인다
    out, _ = _fit_palette(a2, first=235)  # 계조를 살리려면 색이 더 필요하다(JP 몸통 132색)
    out[: OP["top"]] = plate[: OP["top"]]  # …그리고 뒤에 다시 (색이 흔들리지 않게)
    return Image.fromarray(
        out, "RGBA"
    ), f"자간 {gap} · 큰 글자 폭 {big_w} · 부제 폭 {sub.width} · 색 {_colors(out)}"


def op_plate():
    """오프닝 로고의 금판 — 원본 그림에서 그대로 떠 온다."""
    import dump_tim
    import tim as timmod

    lba, size = common.iso_files("ed3")["/M01.DAT"]
    data = common.read_lba("ed3", lba, size)
    _, ents = common.arc_parse(data)
    m = {e[0]: (e[1], e[2]) for e in ents}
    off, sz = m[next(k for k in m if k.endswith("OP_MAIN.BIN"))]
    _, ts = dump_tim.images(bytes(data[off : off + sz]))
    return timmod.to_image(ts[19][1]).convert("RGBA")


# ── 버튼 ────────────────────────────────────────────────────────────────────
def _btn_src(idx):
    return Image.open(f"{SPEC}/title_DATA5_{idx}_174x24_8bpp.png").convert("RGBA")


def _text_mask(a, band=(4, 20)):
    """원본 일본어 글자 자리 — 밝은 획 + 그 둘레의 검은 테.

    ⚠ 넉넉히 잡는다. 좁게 잡으면 획의 어두운 부분이 남아 **옛 글자가 유령처럼** 비친다.
    """
    v = a.mean(axis=2)
    bright = np.zeros(v.shape, bool)
    bright[band[0] : band[1]] = v[band[0] : band[1]] > 140
    dark = (v < 60) & ndimage.binary_dilation(bright, np.ones((9, 9)))
    m = ndimage.binary_dilation(bright | dark, np.ones((3, 3)))
    m[: band[0]] = m[band[1] :] = False
    return m


def _free_cols(a, w):
    free = np.nonzero(~_text_mask(a).any(axis=0))[0]
    return free[(free >= EDGE_CUT) & (free < w - EDGE_CUT)]


def _synth(res, width, rng):
    """원본 잔결과 **같은 주파수 성질**의 무늬를 만든다 — 진폭만 빌리고 위상은 새로 뽑는다.

    조각을 되접어 깔면 **거울 대칭**이 보이고, 흰 잡음은 **소금·후추**가 된다. 셋 다 밟았다.
    ⚠ 세로 크기는 표본과 같아야 주파수 축이 맞는다 — 가로만 늘린다.
    """
    h, w = res.shape
    P = np.abs(np.fft.fft2(res))
    fx, tx = np.fft.fftfreq(w), np.fft.fftfreq(width)
    order = np.argsort(fx)
    Pi = np.stack([np.interp(tx, fx[order], P[i][order], period=1.0) for i in range(h)])
    Pi *= np.sqrt(width / w)
    out = np.fft.ifft2(Pi * np.exp(1j * rng.uniform(0, 2 * np.pi, (h, width)))).real
    return out * (res.std() / max(out.std(), 1e-6))


def button_plate(idx, band=(4, 20), grain_from=1, seed=11, feather=2, amount=0.7, dim=1.0):
    """판을 다시 만든다 — 행마다 밝기 중앙값 + 합성 결.

    🔴 밝기는 **글자가 없는 픽셀 전부**에서 잰다. 「글자가 하나도 없는 열」만 쓰면 그건
       판의 양끝(밝은 테)뿐이라 판이 통째로 뜬다(평균 119/86/57 vs 원본 80/54/34).
    🔴 결은 **곱으로** 얹는다 — 더하면 채널마다 세기가 달라 **올리브(초록끼)** 가 돈다.
    🔴 **알파 구멍을 메운다** — 원본 판의 투명 점이 우리 글자 밑에서 드러난다.
    ⚠ 글자 자리만 고치면 옛 글자 사이의 얼룩이 **밝은 세로줄**로 도드라진다 ⇒ 띠를 통째로.
    """
    src = _btn_src(idx)
    a = np.asarray(src)[..., :3].astype(np.float32)
    alpha = np.asarray(src)[..., 3].copy()
    h, w = a.shape[:2]
    g = np.asarray(_btn_src(grain_from).convert("RGB")).astype(np.float32)
    mt = _text_mask(a)
    base = np.stack(
        [
            np.median(a[y][~mt[y]], axis=0) if (~mt[y]).any() else np.median(a[y], axis=0)
            for y in range(h)
        ]
    )
    gfree = _free_cols(g, w)
    res = g[:, gfree] - np.median(g[:, gfree], axis=1)[:, None, :]
    lum = res.mean(axis=2)
    t = _synth(lum, w, np.random.default_rng(seed))
    # ⚠ 결의 세기는 **어둡게 하기 전** 밝기로 잰다 — 안 그러면 어두운 판에서 결만 세진다.
    k = amount * lum.std() / max(float(np.median(base.mean(axis=1))), 1e-6)
    new = (base * dim)[:, None, :] * (1.0 + (t / max(t.std(), 1e-6) * k)[..., None])

    wgt = np.zeros((h, w), np.float32)
    wgt[band[0] : band[1], EDGE_CUT : w - EDGE_CUT] = 1.0
    if feather:  # ⚠ 띠 경계를 깃털처럼 — 안 그러면 가로줄이 생긴다
        wgt = ndimage.uniform_filter(wgt, size=2 * feather + 1, mode="constant")
        wgt[band[0] + feather : band[1] - feather, EDGE_CUT + feather : w - EDGE_CUT - feather] = (
            1.0
        )
    out = a * (1 - wgt[..., None]) + new * wgt[..., None]
    op = alpha > 0
    alpha[ndimage.binary_fill_holes(op) & ~op] = 255
    return np.clip(out, 0, 255).astype(np.uint8), alpha


def _neodgm(txt, size=BTN_SIZE):
    f = ImageFont.truetype(NEODGM, size)
    img = Image.new("L", (500, 60), 0)
    ImageDraw.Draw(img).text((20, 10), txt, font=f, fill=255)
    m = np.asarray(img) > 100
    ys, xs = np.nonzero(m.any(axis=1))[0], np.nonzero(m.any(axis=0))[0]
    return m[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]


def make_button(idx, txt):
    """글자를 판에 **새긴다** — 검은 테가 아니라 엠보싱이다.

    원본 실측(판 평균 74): 잉크의 **왼 84 · 위 83**(밝다) · **오른 53 · 아래 70**(어둡다)
    — 왼위에서 빛이 온다.
    ⚠ 중심은 10 이다. 원본 잉크는 11줄인데 우리 글자는 13줄이라, 원본과 같은 11 에 맞추면
      아래가 무겁게 보인다 — 줄 수가 다르면 **bbox 가 아니라 눈에 맞춘다.**
    """
    plate, alpha = button_plate(idx, dim=BTN_DIM[idx])
    m = _neodgm(txt)
    h, w = plate.shape[:2]
    gh, gw = m.shape
    assert gw <= w - 6, f"{txt} 가 버튼을 넘는다 {gw} > {w - 6}"
    ink = np.zeros((h, w), bool)
    top = BTN_CENTER - gh // 2
    ink[top : top + gh, (w - gw) // 2 : (w - gw) // 2 + gw] = m
    sh = np.roll(np.roll(ink, 1, 0), 1, 1) & ~ink  # 오른아래 그림자
    hl = np.roll(np.roll(ink, -1, 0), -1, 1) & ~ink & ~sh  # 왼위 하이라이트
    out = plate.astype(np.float32)
    out[sh] *= 0.55
    out[hl] *= 1.30
    ys = np.nonzero(ink.any(axis=1))[0]
    for y in ys:
        t = (y - ys.min()) / max(1, ys.max() - ys.min())
        out[y][ink[y]] = tuple(INK_TOP[i] + (INK_BOT[i] - INK_TOP[i]) * t for i in range(3))
    rgba = np.dstack([np.clip(out, 0, 255).astype(np.uint8), alpha])
    res, n = _fit_palette(rgba)
    return Image.fromarray(res, "RGBA"), f"글자 {gw}x{gh} · 색 {n}"


# ── 진입점 ──────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="커밋된 PNG 와 바이트 대조만")
    a = ap.parse_args()
    jobs = []
    if os.path.exists(AI_SRC):
        jobs.append(("title_logo.png", make_logo))
        jobs.append(("title_logo_op.png", make_logo_op))
    else:
        print(f"⬜ 로고는 건너뛴다 — {AI_SRC} 가 없다(머신 전용). 커밋된 PNG 가 정본이다.")
    for idx, txt, name in BUTTONS:
        jobs.append((name, lambda i=idx, t=txt: make_button(i, t)))

    bad = 0
    for name, fn in jobs:
        im, note = fn()
        dst = os.path.join(ASSETS, name)
        if a.check:
            same = os.path.exists(dst) and np.array_equal(
                np.asarray(im), np.asarray(Image.open(dst).convert("RGBA"))
            )
            print(f"  {'✅' if same else '🔴'} {name:26} {note}")
            bad += not same
        else:
            im.save(dst)
            print(f"  → {name:26} {note}")
    if a.check and bad:
        print(f"🔴 {bad}장이 커밋된 PNG 와 다르다")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
