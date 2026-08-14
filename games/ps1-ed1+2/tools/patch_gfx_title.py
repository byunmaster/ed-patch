"""타이틀 화면 그래픽 한글화 — 8bpp TIM 픽셀 재작성 (graphics-text 트랙).

PS1 타이틀은 3장의 8bpp TIM(전부 START.DAT, 디스크 섹터 정렬):
  0x50C800 컬렉션(480x240): 대형 英雄伝説 로고 + 英雄伝説Ⅰ/Ⅱ 버튼(각 2상태)
  0x52A000 ED1(390x240):   はじめから/つづきから 버튼(각 2상태)
  0x541000 ED2(390x240):   はじめから/つづきから 버튼(각 2상태)
영문 로고("The Legend of Heroes")·저작권·PRESS START·엠블럼·월드맵은 유지.

로고 방식(2026-07-14, 유저 확정):
  · 유저 제작 금색 로고(assets/title_logo.png, 배경제거 RGBA)를 활용 — 절차적 재현이
    아니라 실제 에셋 합성이라 품질↑(유저 방침 [[title-logo-font]]).
  · 옛 금색 로고 픽셀을 검출→마스크→월드맵 배경 인페인트(거리변환 최근접)→클린 로고
    합성(88%, 박스 중앙)→기존 256색 CLUT에 최근접 양자화.
  · 컬렉션 TIM은 빈 슬롯 6개뿐이나 기존 팔레트에 금색 계조가 풍부해 최근접 매핑으로
    충분(열화 허용 — 유저: 전체 저화질이라 타이틀 열화 OK).

컬렉션 버튼(2026-07-16 최종, 상세 `devlog.md`): 원본 英雄伝説Ⅰ/Ⅱ 버튼을 **보존**하고
내부 일본어 텍스트만 한글로 교체. 여러 방식(이미지에셋·절차적재작도) 반려 후 확정 —
  · emucap 캘리브레이션으로 엔진이 4셀을 1:1(무스케일) 화면 고정슬롯에 blit함을 규명.
  · overwrite_text: 일본어 **획 픽셀만** 버튼 내부색(채널별 p40=바탕 크림)으로 페인트(외부색 안
    당겨와 오염 없음). **테두리 inset 마스크**(가로2·세로3)로 버튼 프레임 베벨은 원본 그대로 보존,
    안쪽만 최소 페인트(딱딱함 완화). 그 위에 한글을 각 버튼 중앙(cx·cy 실측)에 얹는다(COLL_TEXT).
글자색 TEXT_DARK. 선택/비선택 밝기·radius·테두리는 원본 셀 그대로(엔진 특성 상속).
ED1/ED2 알약(처음부터/이어하기)도 같은 원리 — overwrite_text의 gradient=True(금색 세로 그라디언트
행별 보존)·비대칭 pad(우측 ら 잔여)·서브픽셀 dx로 처리(PILL_TEXT).

전제: reinsert_kr_pilot로 만든 KR 이미지 위에 얹는다(build 체인). TIM 픽셀은 원본에서
읽어(START.DAT는 앞 단계가 안 건드림) 대상 디스크에 write-back + EDC.
"""

import os
import struct

import numpy as np
from common import BUILD_DIR, write_user_data
from PIL import Image, ImageDraw, ImageFont
from scan_tim import parse_tim, user_stream
from scipy.ndimage import (
    binary_dilation,
    binary_fill_holes,
    binary_opening,
    distance_transform_edt,
    label,
)

# ⚠ 레이아웃 엔진을 못 박는다 — Pillow 는 Raqm(HarfBuzz)이 있으면 그걸 기본으로 쓰는데,
# 같은 Pillow·FreeType 이어도 Raqm 유무로 **글자 배치가 달라진다**(macOS 휠 없음 / 리눅스 휠 있음).
# 그러면 같은 입력에도 머신마다 다른 이미지가 나온다(2026-08-09 실측: START.DAT 8섹터).
BASIC_LAYOUT = ImageFont.Layout.BASIC


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
LOGO_PNG = os.path.join(ROOT, "assets", "title_logo.png")

