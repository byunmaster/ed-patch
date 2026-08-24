"""타이틀 화면 로고 한글화 — `英雄伝説` → 「영웅전설」.

**자리**(2026-08-22 실측) — `/OPENEND/ED_STA1.DG2`.
⚠ **이름이 함정이다.** `ED_STA1` 은 「엔딩 스태프롤」로 읽히는데 실제로는 **타이틀 화면**이다.
   이름으로 짐작해 후보에서 일찍 뺐다가 한참 헤맸다.
찾은 방법: 타이틀이 뜬 상태에서 **VDP2 VRAM 을 뜨고 그 바이트를 전 파일에서 검색**했다.
파일을 하나씩 열어 보는 것보다 훨씬 빠르다 — 화면에 있는 것은 반드시 어딘가에서 왔다.

**DG2 포맷** — `"PP"` + 폭(BE16) + 높이(BE16) + 팔레트 512B(RGB555 BE) + 8bpp 선형 픽셀.
검산: 320×240 + 518 = 77,318 = 파일 크기. 압축 없음.

**수법은 PS1 과 같다**(`ps1-ed1+2/tools/patch_gfx_title.py`) — 원본 로고 픽셀을 지우고
**배경을 거리변환 최근접으로 인페인트**한 뒤, 유저 제작 금색 로고를 합성하고 기존 팔레트에
최근접 양자화한다. 배경이 월드맵이라 단색으로는 못 메운다.

    python3 tools/patch_gfx_title.py --apply
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

sys.path.insert(0, common.ROOT)
from shared.gfx import inpaint as gfx_inpaint
from shared.gfx import logo as gfx_logo

DG2 = "/OPENEND/ED_STA1.DG2"
LOGO_PNG = os.path.join(common.ROOT, "shared", "assets", "title_logo.png")
NEODGM = os.path.join(common.ROOT, "shared", "fonts", "neodgm.ttf")
# 원본 `英雄伝説` 이 놓인 상자 — 배너(위)와 저작권(아래)을 피해 잡는다.
# 원본 로고를 **찾을 범위**(크기가 아니다). 배너는 66행에서 끝나고 아래는 지도라
# 넉넉히 잡되 둘을 안 물게 둔다.
LOGO_BOX = (14, 306, 68, 142)  # x0, x1, y0, y1 (끝 포함)
BRIGHT = 430  # 이 위가 로고 획(R+G+B). 배경 월드맵은 훨씬 어둡다
SMOOTH_MIX = 0.65  # 메울 때 확산 비중 — 가짜 해안선 대신 둘레와 이어지는 쪽을 택한다
MAP_ROWS = (24, 236)  # 인페인트 원천으로 쓸 지도 구간(배너 위·화면 아래는 뺀다)
HALO = 3  # 획 둘레 — 안티에일리어스까지 지운다(2 로는 원본 한자 끝자락이 얼룩으로 남았다)
# 🔴 **PS1 과 통일한 로고 정본**(유저 확정 2026-08-23 「같은 제작사라 같은 에셋을 썼을 것,
#   크기·위치 통일하자」). 두 기종 다 320x240 이고 원본 한자 획 상자 실측도 사실상 같다 —
#   PS1 290x69·중심 y106, 새턴 285x71·중심 y107. **PS1 실측을 정본으로 삼는다.**
#   ⚠ 재서 쓰지 않는다 — 재는 마스크가 배너·월드맵을 물어 기종마다 다르게 틀렸다.
#     PS1 은 배너 아랫단을 세서 상자가 위로 10줄 부풀었고(62..140), 그 탓에 로고가 크고
#     높게 앉았다. 「원본과 같다」는 검증도 같은 마스크로 해서 **틀린 값끼리 맞아떨어졌다.**
#   ⚠ 한자(4.20)와 한글 로고(3.78)는 비율이 달라 둘 다 못 맞춘다 — **상자 안에 들어가는**
#     쪽으로 맞춘다(세로가 걸려 261x69). 유저 요구가 「최대한 원본 글자크기대로」다.
LOGO_FIT = (290, 69)  # 원본 한자 획 상자 (w, h)
LOGO_CY = 106  # 세로 중심 (배너와 저작권 사이)
LOGO_SCALE = 1.0  # 원본 한자 획 상자 대비 — **원본 로고와 같은 크기**(유저 확정 2026-08-23)


def _load_dg2(mm, files, path):
    lba, size = files[path]
    d = common.read_extent(mm, lba, size)
    assert d[:2] == b"PP", "DG2 매직이 아니다"
    w = int.from_bytes(d[2:4], "big")
    h = int.from_bytes(d[4:6], "big")
    pal = np.array(
        [
            (
                ((v := int.from_bytes(d[6 + i : 8 + i], "big")) & 0x1F) << 3,
                ((v >> 5) & 0x1F) << 3,
                ((v >> 10) & 0x1F) << 3,
            )
            for i in range(0, 512, 2)
        ],
        dtype=np.uint8,
    )
    px = np.frombuffer(d[518 : 518 + w * h], dtype=np.uint8).reshape(h, w).copy()
    return bytearray(d), px, pal, w, h


def load(mm, files):
    return _load_dg2(mm, files, DG2)


def _dilate(m, n):
    for _ in range(n):
        out = m.copy()
        out[1:] |= m[:-1]
        out[:-1] |= m[1:]
        out[:, 1:] |= m[:, :-1]
        out[:, :-1] |= m[:, 1:]
        m = out
    return m


def _logo_rgba():
    """타이틀 로고 정본 RGBA.

    ⚠ **원화를 여기서 가공하지 않는다** — 자간 재배치와 알파 만들기는 `shared/gfx/logo.py`
      가 하고 결과를 정본으로 커밋한다. 예전엔 여기서 밝기 임계로 알파를 만들었는데,
      원화가 바뀌면 두 기종이 조용히 갈렸다. 경위는 `shared/assets/README.md`.
    """
    return gfx_logo.title_logo()


def patch(px, pal):
    """제자리 갱신. 반환: (지운 픽셀, 그린 픽셀)."""
    from PIL import Image

    x0, x1, y0, y1 = LOGO_BOX
    box = (slice(y0, y1 + 1), slice(x0, x1 + 1))
    rgb = pal[px].astype(int)
    ink = np.zeros(px.shape, bool)
    ink[box] = rgb[box].sum(2) > BRIGHT
    ink = _dilate(ink, HALO)
    ink[:y0, :] = False  # 배너·저작권은 건드리지 않는다
    ink[y1 + 1 :, :] = False

    # 🔴 **패치 인페인트다 — 확산도 최근접도 아니다.**
    #   최근접은 먼 지도 화소를 길게 끌어와 **ㅇ 구멍 속에 검은 얼룩**을 남겼고(유저 지적
    #   2026-08-22), 확산은 얼룩은 없지만 **지도를 통째로 뭉갠다**(PS1 실측: 밝기 178 → 126).
    #   뭉갠 배경 위에 짙은 테두리의 로고를 얹으면 어두운 데 어두운 게 겹쳐 테두리가 안 보인다.
    #   같은 그림의 성한 지도에서 조각을 떠 오면 해안선·섬이 산다 — `shared/gfx/inpaint.py`.
    #   ⚠ 원천에서 **글자류를 뺀다** — 안 빼면 저작권 문구 조각이 배경에 박힌다(PS1 실측).
    h, w = px.shape
    sat = rgb.max(2) - rgb.min(2)
    text = _dilate((rgb.sum(2) > 560) & (sat < 70) & (np.arange(h)[:, None] > 160), 4)
    src = np.zeros((h, w), bool)
    src[MAP_ROWS[0] : MAP_ROWS[1], :] = True
    src &= ~_dilate(ink, 3) & ~text
    # ⚠ **메운 자리의 밝기를 상자 바깥 지도에 맞춘다** — 안 맞추면 그 자리가 통째로 어두워져
    #   사각형 음영으로 보인다(PS1 실측: 상자 안 133 vs 바깥 190. 유저 지적 2026-08-23).
    near = np.concatenate(
        [
            rgb[max(0, y0 - 6) : y0 - 1, x0 : x1 + 1].reshape(-1, 3),
            rgb[y1 + 2 : y1 + 7, x0 : x1 + 1].reshape(-1, 3),
        ]
    )
    tgt = float(near.astype(int).sum(1).mean()) / 3.0
    filled = gfx_inpaint.fill(
        rgb.astype(np.float32), ink.copy(), src, target_mean=tgt, smooth_mix=SMOOTH_MIX
    )
    d2i = ((pal.astype(np.float32)[None, None] - filled[:, :, None]) ** 2).sum(3)
    px[ink] = d2i.argmin(2).astype(np.uint8)[ink]

    logo = _logo_rgba()
    # ⚠ **잉크 상자로 잘라 놓고 재야 한다** — PNG 의 투명 여백까지 세면 글자가 그만큼 작아진다.
    _la = np.array(logo)
    _ys, _xs = np.nonzero(_la[:, :, 3] > 30)
    logo = logo.crop((int(_xs.min()), int(_ys.min()), int(_xs.max()) + 1, int(_ys.max()) + 1))
    # 🔴 크기·자리는 **PS1 과 통일한 정본**(LOGO_FIT/LOGO_CY)이다 — 재서 쓰지 않는다.
    k = min(LOGO_FIT[0] / logo.width, LOGO_FIT[1] / logo.height) * LOGO_SCALE
    lw, lh = max(1, round(logo.width * k)), max(1, round(logo.height * k))
    logo = logo.resize((lw, lh), Image.LANCZOS)
    la = np.asarray(logo).astype(np.float32)
    # ⚠ 가로는 **화면 한가운데** — 원본 획 중심(162)에 맞췄더니 오른쪽으로 치우쳐 보였다
    #   (유저 지적 2026-08-22). 원본 자체가 화면 중심보다 2px 오른쪽이다.
    ox, oy = (px.shape[1] - lw) // 2, round(LOGO_CY - lh / 2)
    tgt = px[oy : oy + lh, ox : ox + lw]
    base = pal[tgt].astype(np.float32)
    a = la[..., 3:] / 255.0
    blend = _warm_gold(base * (1 - a) + la[..., :3] * a)
    # 🔴 **미사용 팔레트 칸에 로고에 필요한 금색을 넣는다.** 그냥 최근접으로 갈아 끼우면
    #   이 팔레트엔 노란 기 도는 금색이 없어 **주황빛으로 쏠린다**(실측: 원화 G137 →
    #   양자화 G132. 유저 인게임 지적 2026-08-23). 새턴 팔레트는 51칸이 비어 있다.
    cnt = np.bincount(px.ravel(), minlength=len(pal))
    free = [i for i in range(len(pal)) if cnt[i] == 0]
    for i, c in zip(free, _pick_gold(blend, pal, len(free)), strict=False):
        pal[i] = c
    d2 = ((pal.astype(np.float32)[None, None] - blend[:, :, None]) ** 2).sum(3)
    tgt[...] = d2.argmin(2).astype(np.uint8)
    return int(ink.sum()), int((a[..., 0] > 0.02).sum())


# 🔴 금색을 **노란 쪽으로** 민다(PS1 과 같은 값, 유저 확정 2026-08-23).
#   팔레트에 금색을 넣어 G 는 맞췄지만 B 가 +10 높아 탁해 보인다.
GOLD_WARM_G, GOLD_WARM_B = 6, 14


def _warm_gold(comp):
    """R>G>B 인 중간 밝기 화소(=금색)만 노란 쪽으로."""
    a = comp.astype(np.float32).copy()
    lum = a.sum(2)
    m = (a[:, :, 0] > a[:, :, 1]) & (a[:, :, 1] > a[:, :, 2]) & (lum > 180) & (lum < 660)
    a[:, :, 1] = np.where(m, np.clip(a[:, :, 1] + GOLD_WARM_G, 0, 255), a[:, :, 1])
    a[:, :, 2] = np.where(m, np.clip(a[:, :, 2] - GOLD_WARM_B, 0, 255), a[:, :, 2])
    return a


def _pick_gold(comp, pal, n):
    """양자화 오차가 큰 색부터 n 개(오차 합 가중). 무작위 없음 — PS1 과 같은 규칙."""
    if n <= 0:
        return []
    flat = comp.reshape(-1, 3).astype(int)
    q = pal.astype(int)[((pal.astype(int)[None, :, :] - flat[:, None, :]) ** 2).sum(2).argmin(1)]
    err = np.abs(q - flat).sum(1)
    keep = err > 12
    if not keep.any():
        return []
    coarse = (flat[keep] >> 3) << 3
    u, ci = np.unique(coarse, axis=0, return_inverse=True)
    w = np.bincount(np.asarray(ci).ravel(), weights=err[keep], minlength=len(u))
    return [tuple(int(x) for x in u[i]) for i in np.argsort(-w)[:n]]


# 타이틀 화면의 **선택 버튼**도 DG2 다. ⚠ 이름이 `ED_STA*`(엔딩 스태프롤로 읽힌다) 라서
# 여섯 파일을 통째로 잘못 분류하고 있었다 — 실제로는 전부 타이틀 부품이다.
# 선택/미선택이 **파일로 갈려** 있어 상태가 흔들릴 여지가 없다.
PLATES = (
    ("ED_STA2", "영웅전설I"),  # Ⅰ 미선택
    ("ED_STA3", "영웅전설I"),  # Ⅰ 선택(초록)
    ("ED_STA4", "영웅전설II"),  # Ⅱ 미선택
    ("ED_STA5", "영웅전설II"),  # Ⅱ 선택(초록)
)
PLATE_BORDER = 2  # 판 테두리는 남긴다
# 🔴 판 사각은 **손으로 잰 값을 못 박는다**(x0, y0, x1, y1 — 판 바깥 경계).
# 검출(가운데서 이어진 밝은 덩어리)은 배경 지도로 새거나 판을 덜 잡았다 — 넷이 100x30 ·
# 96x28 · 104x30 으로 흔들렸고, 그 상자로 중앙정렬하니 글자가 판 밖으로 밀렸다.
# ⚠ 넷이 같은 사각이 **아니다** — 폭은 96 으로 같은데 Ⅱ 쪽이 2px 오른쪽에 얹혀 있다
# (화면상 자리가 달라 스프라이트 오프셋이 다르다). 열 100~103 은 순백 패딩이라 판이 아니다.
PLATE_RECT = {
    "ED_STA2": (1, 5, 96, 27),
    "ED_STA3": (1, 5, 96, 27),
    "ED_STA4": (3, 5, 98, 27),
    "ED_STA5": (3, 5, 98, 27),
}
# ⚠ 크기도 **못 박는다** — 자동맞춤은 상자마다 다른 값을 골랐다(Ⅰ 20px · Ⅱ 18~19px).
# 유저가 「ed1 과 ed2 폰트크기가 다른것 같은데?」로 잡아냈다. PS1 도 같은 자리에서 같은
# 결론이었다(`patch_gfx_title.PIN_SIZE` 의 영웅전설I/II = 52 로 동일).
# ⚠ Ⅰ/Ⅱ 는 원본처럼 U+2160/2161 로 못 쓴다 — 폰트에 없어 **두부(.notdef)로 그려진다**
# (픽셀 수가 둘 다 184 로 같아 얼핏 정상으로 보였다. 그려 보고 알았다). ASCII I/II 라
# Ⅱ 쪽이 한 글자 넓어지므로, 넓은 쪽이 안 넘치는 크기로 잡는다.
# 🔴 **16px** — PS1 선택 버튼과 같은 크기(유저 확정 2026-08-23).
#   ⚠ 16 인 이유는 「4로 나눠떨어져서」만이 아니다 — **네오둥근모가 16×16 픽셀 폰트**라
#     그 크기에서 리샘플 없이 또렷하다. 17px 는 격자를 벗어나 획이 뭉갠다.
#   실측: 「영웅전설II」 80px < 안쪽 92px (17px 는 86px 이었다).
GLOW_WIDTH = 1  # 선택 판의 밝은 테 두께(최종 px)
BOLD_X = 1  # 판 글자를 가로로 이만큼 불린다 — 굵은 네오둥근모가 없어 합성한다
PLATE_SIZE = 16


# 🔴 **판은 새로 그린다**(유저 확정 2026-08-23, PS1 과 같은 규격). 원본은 넷이 제각각이다 —
#   배경 질감이 다르고 왼쪽 테두리만 굵으며 ED1/ED2 의 같은 상태끼리 배경이 다르다.
#   단색 배경 + 균일 테두리 + 라운드로 다시 그린다.
#   ⚠ 라운드 모서리는 **테두리 색으로 채운다** — 판은 화면에 통째로 얹히므로 잘라낸 자리에
#     뒤 배경을 비출 수가 없다. 어두운 지도 위라 둥글게 읽힌다.
#   ⚠ 판의 **자리·크기는 안 건드린다**(PLATE_RECT). 화면에서 버튼이 밀린다.
PLATE_RADIUS = 4
# 🔴 테두리는 **판 안쪽에 진한 녹색**(유저 확정 2026-08-23, PS1 과 같은 규격).
#   PS1 에서 검정으로 가장자리에 그렸더니 엔진이 잘라 가 화면에 안 보였다. 안쪽으로 들이면
#   기종을 안 타고, 밝은 판에 검정보다 어울린다.
# 🔴 **새턴은 라운드 바깥을 검정으로 채우면 안 된다**(유저 QA 2026-08-24).
#   PS1 은 그렇게 해도 됐다 — 판 아래가 **어두운 바다**라 검정이 묻힌다. 새턴 타이틀은
#   같은 자리가 **밝은 육지**여서 그 검정이 「검은 액자」로 튄다. 데이터는 양쪽이 같은데
#   화면이 갈린다(PS1 판 픽셀을 꺼내 대조해 확인).
#   그래서 라운드 바깥은 **원본 배경(지도)으로 되돌린다.** 상자 바로 위·아래 행이 지도이므로
#   세로로 이어 온다 — 라운드 반경이 4px 뿐이라 이 근사로 충분하다.
#   ⚠ PS1 의 `PLATE_INSET = 1` 도 여기선 0 이다. 그건 **엔진이 바깥 1px 을 잘라 가는**
#     PS1 사정이고, 새턴은 셀을 통째로 그려서 들일 이유가 없다.
# 🔴 테두리는 **상태별로 다르다**(유저 확정 2026-08-23) — 미선택은 진하게, 선택은 밝게.
#   같은 색으로 두니 선택을 오가도 안 변해 어색했다.
# ⚠ 키는 「판이 어두운가」다 — **어두운 판이 미선택**이다. 원본 주석(`cell0 Ⅰsel`)대로
#   밝은 판이 선택이고, 유저도 「선택일 때 테두리가 밝아야 한다」고 확인했다(2026-08-23).
PLATE_BORDER_RGB = {False: (0xA8, 0xC8, 0xB8), True: (0x6F, 0x9A, 0x82)}
PLATE_INSET = 0  # 새턴은 엔진이 안 잘라 간다 — 들일 이유가 없다(PS1 은 1)
PLATE_BORDER_W = 2  # 테두리 굵기 — 버튼처럼 읽힌다(유저 확정 2026-08-23)
# ⚠ 볼록 엠보싱도 해 봤는데 모서리 색이 어색해 **단색 2px** 로 되돌렸다(유저 확정 2026-08-23).


PLATE_BG = {False: (0xEE, 0xF0, 0xEE), True: (0x9A, 0xC0, 0xA9)}  # 미선택 / 선택
PLATE_INK = {False: (0x24, 0x57, 0x37), True: (0x0D, 0x0D, 0x0D)}


def patch_plate(px, pal, text, rect, sel):
    """판을 통째로 다시 그린다. 반환: (지운 화소, 그린 화소)."""
    from PIL import Image, ImageDraw, ImageFont

    x0, y0, x1, y1 = rect
    w, h = x1 - x0 + 1, y1 - y0 + 1
    im = Image.new("RGB", (w, h), PLATE_BG[sel])
    d = ImageDraw.Draw(im)
    k = PLATE_INSET
    # 🔴 테두리는 **두 겹** — 바깥 검정, 그 안쪽에 진한 녹색(유저 확정 2026-08-23).
    #   검정 한 겹만 가장자리에 두면 엔진이 잘라 가 안 보이고, 녹색만 안쪽에 두면 그 바깥에
    #   밝은 여백이 남는다. 두 겹이면 원본의 어두운 경계도 살고 잘려도 녹색이 남는다.
    mk = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mk).rounded_rectangle(
        [k, k, w - 1 - k, h - 1 - k], radius=PLATE_RADIUS, fill=255
    )
    arr = np.asarray(im).copy()
    out = np.asarray(mk) == 0
    if out.any():
        # 라운드 바깥 = 원본 지도. 상자 위·아래 행에서 세로로 이어 온다.
        above = pal[px[max(y0 - 1, 0), x0 : x1 + 1]]
        below = pal[px[min(y1 + 1, px.shape[0] - 1), x0 : x1 + 1]]
        src = np.where((np.arange(h) < h // 2)[:, None, None], above[None], below[None])
        arr[out] = src[out]
    im = Image.fromarray(arr)
    d = ImageDraw.Draw(im)
    bd = PLATE_BORDER_RGB[sel]
    d.rounded_rectangle(
        [k, k, w - 1 - k, h - 1 - k],
        radius=PLATE_RADIUS,
        outline=bd,
        width=PLATE_BORDER_W,
    )
    f = ImageFont.truetype(NEODGM, PLATE_SIZE, layout_engine=ImageFont.Layout.BASIC)
    # 🔴 **가로로 1px 불려 굵게 쓴다**(유저 확정 2026-08-24). 네오둥근모엔 굵은 자형이 없어
    #   합성한다 — 밝은 판에 짙은 글자라 얇은 획이 눌려 보였다.
    #   ⚠ 중앙정렬은 **불린 폭**으로 잰다. 원래 폭으로 재면 오른쪽으로 1px 쏠린다.
    #   ⚠ 안티에일리어스는 살린다 — 문턱으로 자르면 16px 획이 계단진다.
    m = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(m)
    bb = md.textbbox((0, 0), text, font=f)
    md.text(
        ((w - (bb[2] - bb[0] + BOLD_X)) // 2 - bb[0], (h - (bb[3] - bb[1])) // 2 - bb[1]),
        text,
        fill=255,
        font=f,
    )
    a = np.asarray(m).astype(np.float32)
    for k in range(1, BOLD_X + 1):
        a = np.maximum(a, np.roll(np.asarray(m).astype(np.float32), k, axis=1))
    al = (a / 255)[..., None]
    arr = np.asarray(im).astype(np.float32) * (1 - al) + np.array(PLATE_INK[sel], np.float32) * al
    im = Image.fromarray(arr.round().astype(np.uint8))
    comp = np.asarray(im).astype(np.float32)
    d2 = ((pal.astype(np.float32)[None, None] - comp[:, :, None]) ** 2).sum(3)
    px[y0 : y1 + 1, x0 : x1 + 1] = d2.argmin(2).astype(np.uint8)
    return w * h, w * h


def _pal_bytes(pal):
    """(256,3) RGB888 → DG2 팔레트 512B (RGB555 BE)."""
    c = np.asarray(pal).astype(int) >> 3
    v = ((c[:, 2] << 10) | (c[:, 1] << 5) | c[:, 0]).astype(">u2")  # ⚠ R 이 하위 5비트다
    return v.tobytes()


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    _f, mm = common.open_image()
    files = {p: (l, s) for p, l, s in common.iso_files(mm)}
    raw, px, pal, w, h = load(mm, files)
    erased, drawn = patch(px, pal)
    print(f"  {DG2}: {w}x{h} · 로고 {erased} 지움 · 한글 {drawn} 그림")
    if not apply:
        print("  (미리보기만 — 실제로 넣으려면 `--apply`)")
        return
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if not os.path.exists(dst):
        raise SystemExit(f"먼저 자막을 넣는다(patch_title.py --apply) — {dst} 가 없다")
    # ⚠ 팔레트도 함께 쓴다 — 금색을 새로 넣었으므로(빈 칸 활용).
    raw[6:518] = _pal_bytes(pal)
    raw[518 : 518 + w * h] = px.tobytes()
    lba, size = files[DG2]
    with open(dst, "r+b") as f:
        n = common.write_at(f, lba, size, 0, bytes(raw), label="ED_STA1.DG2 타이틀 로고")
    print(f"    → 섹터 {n}")
    for name, text in PLATES:
        praw, ppx, ppal, pw, ph = _load_dg2(mm, files, f"/OPENEND/{name}.DG2")
        e, dr = patch_plate(ppx, ppal, text, PLATE_RECT[name], name in ("ED_STA3", "ED_STA5"))
        praw[518 : 518 + pw * ph] = ppx.tobytes()
        lba, size = files[f"/OPENEND/{name}.DG2"]
        with open(dst, "r+b") as f:
            n = common.write_at(f, lba, size, 0, bytes(praw), label=f"{name}.DG2 선택 버튼")
        print(f"  {name}: {text} · {e} 지움 · {dr} 그림 → 섹터 {n}")


if __name__ == "__main__":
    main()