COLL_OFF = 0x50C800  # 컬렉션 타이틀 TIM (스트림=디스크 섹터 오프셋)
ED1_OFF = 0x52A000  # ED1 타이틀
ED2_OFF = 0x541000  # ED2 타이틀
# 옛 英雄伝説 로고 bbox. y0=62 — 위 영어박스 "The Legend of Heroes I&II" 하단(y48~60)을
# 침범하면 그 박스 바닥이 인페인트로 깨진다(유저 QA). 로고 실제 시작은 y72라 y62는 갭 안.
LOGO_BOX = (8, 310, 62, 141)
LOGO_SCALE = 0.88  # 한자보다 커서 축소(유저 확정)

# ── 타이틀 폰트 = 네오둥근모 (유저 확정 2026-08-14) ─────────────────────────────
# ⚠ 예전엔 **애플 번들 폰트**(`AppleSDGothicNeo.ttc`)를 시스템 경로에서 찾아 썼다. 두 가지가
# 걸렸다:
#   ① **결정성** — 그 폰트가 없는 머신(이 레포의 리눅스 개발기)에선 빌드가 아예 못 돈다.
#      루트 CLAUDE.md 제1 원칙(같은 입력이면 같은 바이트)이 서지 않는 자리였다.
#   ② **라이선스** — 애플 폰트로 렌더한 그림을 공개 배포하는 셈이었다.
# 네오둥근모는 **OFL 이고 레포 안에 있다**(`shared/fonts/neodgm.ttf`) — 둘 다 풀린다.
# 챕터 카드(`patch_gfx_cards`)가 이미 같은 폰트라 결도 맞는다.
# ⚠ 자형이 바뀌므로 **타이틀은 다시 인게임 확인이 필요하다**(옛 확인분은 2026-07-16).
FONT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared", "fonts", "neodgm.ttf"
)

# ⚠ `index` 는 **TTC 안의 굵기 번호**였다(애플 폰트가 컬렉션이라). 네오둥근모는 단일
# TTF 라 인덱스가 없다 — 굵기는 폰트 자체 하나뿐이다.

# ── 원리(유저 방침): 원본 버튼 보존, 내부 일본어 획만 페인트하고 그 위에 한글을 얹는다 ──
# 버튼을 다시 그리지 않아 이동·크기변화·테두리 위화감이 원천 소멸. 상세는 overwrite_text 참조.
# 한글 글자색. ⚠ **이 값이 화면에 그대로 나가진 않는다** — `quantize_region` 이 원본 CLUT 에서
# 가장 가까운 색으로 갈아 끼운다. 컬렉션 팔레트엔 순검정(idx0)·(8,8,8)·(16,16,16) 이 있는데
# `(32,36,32)`(합 100)는 그보다 밝은 쪽으로 떨어져 **획이 흐려 보였다**(유저 QA 2026-08-14).
TEXT_DARK = (8, 8, 8)
# ⚠ **선명도 보정은 전부 기각**(유저 QA 2026-08-14). 네오둥근모로 바꾼 뒤 글자가 흐려
# 보인다고 해서 셋을 시험했는데 다 화면에서 더 나빴다 — 결론만 남기고 코드는 지운다(YAGNI):
#   · `stroke_width` 로 굵히기 → 버튼이 작아 획이 뭉갰다
#   · 글자색을 더 짙게 → 원본 텍스트 톤과 어긋났다
#   · 알파 감마·임계 자르기 → 계단이 드러나 오히려 거칠어졌다
# 흐림의 원인은 **4x 스프라이트를 1x 로 LANCZOS 축소**하면서 1px 획 가장자리가 반투명으로
# 퍼지는 것이다. 근본 해법은 축소 없이 1x 격자에 직접 굽는 것인데, 그러면 `dx`·`dy`
# 서브픽셀 배치를 잃는다 — 지금은 배치가 더 중요해 축소를 유지한다.
# OVERLAY_ONLY=True면 배경 안 지우고 폰트만 얹음(위치 디버깅용, OVERLAY_COLOR로 대비). False가
# 최종(배경 덮어 일본어 가림, 버튼 밝기 그대로 → 선택 밝음/비선택 짙음 자동 유지).
OVERLAY_ONLY = False
OVERLAY_COLOR = (220, 40, 40)  # 위치 확인용 임시 빨강(OVERLAY_ONLY일 때만)

# ED1·ED2 게임시작 알약 (ix0,ix1,iy0,iy1, 문안, dx, pad). 하단2=비선택·상단뱅크2=선택.
# dx=한글 좌우 보정(서브픽셀, 화면 실측). pad=fill 확장 — 선택은 일본어 ら가 rect 우측 밖에 남아 확장.
PILL_TEXT = [
    (49, 111, 195, 217, "처음부터", 0, (0, 0)),  # 비선택 (iy1=217→높이22=선택과 동일 폰트)
    (225, 287, 195, 218, "이어하기", 0, (0, 0)),  # 비선택
    (
        324,
        383,
        5,
        27,
        "처음부터",
        1.5,
        (0, 2, 0, 0),
    ),  # 선택 — 우측만 살짝 확장(ら 잔여, streak 최소)
    (325, 385, 35, 58, "이어하기", 1, (0, 2, 0, 0)),  # 선택
]
# ── 컬렉션 버튼 파라미터(전부 emucap 실측·유저 QA로 확정, 상세 `devlog.md`) ──
# 엔진은 각 셀을 1:1(무스케일)로 화면 고정 슬롯에 blit → TIM 좌표 = 화면 좌표.
COLL_PAD = (2, 2)  # fill 검출영역 확장(가로,세로) — 일본어를 덮되 아래 INSET이 테두리를 보호.
COLL_RADIUS = 5  # fill 라운드 코너 반경(버튼 모서리 맵 삼각형 보존 → 버튼다운 radius 유지)
# ⭐테두리 보존(유저 QA #72,#74): fill 바깥 (가로,세로) INSET px(=상하좌우 베벨)는 절대 안 칠해
# 테두리를 상태 무관 100% 원본(거친 베벨) 유지. 세로 베벨이 두꺼워 세로 inset 큼. 중앙 flat은 감수.
COLL_FILL_INSET = (3, 4)
# (ix0,ix1,iy0,iy1, 문안, dx). 각 버튼 중앙(cx≈369·cy 실측)에 배치. dx=2(전체): 시각 무게가 왼쪽
# (굵은 영웅전설)이라 오른쪽으로 보정. Ⅱ는 ix1 확장(→416)+dx3: 説Ⅱ가 우측으로 넓어 오른쪽 잔여 청소.
# ⚠ `dy` 는 **눈으로 맞추는 값**이다. 상자 중심과 버튼 중심은 실측으로 정확히 같은데
# (둘 다 셀 안 y16, 원본 버튼 잉크 7~25) 화면에선 글자가 살짝 위로 보였다(유저 QA
# 2026-08-14). 한글은 일본어보다 아래 여백이 커서 잉크 상자 중앙정렬이 시각 중심과
# 어긋난다 — 자동 측정으론 셀마다 값이 흔들려(+2.5~-3.5) 안 모였다. 그래서 손잡이를 둔다.
COLL_TEXT = [
    (325, 413, 5, 27, "영웅전설Ⅰ", 2, 0.5),  # cell0 Ⅰsel  중심 y16
    (325, 413, 35, 57, "영웅전설Ⅰ", 2, 0.5),  # cell1 Ⅰnorm 중심 y46
    (325, 416, 65, 87, "영웅전설Ⅱ", 3, 0.5),  # cell2 Ⅱsel  중심 y76
    (325, 416, 95, 117, "영웅전설Ⅱ", 3, 0.5),  # cell3 Ⅱnorm 중심 y106
]


# ⚠ **폰트에 없는 글자는 `.notdef`(빈 네모)로 조용히 나간다.** 애플 폰트에서 네오둥근모로
# 갈면서 `Ⅰ`(U+2160)·`Ⅱ`(U+2161)가 네모로 떴다(유저 QA 2026-08-14) — 픽셀 폰트엔 로마 숫자가
# 없는 게 보통이다. 아스키로 치환하고, **남은 없는 글자는 빌드를 세운다.**
GLYPH_SUB = {"Ⅰ": "I", "Ⅱ": "II", "Ⅲ": "III"}


def _sub(text):
    for a, b in GLYPH_SUB.items():
        text = text.replace(a, b)
    return text


def _assert_glyphs(text):
    """이 폰트에 없는 글자가 있으면 죽는다 — 네모가 화면에 나가는 것보다 낫다."""
    import numpy as np

    f = ImageFont.truetype(FONT_PATH, 16, layout_engine=BASIC_LAYOUT)

    def ink(ch):
        im = Image.new("L", (32, 32), 0)
        ImageDraw.Draw(im).text((2, 2), ch, font=f, fill=255)
        return np.array(im) > 110

    notdef = ink("\ue000")  # 사용자 정의 영역 — 어느 폰트에도 없다
    bad = [c for c in set(text) if c.strip() and np.array_equal(ink(c), notdef)]
    assert not bad, f"타이틀 폰트에 없는 글자 {bad} — `GLYPH_SUB` 에 치환을 넣거나 폰트를 볼 것"


def _fit_font(draw, text, maxw, maxh, pin=None):
    """상자에 맞는 최대 크기. `pin` 을 주면 그 크기로 고정한다.

    ⚠ **상태(선택/비선택)마다 크기가 달라지면 안 된다.** 상자 높이가 22/23 으로 1px 달라
    자동맞춤이 갈렸고, 커서를 옮길 때 글자가 미세하게 커졌다 작아졌다 했다(유저 QA
    2026-08-14). 같은 문안은 **한 크기로 못 박는다**.
    """
    if pin:
        f = ImageFont.truetype(FONT_PATH, pin, layout_engine=BASIC_LAYOUT)
        return f, draw.textbbox((0, 0), text, font=f)
    for sz in range(maxh, 6, -1):
        f = ImageFont.truetype(FONT_PATH, sz, layout_engine=BASIC_LAYOUT)
        bb = draw.textbbox((0, 0), text, font=f)
        if bb[2] - bb[0] <= maxw and bb[3] - bb[1] <= maxh:
            return f, bb
    f = ImageFont.truetype(FONT_PATH, 7, layout_engine=BASIC_LAYOUT)
    return f, draw.textbbox((0, 0), text, font=f)


# 문안별 고정 폰트 크기 — 상태(선택/비선택)가 달라도 **같은 글자는 같은 크기**여야 한다.
# 값은 자동맞춤이 각 상자에서 고르던 것 중 **작은 쪽**(둘 다 안 넘치는 크기)을 쓴다.
# ⚠ **같은 층의 버튼은 한 크기여야 한다**(유저 지적 2026-08-14). 자동맞춤은 상자마다 다른
# 값을 골랐다 — 처음부터 49/47 · 이어하기 49/48. 상태를 오갈 때 글자가 커졌다 작아졌고,
# 두 버튼끼리도 크기가 달랐다.
#
# 원인은 폰트가 아니라 **상자 치수**다. 이 상자는 버튼이 아니라 *일본어를 지울 영역*이라
# 손으로 재 넣은 값이고, 그 과정에서 1px 씩 어긋나 있다(이어하기 쪽이 iy1 이 1 크다).
# 상자를 다시 재는 대신 **글자 크기를 못 박는다** — 상자는 지우는 용도라 그대로 둬도 된다.
# 값은 네 상자 전부에서 안 넘치는 최댓값이다(알약 47 · 컬렉션 52, 실측).
PIN_SIZE = {
    "처음부터": 47,
    "이어하기": 47,
    "영웅전설I": 52,
    "영웅전설II": 52,
}


def _draw_text(img, text, fill, wfrac=0.80, hfrac=0.62, xoff=0, yoff=0):
    """img 중앙에 글자(폭·높이 프랙션으로 축소해 버튼 안쪽 여백 확보). xoff는 스프라이트(4x) 픽셀
    단위 x 오프셋 — 축소 후 서브픽셀 이동이 된다."""
    text = _sub(text)
    _assert_glyphs(text)
    W, H = img.size
    d = ImageDraw.Draw(img)
    f, bb = _fit_font(d, text, int(W * wfrac), int(H * hfrac), pin=PIN_SIZE.get(text))
    d.text(
        (
            (W - (bb[2] - bb[0])) // 2 - bb[0] + xoff,
            (H - (bb[3] - bb[1])) // 2 - bb[1] + yoff,
        ),
        text,
        fill=fill,
        font=f,
    )


def _pad4(pad):
    """pad를 (좌,우,상,하)로 정규화. int→사방, (가로,세로)→대칭, (좌,우,상,하)→그대로."""
    if isinstance(pad, tuple) and len(pad) == 4:
        return pad
    if isinstance(pad, tuple):
        return pad[0], pad[0], pad[1], pad[1]
    return pad, pad, pad, pad


def overwrite_text(
    comp,
    ix0,
    ix1,
    iy0,
    iy1,
    text,
    wfrac=0.80,
    hfrac=0.60,
    dx=0,
    dy=0,
    pad=0,
    inset=None,
    radius=None,
    gradient=False,
):
    """버튼 내부 일본어 **획 픽셀만** 버튼 내부색으로 칠하고 한글을 얹는다.

    inpaint(최근접) 방식은 가장자리 획을 버튼 **밖 맵 색**으로 당겨와 테두리를 오염시켜 반려.
    대신 **획으로 검출된 픽셀만 '내부색 중앙값'으로 페인트** → 외부 색을 절대 안 당겨오므로
    프레임·테두리 오염이 원천 불가능하고, 획 아닌 내부·베벨은 원본 그대로(밝기 유지).
    rect는 프레임 안쪽만. dx로 한글만 좌우 미세이동(fill과 분리). comp(RGB uint8) 제자리 갱신."""
    if not OVERLAY_ONLY:
        # 검출·페인트 영역 = 텍스트 rect + pad(잔여까지 포함). pad는 int/(가로,세로)/(좌,우,상,하).
        # 비대칭 지원 — 알약 ら 잔여는 오른쪽에만 있어 오른쪽만 확장(좌우 대칭이면 반대편 캡 손상).
        pl, pr, pt, pb = _pad4(pad)
        sub = comp[iy0 - pt : iy1 + pb, ix0 - pl : ix1 + pr]
        lum = sub.astype(int).sum(2)
        thr = (np.percentile(lum, 75) + np.percentile(lum, 25)) / 2  # 셀 밝기 적응 경계
        ink = binary_dilation(lum < thr, iterations=1)  # 획 + 안티에일리어스 halo
        # 라운드 코너 + **테두리 inset 마스크**: 바깥 inset px(버튼 프레임/캡)는 절대 안 칠해
        # 테두리를 원본 그대로 보존(유저 QA #72). 안쪽 일본어 획만 페인트.
        h, w = sub.shape[:2]
        ih, iv = inset if inset is not None else COLL_FILL_INSET
        mimg = Image.new("L", (w, h), 0)
        rad = radius if radius is not None else COLL_RADIUS
        ImageDraw.Draw(mimg).rounded_rectangle(
            [ih, iv, w - 1 - ih, h - 1 - iv], radius=rad, fill=255
        )
        paint = ink & (np.asarray(mimg) > 0)
        if gradient:
            # 알약 금색 세로 그라디언트 보존: **행별** 밝은 픽셀(금색 배경, 상위 ~32%) median으로
            # 채움 — 획 사이로 비치는 금색을 잡아 빽빽한 행도 처리(그라디언트 유지).
            for r in range(h):
                pr = paint[r]
                if not pr.any():
                    continue
                rl = lum[r]
                bg = sub[r][rl >= np.percentile(rl, 68)]
                sub[r][pr] = (np.median(bg, axis=0) if len(bg) else sub[r].mean(0)).astype(np.uint8)
        else:
            interior = sub[~ink]  # 획 아닌 내부 픽셀 → 채널별 p40=바탕색(하이라이트 배제)
            fill = (
                np.percentile(interior, 40, axis=0) if len(interior) else sub.reshape(-1, 3).mean(0)
            )
            sub[paint] = fill.astype(np.uint8)
    # 한글 스프라이트(투명 배경, 4x 슈퍼샘플) 합성 — rect 중앙 + dx. dx는 스프라이트 안에서 4x
    # 오프셋(xoff) → 축소 후 **서브픽셀 이동 가능**(정수 composite였으면 0.5px 불가).
    color = OVERLAY_COLOR if (OVERLAY_ONLY and OVERLAY_COLOR) else TEXT_DARK
    sp = Image.new("RGBA", ((ix1 - ix0) * 4, (iy1 - iy0) * 4), (0, 0, 0, 0))
    _draw_text(
        sp,
        text,
        color + (255,),
        wfrac=wfrac,
        hfrac=hfrac,
        xoff=round(dx * 4),
        yoff=round(dy * 4),
    )
    sp = sp.resize((ix1 - ix0, iy1 - iy0), Image.LANCZOS)
    base = Image.fromarray(comp).convert("RGBA")
    base.alpha_composite(sp, (ix0, iy0))
    comp[:, :, :] = np.asarray(base.convert("RGB"))
    return comp


def clut_rgb(clut):
    """TIM CLUT(u16 배열) → (256,3) RGB888."""
    c = np.asarray(clut).astype(int)
    return np.stack([(c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3], 1).astype(
        np.int32
    )


def load_logo_alpha():
    """유저 금색 로고 PNG에서 글자만 RGBA로 추출. 세 케이스:
    ① 알파 있으면 그대로. ② **검정 배경**(유저가 자모 여백을 검정으로 분리) → 밝기 임계로 알파
    생성(검정=배경·여백·카운터 전부 투명). ③ 체커보드(저채도·밝음) → 배경 검출 + 큰 구멍=카운터."""
    im = Image.open(LOGO_PNG).convert("RGB")
    a = np.array(im).astype(int)
    if (np.array(Image.open(LOGO_PNG).convert("RGBA"))[:, :, 3] < 250).any():
        # ① 이미 투명 알파가 있으면 그대로
        rgba = Image.open(LOGO_PNG).convert("RGBA")
        arr = np.array(rgba)
        return rgba, arr[:, :, 3] > 30
    if a[:8, :8].max() < 60:
        # ② 검정 배경: 금색 글자(밝음)만 불투명, 검정(여백·카운터·배경) 투명 → 배경(맵) 비침
        letter = a.sum(2) > 40
        ll, ln = label(letter)  # 떠다니는 작은 조각 제거
        lsz = np.bincount(ll.ravel())
        letter = np.isin(ll, [i for i in range(1, ln + 1) if lsz[i] >= 400])
        rgba = Image.fromarray(np.dstack([a.astype(np.uint8), (letter * 255).astype(np.uint8)]))
        return rgba, letter
    sat = a.max(2) - a.min(2)
    bg = (sat < 16) & (a.max(2) > 165)
    letter0 = binary_opening(~bg, iterations=2)
    filled = binary_fill_holes(letter0)
    holes = filled & ~letter0
    hl, hn = label(holes)
    hsz = np.bincount(hl.ravel())
    counters = np.isin(hl, [i for i in range(1, hn + 1) if hsz[i] >= 1500])
    counters = binary_dilation(counters, iterations=6)
    final = filled & ~counters
    ll, ln = label(final)
    lsz = np.bincount(ll.ravel())
    final = np.isin(ll, [i for i in range(1, ln + 1) if lsz[i] >= 8000])
    rgba = Image.fromarray(np.dstack([a.astype(np.uint8), (final * 255).astype(np.uint8)]))
    return rgba, final


def inpaint_box(rgb, mask):
    """mask 픽셀을 비마스크 최근접(거리변환)으로 채움."""
    ind = distance_transform_edt(mask, return_distances=False, return_indices=True)
    out = rgb.copy().astype(np.float32)
    for c in range(3):
        out[:, :, c][mask] = rgb[:, :, c][tuple(ind[:, mask])]
    return np.clip(out, 0, 255).astype(np.uint8)


def quantize_region(comp_rgb, clut_arr):
    """comp_rgb(H,W,3)를 256색 CLUT에 픽셀별 최근접 매핑 → 인덱스 배열."""
    flat = comp_rgb.reshape(-1, 3).astype(np.int32)
    # 청크로 거리 계산(메모리)
    idx = np.empty(flat.shape[0], np.uint8)
    step = 4096
    for i in range(0, flat.shape[0], step):
        seg = flat[i : i + step]
        d = ((seg[:, None, :] - clut_arr[None, :, :]) ** 2).sum(2)
        idx[i : i + step] = d.argmin(1).astype(np.uint8)
    return idx.reshape(comp_rgb.shape[:2])


def render_logo(tim):
    """컬렉션 TIM(dict) → 로고 교체된 새 픽셀 인덱스 배열(h,w)."""
    w, h = tim["w"], tim["h"]
    pix = np.frombuffer(tim["pix"], np.uint8).reshape(h, w).copy()
    clut = clut_rgb(tim["clut"])
    rgb = clut[pix]
    R, B = rgb[:, :, 0], rgb[:, :, 2]
    x0, x1, y0, y1 = LOGO_BOX
    seed = (R >= B + 20) & (rgb[:, :, 0] + rgb[:, :, 1] > 150) & (R > 75)
    box = np.zeros((h, w), bool)
    box[y0:y1, x0:x1] = True
    mask = binary_dilation(seed & box, iterations=4) & box
    base = inpaint_box(rgb, mask)

    logo, _ = load_logo_alpha()
    la = np.array(logo)[:, :, 3] > 30
    ys, xs = np.where(la)
    logo = logo.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    tw, th = logo.size
    TW, TH = int((x1 - x0) * LOGO_SCALE), int((y1 - y0) * LOGO_SCALE)
    s = min(TW / tw, TH / th)
    nw, nh = int(tw * s), int(th * s)
    lr = logo.resize((nw, nh), Image.LANCZOS)
    cx = x0 + ((x1 - x0) - nw) // 2
    cy = y0 + ((y1 - y0) - nh) // 2
    canvas = Image.fromarray(base).convert("RGBA")
    canvas.alpha_composite(lr, (cx, cy))
    comp = np.array(canvas.convert("RGB"))

    newpix = pix.copy()
    newpix[y0:y1, x0:x1] = quantize_region(comp[y0:y1, x0:x1], clut)
    return newpix


def render_buttons(tim):
    """ED1/ED2 TIM → 원본 알약은 그대로 두고 내부 **일본어 텍스트만** 한글로 덮어씀.

    알약 프레임·금색·상태색·크기·위치는 원본 유지 → 커서 이동 시 이동/크기변화 없음."""
    w, h = tim["w"], tim["h"]
    pix = np.frombuffer(tim["pix"], np.uint8).reshape(h, w).copy()
    clut = clut_rgb(tim["clut"])
    comp = clut[pix].astype(np.uint8)
    for ix0, ix1, iy0, iy1, text, dx, pad in PILL_TEXT:
        # 알약: gradient=True(금색 세로 그라디언트 행별 보존), inset으로 캡·아웃라인 원본 유지.
        comp = overwrite_text(
            comp,
            ix0,
            ix1,
            iy0,
            iy1,
            text,
            hfrac=0.58,
            dx=dx,
            pad=pad,
            inset=(1, 2),
            radius=2,
            gradient=True,
        )
    newpix = pix.copy()
    for ix0, ix1, iy0, iy1, _, _, pad in PILL_TEXT:  # 재양자화도 pad 포함(페인트 영역 전부)
        pl, pr, pt, pb = _pad4(pad)
        newpix[iy0 - pt : iy1 + pb, ix0 - pl : ix1 + pr] = quantize_region(
            comp[iy0 - pt : iy1 + pb, ix0 - pl : ix1 + pr], clut
        )
    return newpix


def render_coll_buttons(tim, pix):
    """컬렉션 TIM: 원본 英雄伝説Ⅰ/Ⅱ 버튼은 그대로 두고 일본어 텍스트만 한글로 교체(유저 #68 "완전히
    깨끗" 버전). 클린-재작도(4셀 버튼 직접 그리기)는 엔진 셀 지오메트리 제각각이라 Ⅱ y어긋남·각짐이
    생겨 폐기. 원본 보존이 radius·상태색 원본 그대로라 오리지널에 충실. 획만 내부색 페인트+pad+라운드
    마스크로 잔여·모서리 처리(overwrite_text)."""
    clut = clut_rgb(tim["clut"])
    comp = clut[pix].astype(np.uint8)
    hp, vp = COLL_PAD
    for ix0, ix1, iy0, iy1, text, dx, dy in COLL_TEXT:
        comp = overwrite_text(
            comp, ix0, ix1, iy0, iy1, text, wfrac=0.72, hfrac=0.68, dx=dx, dy=dy, pad=COLL_PAD
        )
    newpix = pix.copy()
    for ix0, ix1, iy0, iy1, *_ in COLL_TEXT:  # 재양자화도 pad 포함(페인트한 영역 전부)
        newpix[iy0 - vp : iy1 + vp, ix0 - hp : ix1 + hp] = quantize_region(
            comp[iy0 - vp : iy1 + vp, ix0 - hp : ix1 + hp], clut
        )
    return newpix


def tim_bytes(buf, off, newpix):
    """원본 TIM 바이트에서 픽셀 블록만 교체한 새 바이트열(섹터 write용)."""
    t = parse_tim(buf, off)
    cbsize = struct.unpack_from("<I", buf, off + 8)[0]
    pix_off = 8 + cbsize + 12
    n = t["w"] * t["h"]
    blob = bytearray(buf[off : off + pix_off + n])
    blob[pix_off : pix_off + n] = newpix.astype(np.uint8).tobytes()
    tail = (len(blob) + 2047) // 2048 * 2048 - len(blob)
    return bytes(blob) + b"\x00" * tail


def main():
    if not os.path.exists(TARGET):
        raise SystemExit(f"대상 없음: {TARGET} — build.py 먼저")
    buf = user_stream()  # 원본 디스크(TIM 소스)
    with open(TARGET, "r+b") as f:
        # 컬렉션: 대형 로고 + 英雄伝説Ⅰ/Ⅱ 선택 버튼
        coll = parse_tim(buf, COLL_OFF)
        assert coll and (coll["w"], coll["h"]) == (480, 240), "컬렉션 TIM 오류"
        assert COLL_OFF % 2048 == 0, "TIM 섹터 비정렬"
        pix = render_coll_buttons(coll, render_logo(coll))
        n = write_user_data(
            f, COLL_OFF // 2048, tim_bytes(buf, COLL_OFF, pix), label="타이틀 로고 TIM"
        )
        print(f"타이틀 로고(영웅전설)+선택버튼(영웅전설Ⅰ/Ⅱ) → 섹터 {n}개 수정")
        # ED1·ED2: 게임시작 알약(처음부터/이어하기)
        for off, nm in ((ED1_OFF, "ED1"), (ED2_OFF, "ED2")):
            tim = parse_tim(buf, off)
            assert tim and (tim["w"], tim["h"]) == (390, 240), f"{nm} TIM 오류"
            assert off % 2048 == 0, "TIM 섹터 비정렬"
            n = write_user_data(
                f, off // 2048, tim_bytes(buf, off, render_buttons(tim)), label="타이틀 버튼 TIM"
            )
            print(f"{nm} 버튼(처음부터/이어하기) → 섹터 {n}개 수정")


if __name__ == "__main__":
    main()
