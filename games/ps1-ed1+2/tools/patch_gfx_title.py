"""타이틀 화면 그래픽 한글화 — 8bpp TIM 픽셀 재작성 (graphics-text 트랙).

PS1 타이틀은 3장의 8bpp TIM(전부 START.DAT, 디스크 섹터 정렬):
  0x50C800 컬렉션(480x240): 대형 英雄伝説 로고 + 英雄伝説Ⅰ/Ⅱ 버튼(각 2상태)
  0x52A000 ED1(390x240):   はじめから/つづきから 버튼(각 2상태)
  0x541000 ED2(390x240):   はじめから/つづきから 버튼(각 2상태)
영문 로고("The Legend of Heroes")·저작권·PRESS START·엠블럼·월드맵은 유지.

로고 방식(2026-07-14, 유저 확정):
  · 유저 제작 금색 로고(`shared/assets/title_logo.png`, 배경제거 RGBA)를 활용 — 절차적 재현이
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
import sys

import numpy as np
from common import BUILD_DIR, write_user_data
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scan_tim import parse_tim, user_stream
from scipy.ndimage import (
    binary_dilation,
    distance_transform_edt,
)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
from shared.gfx import inpaint as gfx_inpaint
from shared.gfx import logo as gfx_logo

# ⚠ 레이아웃 엔진을 못 박는다 — Pillow 는 Raqm(HarfBuzz)이 있으면 그걸 기본으로 쓰는데,
# 같은 Pillow·FreeType 이어도 Raqm 유무로 **글자 배치가 달라진다**(macOS 휠 없음 / 리눅스 휠 있음).
# 그러면 같은 입력에도 머신마다 다른 이미지가 나온다(2026-08-09 실측: START.DAT 8섹터).
BASIC_LAYOUT = ImageFont.Layout.BASIC


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
# ⚠ 로고는 **공용**이다(`shared/assets/`) — 새턴 타이틀도 같은 그림을 쓴다.
#   한쪽 게임 폴더에 두면 다른 게임이 남의 폴더를 가리키게 된다.
LOGO_PNG = os.path.join(ROOT, "..", "..", "shared", "assets", "title_logo.png")

COLL_OFF = 0x50C800  # 컬렉션 타이틀 TIM (스트림=디스크 섹터 오프셋)
ED1_OFF = 0x52A000  # ED1 타이틀
ED2_OFF = 0x541000  # ED2 타이틀
# 옛 英雄伝説 로고 bbox. y0=62 — 위 영어박스 "The Legend of Heroes I&II" 하단(y48~60)을
# 침범하면 그 박스 바닥이 인페인트로 깨진다(유저 QA). 로고 실제 시작은 y72라 y62는 갭 안.
LOGO_BOX = (8, 310, 62, 141)
LOGO_SCALE = 1.0  # LOGO_FIT 위에 얹는 취향값. 1.0 = 원본 한자 상자 그대로
# 🔴 **새턴과 통일한 로고 정본**(유저 확정 2026-08-23 「같은 제작사라 같은 에셋을 썼을 것,
#   크기·위치 통일하자」). 두 기종 다 화면 320x240 이고 원본 한자 획 상자 실측도 사실상
#   같다 — PS1 290x69·중심 y106, 새턴 285x71·중심 y107. **PS1 실측을 정본으로 삼는다.**
LOGO_FIT = (290, 69)  # 원본 한자 획 상자 (w, h)
LOGO_CY = 106  # 세로 중심 (배너와 저작권 사이)
KANJI_TOP = 71  # 원본 한자 획이 시작하는 행 — 그 위는 배너다(재는 마스크가 물던 자리)
KANJI_HALO = 4  # 획 둘레로 이만큼 지운다(외곽선·그림자까지). 잔여 일본어 실측 5화소
LOGO_INK_LUM = 430  # 한자 획으로 칠 최소 밝기(R+G+B)
HALO_EXCL = 4  # 판 색을 잴 때 글자 둘레 이만큼을 뺀다(밝은 테가 섞이면 판이 밝아진다)
GLOW_WIDTH = 1  # 선택 셀의 밝은 테 두께(최종 px)
SMOOTH_MIX = 0.65  # 메울 때 확산 비중 — 가짜 해안선 대신 둘레와 이어지는 쪽을 택한다
MAP_ROWS = (24, 236)  # 인페인트 원천으로 쓸 지도 구간(배너 위·화면 아래는 뺀다)
SCREEN_W = 320  # ⚠ TIM 은 480 폭이지만 화면에 나가는 건 앞 320 이다

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
# 🔴 알약 **모양 하나 + 자리 넷**. 합성 둥근사각(radius=2)은 실제 캡을 못 따라가서, `inset` 을
# 줄여 칠을 넓히면 **모서리가 각져** 버린다(실측 2026-08-23). 새턴에서 같은 벽을 만나 실제
# 알약 곡선을 상수로 박았고(`ss-ed1+2/tools/patch_gfx_menu.PILL_PROF`), **같은 도안이라 그
# 곡선이 PS1 에도 맞는다**(겹쳐 확인). 그러면 `inset=0` 으로 알약 전체를 칠해도 안전하다.
# `PILL_TOP` = 위 절반 각 행의 좌·우 들여쓰기. 아래는 뒤집어 붙여 **상하 대칭**을 보장한다.
# 🔴 알약 **모양 하나 + 자리 넷**. 순수 기하다 — 색을 안 본다(새턴과 같은 방식).
# `PILL_TOP` = 위 절반 각 행의 좌·우 들여쓰기. 아래는 뒤집어 붙여 **상하 대칭**을,
# 좌우는 같은 값을 양쪽에 써서 **좌우 대칭**을 보장한다.
# ⚠ 재는 건 **오른쪽 경계**로 했다 — 왼쪽은 배경 지도에 금색 픽셀이 있어 검출이 오염된다.
#   여덟 알약의 오른쪽 곡선이 서로 일치해서(±1) 그 값을 정본으로 삼았다.
# ⚠ 한때 여기에 **원본 금색과의 교집합**을 걸었는데(선택 알약에서 곡선이 몇 px 어긋나서),
#   그게 유저 지적 넷의 원인이었다 — 일본어가 테두리에 닿은 행에서 마스크가 흔들려
#   ① 잔재가 남고 ② 우리 한글의 ㅇ이 부분적으로 안 그려졌다. **색을 섞으면 안 된다.**
PILL_TOP = [7, 5, 4, 3, 2, 1, 1, 0, 0, 0]
PILL_PROF = PILL_TOP + [0] * 5 + PILL_TOP[::-1]  # 25행
PILL_W = 64
# 좌상 자리 — **오른쪽 경계 − 63** 으로 잡았다(오른쪽이 깨끗해서).
PILL_AT = [(48, 193), (224, 193), (323, 3), (324, 33)]
PILL_INK_MIN = 8  # 글자색 후보로 칠 최소 픽셀 수(같은 상태 두 버튼 합산)
PILL_RING_DEV = 70  # 링 안쪽 — 좌우 이웃보다 이만큼 어두우면 잔재
PILL_DY = 0.5  # 기하 중심 보정 뒤 남는 반 픽셀 — 새턴 글자 중심(12.0)에 맞춘다
# 캡 맨 바깥 열 — 위아래 이웃보다 이만큼 어두우면 잔재.
# ⚠ 60 으로 두면 **알약 자신의 안티에일리어스**(실측 밝기 440·448)까지 잡아 밝게 바꾸고,
#   그러면 왼쪽 위 캡이 부풀어 **삐져나온 것처럼** 보인다(유저 지적 2026-08-23).
#   150 이면 진짜 잔재(280)만 잡고 AA 는 그대로 둔다. 250 까지 올리면 잔재도 놓친다.
PILL_EDGE_DEV = 150
#   (채우는 값은 이웃이 아니라 **같은 행 반대쪽 가장자리** — 아래 주석 참조)
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
# ⚠ dy 는 **정수**로 둔다 — 0.5px 를 주면 4배 스프라이트에서 2px 어긋나 축소 때 다시 흐려진다.
COLL_TEXT = [
    (325, 413, 5, 27, "영웅전설Ⅰ", 2, 0),  # cell0 Ⅰsel  중심 y16
    (325, 413, 35, 57, "영웅전설Ⅰ", 2, 0),  # cell1 Ⅰnorm 중심 y46
    (325, 416, 65, 87, "영웅전설Ⅱ", 3, 0),  # cell2 Ⅱsel  중심 y76
    (325, 416, 95, 117, "영웅전설Ⅱ", 3, 0),  # cell3 Ⅱnorm 중심 y106
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
# ⚠ 알약 글자가 **원본보다 한참 작았다**(유저 지적 2026-08-23 — 실측: 원본 일본어 획 55x16,
#   우리 45x10). 4배 스프라이트라 실효 크기는 이 값의 1/4 이다(47 → 11.75px).
#   54(=13.5px)면 획이 원본과 같은 폭(54~55)이 되고 캡에는 안 닿는다. 새턴도 13px 이다.
PIN_SIZE = {
    # ⚠ **4의 배수**여야 한다 — 그래야 4배 스프라이트에서 위치를 격자에 스냅해 축소 때
    #   획이 안 뭉갠다(54 = 13.5px 라 위상이 어긋나 뿌옇게 나왔다. 유저 지적 2026-08-23).
    #   56 = 14px — 원본 일본어 획 폭(55)에 가장 가깝다(12px 는 48, 13px 는 52).
    "처음부터": 56,
    "이어하기": 56,
    # 🔴 **16px** — 4배 스프라이트라 64 다. 새턴 선택판과 같은 크기로 맞췄다(유저 확정
    #   2026-08-23 「새턴이 폰트도 크고 가독성이 좋다」). 52(=13px)는 새턴 17px 대비 31% 작았다.
    #   ⚠ 16 인 이유는 「4로 나눠떨어져서」만이 아니다 — **네오둥근모가 16×16 픽셀 폰트**라
    #     그 크기에서 리샘플 없이 또렷하다. 17px 는 격자를 벗어나 획이 뭉갠다.
    #   실측: 「영웅전설II」 80px < 칸 89px.
    "영웅전설I": 64,
    "영웅전설II": 64,
}


def _draw_text(img, text, fill, wfrac=0.80, hfrac=0.62, xoff=0, yoff=0):
    """img 중앙에 글자(폭·높이 프랙션으로 축소해 버튼 안쪽 여백 확보). xoff는 스프라이트(4x) 픽셀
    단위 x 오프셋 — 축소 후 서브픽셀 이동이 된다."""
    text = _sub(text)
    _assert_glyphs(text)
    W, H = img.size
    d = ImageDraw.Draw(img)
    pin = PIN_SIZE.get(text)
    f, bb = _fit_font(d, text, int(W * wfrac), int(H * hfrac), pin=pin)
    tx = (W - (bb[2] - bb[0])) // 2 - bb[0] + xoff
    ty = (H - (bb[3] - bb[1])) // 2 - bb[1] + yoff
    if pin and pin % 4 == 0:
        # 🔴 **4배 스프라이트에서 위치를 4의 배수로 맞춘다.** 네오둥근모는 픽셀 폰트라
        #   64px 렌더가 16px 의 정확한 4배인데(실측 320x52 = 80x13 ×4), 위치가 4의 배수가
        #   아니면 4:1 축소 때 이웃 두 화소가 섞여 획이 **회색으로 뭉갠다** — 유저가
        #   「뭉개지고 뿌연 느낌」으로 잡아낸 자리다(2026-08-23. 실측 오프셋 22 → 위상 2).
        tx, ty = round(tx / 4) * 4, round(ty / 4) * 4
    d.text((tx, ty), text, fill=fill, font=f)


def _pad4(pad):
    """pad를 (좌,우,상,하)로 정규화. int→사방, (가로,세로)→대칭, (좌,우,상,하)→그대로."""
    if isinstance(pad, tuple) and len(pad) == 4:
        return pad
    if isinstance(pad, tuple):
        return pad[0], pad[0], pad[1], pad[1]
    return pad, pad, pad, pad


def pill_ink_color(comp, idxs):
    """그 상태(미선택/선택) 알약들의 **원본 획 색**을 하나 고른다.

    🔴 `TEXT_DARK`(8,8,8) 하나로 두 상태를 칠하고 있었는데, **원본이 상태별로 다르다**
      (실측: 미선택 RGB(8,8,8) · 선택 (48,56,56)~(80,80,56)). 선택 알약이 훨씬 밝아
      거기선 검정이 원본보다 짙다(유저 지적 2026-08-23). 새턴도 같은 이유로 상태별로 뽑는다.
    ⚠ 같은 상태 두 버튼을 **합쳐서** 고른다 — 따로 뽑으면 버튼끼리 색이 갈린다(새턴 실측).
    ⚠ 「최빈 대비 비율」로 거르면 합칠 때 최빈이 커져 어두운 색이 통째로 탈락한다 —
      **절대 개수**로 자른다.
    """
    hist = {}
    for i in idxs:
        ix0, ix1, iy0, iy1, _t, _dx, pad = PILL_TEXT[i]
        pl, pr, pt, pb = _pad4(pad)
        sub = comp[iy0 - pt : iy1 + pb, ix0 - pl : ix1 + pr].astype(int)
        hh, ww = sub.shape[:2]
        mimg = Image.new("L", (ww, hh), 0)
        ImageDraw.Draw(mimg).rounded_rectangle([1, 2, ww - 2, hh - 3], radius=2, fill=255)
        m = np.asarray(mimg) > 0
        lum = sub.sum(2)
        thr = (np.percentile(lum[m], 75) + np.percentile(lum[m], 25)) / 2
        for col, n in zip(
            *np.unique(sub[(lum < thr) & m], axis=0, return_counts=True), strict=True
        ):
            key = tuple(int(v) for v in col)
            hist[key] = hist.get(key, 0) + int(n)
    cand = [c for c, n in hist.items() if n >= PILL_INK_MIN]
    return min(cand, key=sum) if cand else TEXT_DARK


def pill_shape_mask(comp, ix0, ix1, iy0, iy1, pad, at):
    """알약 마스크 — **못 박은 곡선 ∩ 원본 금색**. `overwrite_text`·재양자화가 같이 쓴다.

    🔴 곡선만으로는 부족하다 — 미선택 알약에서 잰 곡선이라 **선택(밝은) 알약과 몇 px
      어긋난다**(실측: 자리를 최적으로 맞춰도 86~93px 이 밖으로 나갔다). 금색과 교집합을
      내면 **넓히는 법이 없어** 넘칠 수가 없다.
    ⚠ 금색은 밝기가 아니라 **색의 순서**(R>G>B)로 잡는다 — 선택/미선택은 밝기가 크게 달라
      임계로는 한쪽이 늘 틀린다(새턴에서 다섯 번 물렸다).
    """
    pl, pr, pt, pb = _pad4(pad)
    sub = comp[iy0 - pt : iy1 + pb, ix0 - pl : ix1 + pr]
    h, w = sub.shape[:2]
    ox, oy = at[0] - (ix0 - pl), at[1] - (iy0 - pt)
    m = np.zeros((h, w), bool)
    for r, padx in enumerate(PILL_PROF):
        y = oy + r
        if 0 <= y < h:
            m[y, max(0, ox + padx) : max(0, min(w, ox + PILL_W - padx))] = True
    # 🔴 **빗장** — 원본이 배경 지도면 안 건드린다. 곡선은 상수라 알약보다 큰 행이 생길 수
    #   있고, 그 자리에 칠이 나가면 「곡선을 뚫고 나왔다」가 된다(유저 지적 2026-08-23).
    #   지도는 **파랑(B>R) 또는 초록(G>R)**, 알약은 금색(R>G>B), 획은 따뜻한 어두움
    #   (실측 RGB(8,8,8)·(16,16,8)·(80,56,16) — 전부 R≥G≥B)이다. 그래서 이 기준은
    #   **획을 안 건드리고 지도만** 뺀다.
    #   ⚠ **금색(R>G>B)으로 자르면 안 된다** — 검은 획이 빠져 아무것도 안 지워진다.
    #     실제로 그렇게 만들었다가 한글이 일본어 위에 겹쳐 찍혔다.
    g = sub.astype(int)
    bg = (g[..., 2] > g[..., 0]) | (g[..., 1] > g[..., 0])
    return m & ~bg


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
    text_color=None,
    glow_color=None,
    fill_color=None,
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
        mask = np.asarray(mimg) > 0
        paint = ink & mask
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
            # ⚠ **밝은 테를 빼고 잰다** — 선택 셀엔 글자 둘레에 밝은 테가 있어서, 안 빼면
            #   판이 통째로 밝아지고(실측 328 → 456) 그 위에 테를 그려도 대비가 없다.
            halo = binary_dilation(ink, iterations=HALO_EXCL) & ~ink
            interior = sub[~ink & ~halo]  # 획·테 아닌 내부
            # ⚠ **최빈색**으로 잡는다. p40 은 남은 화소 분포를 타서 같은 상태의 두 셀이
            #   서로 다른 밝기로 칠해졌다(실측: 초록 셀 판 432 vs 280). 판은 원래 한 색이라
            #   최빈값이 곧 그 색이고 흔들리지 않는다.
            if fill_color is not None:
                fill = np.asarray(fill_color, float)
            elif len(interior):
                u, cnt = np.unique(interior.reshape(-1, 3), axis=0, return_counts=True)
                fill = u[cnt.argmax()].astype(float)
            else:
                fill = sub.reshape(-1, 3).mean(0)
            sub[paint] = fill.astype(np.uint8)
    # 한글 스프라이트(투명 배경, 4x 슈퍼샘플) 합성 — rect 중앙 + dx. dx는 스프라이트 안에서 4x
    # 오프셋(xoff) → 축소 후 **서브픽셀 이동 가능**(정수 composite였으면 0.5px 불가).
    color = OVERLAY_COLOR if (OVERLAY_ONLY and OVERLAY_COLOR) else (text_color or TEXT_DARK)
    # ⚠ 스프라이트를 **글자색으로 채워** 둔다(알파만 0). 투명부 RGB 가 검정이면 4:1 축소가
    #   그 검정을 가장자리에 섞어 획을 굵고 뿌옇게 만든다 — 유저가 「뭉개지고 뿌연 느낌」으로
    #   잡아낸 자리다(2026-08-23). 테(glow)에서 같은 사고를 한 번 더 겪었다.
    sp = Image.new("RGBA", ((ix1 - ix0) * 4, (iy1 - iy0) * 4), tuple(color) + (0,))
    _draw_text(
        sp,
        text,
        color + (255,),
        wfrac=wfrac,
        hfrac=hfrac,
        xoff=round(dx * 4),
        yoff=round(dy * 4),
    )
    # 🔴 픽셀 폰트 경로는 **BOX**(정확 평균)로 줄인다. LANCZOS 는 링잉이 있어 딱딱한
    #   4배 확대본을 줄이면 획 둘레가 어두워져 굵고 뭉개져 보인다(유저 지적 2026-08-23).
    #   BOX + 4의 배수 오프셋이면 4배 확대 전의 비트맵이 **그대로** 돌아온다.
    down = Image.BOX if (PIN_SIZE.get(text, 0) % 4 == 0) else Image.LANCZOS
    sp = sp.resize((ix1 - ix0, iy1 - iy0), down)
    base = Image.fromarray(comp).convert("RGBA")
    if glow_color is not None:
        # 🔴 **선택 셀은 글자 둘레에 밝은 테가 있다** — 「빛을 받은」 느낌의 정체다
        #   (유저 지적 2026-08-23). 미선택 셀엔 없다. 실측: 초록 셀은 둘레의 55~60%가
        #   판보다 10%+ 밝고, 흰 셀은 0% 다. 획을 GLOW_WIDTH 만큼 부풀려 먼저 깐다.
        #   ⚠ **알파만 부풀리면 안 된다** — 스프라이트의 RGB 는 글자 밖에서 (0,0,0)이라
        #     늘어난 테가 **검게** 나온다(실측: 초록 셀 어두운 화소 343 → 1027).
        #     색을 통째로 깔고 그 위에 부푼 알파를 씌운다.
        sz = ((ix1 - ix0) * 4, (iy1 - iy0) * 4)
        tmp = Image.new("RGBA", sz, (0, 0, 0, 0))
        _draw_text(
            tmp,
            text,
            (255, 255, 255, 255),
            wfrac=wfrac,
            hfrac=hfrac,
            xoff=round(dx * 4),
            yoff=round(dy * 4),
        )
        ga = tmp.split()[3].filter(ImageFilter.MaxFilter(GLOW_WIDTH * 8 + 1))
        gs = Image.new("RGBA", sz, tuple(int(v) for v in glow_color) + (0,))
        gs.putalpha(ga)
        base.alpha_composite(gs.resize((ix1 - ix0, iy1 - iy0), down), (ix0, iy0))
    base.alpha_composite(sp, (ix0, iy0))
    comp[:, :, :] = np.asarray(base.convert("RGB"))
    return comp


def clut_rgb(clut):
    """TIM CLUT(u16 배열) → (256,3) RGB888."""
    c = np.asarray(clut).astype(int)
    return np.stack([(c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3], 1).astype(
        np.int32
    )


# 🔴 금색을 **노란 쪽으로** 민다(유저 확정 2026-08-23 「모니터마다 주황 강도가 다르다」).
#   팔레트에 금색을 넣어 G 는 맞췄지만(131 → 136, 원화 137) **B 가 +10~14 높아**(45 → 55~59)
#   탁해 보인다. 금색 구간만 B 를 내리고 G 를 살짝 올린다 — 흰 본문·검은 외곽선은 안 건드린다.
GOLD_WARM_G, GOLD_WARM_B = 6, 14


def warm_gold(comp):
    """R>G>B 인 중간 밝기 화소(=금색)만 노란 쪽으로."""
    a = comp.astype(np.int16)
    lum = a.sum(2)
    m = (a[:, :, 0] > a[:, :, 1]) & (a[:, :, 1] > a[:, :, 2]) & (lum > 180) & (lum < 660)
    a[:, :, 1] = np.where(m, np.clip(a[:, :, 1] + GOLD_WARM_G, 0, 255), a[:, :, 1])
    a[:, :, 2] = np.where(m, np.clip(a[:, :, 2] - GOLD_WARM_B, 0, 255), a[:, :, 2])
    return a.astype(np.uint8)


def rgb_to_clut(rgb):
    """RGB888 → TIM CLUT u16 (RGB555)."""
    c = np.asarray(rgb).astype(int) >> 3
    return ((c[..., 2] << 10) | (c[..., 1] << 5) | c[..., 0]).astype(np.uint16)


def reclaim_clut(clut, pix):
    """🔴 **팔레트에서 낭비되는 자리를 회수한다.**

    로고가 인게임에서 주황빛으로 보인다는 지적(2026-08-23)의 원인은 양자화다 — 이 팔레트엔
    **노란 기 도는 금색이 없어** 최근접이 계통적으로 R 을 올리고 G 를 내린다
    (실측: `#926912 → #a86818`, 어떤 건 G −19). 그런데 256칸 중 **240색만 고유**하고
    16칸이 완전 중복이다(+ 미사용 1). 중복은 색이 같아 대표 하나로 옮겨도 화면이 안 바뀐다 —
    그렇게 회수한 자리에 필요한 금색을 넣는다.

    반환: (색인 재배치를 적용한 pix, 비어난 색인 목록).
    """
    cnt = np.bincount(pix.ravel(), minlength=256)
    _u, inv = np.unique(clut, axis=0, return_inverse=True)
    inv = np.asarray(inv).ravel()
    remap = np.arange(256, dtype=np.uint8)
    free = []
    for g in range(int(inv.max()) + 1):
        idx = np.nonzero(inv == g)[0]
        if len(idx) > 1:
            keep = int(idx[np.argmax(cnt[idx])])
            for i in idx:
                if int(i) != keep:
                    remap[int(i)] = keep
                    free.append(int(i))
    free += [i for i in range(256) if cnt[i] == 0 and i not in free]
    return remap[pix], sorted(set(free))


def pick_gold(comp, clut, n):
    """양자화 오차가 큰 색부터 n 개를 고른다(오차 합 가중). 무작위 없음."""
    if n <= 0:
        return []
    flat = comp.reshape(-1, 3).astype(int)
    q = clut[((clut[None, :, :] - flat[:, None, :]) ** 2).sum(2).argmin(1)]
    err = np.abs(q - flat).sum(1)
    keep = err > 12
    if not keep.any():
        return []
    coarse = (flat[keep] >> 3) << 3  # 8단위로 뭉쳐 같은 색끼리 모은다
    u, ci = np.unique(coarse, axis=0, return_inverse=True)
    ci = np.asarray(ci).ravel()
    w = np.bincount(ci, weights=err[keep], minlength=len(u))
    order = np.argsort(-w)
    return [tuple(int(x) for x in u[i]) for i in order[:n]]


def load_logo_alpha():
    """자간을 다시 잡은 「영웅전설」 RGBA + 잉크 마스크.

    ⚠ 원화 자체를 읽지 않는다 — `shared/gfx/logo.py` 가 자간을 다시 잡고 알파를 만든다.
      원화는 자간이 24 / 3 / -8px 이고 배경이 검게 구워져 있다(알파 없음). 그대로 얹으면
      「영웅은 좁고 전설은 넓다」 + 지도 위에 검은 상자다. 경위는 `shared/assets/README.md`.
    """
    rgba = gfx_logo.title_logo()
    return rgba, np.array(rgba)[:, :, 3] > 30


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
    # 🔴 지우는 마스크는 **한자 획만** 잡는다 — `seed` 는 지도의 따뜻한 화소(밝은 육지)까지
    #   문다. 그러면 상자의 86%가 구멍이 되고 남는 「아는 화소」가 어두운 바다뿐이라,
    #   무엇으로 메우든 상자 안이 통째로 어두워져 **사각형 판**으로 보인다(유저 QA
    #   2026-08-23 「배경이 투명하지가 않은것 같네」. 실측: 상자 안 212 → 141, 바깥은 그대로).
    #   엄한 기준으로 좁히면 육지가 남아 밝기가 맞는다(실측: 위·좌 경계가 원본과 동일).
    #   ⚠ 배너를 물지 않게 `KANJI_TOP` 아래만 본다 — 그게 상자를 위로 열 줄 부풀리던 자리다.
    kanji = box & (rgb.sum(2) > LOGO_INK_LUM) & (R > B + 30)
    kanji[:KANJI_TOP] = False
    mask = binary_dilation(kanji, iterations=KANJI_HALO) & box
    # 🔴 **확산 인페인트를 쓰지 않는다** — 세계지도를 통째로 뭉갠다(밝기 178 → 126, 큼직한
    #   단색 얼룩). 그 위에 짙은 테두리의 로고를 얹으면 어두운 데 어두운 게 겹쳐
    #   「테두리가 안 보인다」가 된다(유저 QA 2026-08-23). 같은 그림의 지도에서 조각을 떠 온다.
    #   ⚠ 원천에서 **글자류를 뺀다** — 안 빼면 저작권 문구 조각(「1999」)이 배경에 박힌다.
    sat = rgb.max(2).astype(int) - rgb.min(2).astype(int)
    text = binary_dilation(
        (rgb.sum(2) > 560) & (sat < 70) & (np.arange(h)[:, None] > 160), iterations=4
    )
    src = np.zeros((h, w), bool)
    src[MAP_ROWS[0] : MAP_ROWS[1], :SCREEN_W] = True
    src &= ~binary_dilation(seed, iterations=3) & ~text
    # ⚠ **메운 자리의 밝기를 상자 바깥 지도에 맞춘다** — 안 맞추면 그 자리가 통째로 어두워져
    #   사각형 음영으로 보인다(실측: 상자 안 133 vs 바깥 190. 유저 인게임 지적 2026-08-23).
    near = np.concatenate(
        [
            rgb[max(0, y0 - 6) : y0 - 1, x0:x1].reshape(-1, 3),
            rgb[y1 + 1 : y1 + 6, x0:x1].reshape(-1, 3),
        ]
    )
    tgt = float(near.astype(int).sum(1).mean()) / 3.0
    base = gfx_inpaint.fill(
        rgb.astype(np.float32), mask.copy(), src, target_mean=tgt, smooth_mix=SMOOTH_MIX
    ).astype(np.uint8)

    logo, _ = load_logo_alpha()
    la = np.array(logo)[:, :, 3] > 30
    ys, xs = np.where(la)
    logo = logo.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    # 🔴 크기·자리는 **새턴과 통일한 정본**(LOGO_FIT/LOGO_CY)이다 — 재서 쓰지 않는다.
    #   ⚠ 재던 마스크가 `LOGO_BOX` 에 걸친 **배너 아랫단**을 로고로 세서 상자가 위로 10줄
    #     부풀었다(62..140, 진짜는 72..140). 그만큼 로고가 크고 높게 앉았는데, 「원본과 같다」는
    #     검증도 같은 마스크로 해서 **틀린 값끼리 맞아떨어졌다** — 유저 인게임 대조로 발각.
    #   ⚠ 한자(4.20)와 한글 로고(3.78)는 비율이 달라 둘 다 못 맞춘다 — **상자 안에 들어가는**
    #     쪽으로 맞춘다(세로가 걸려 261x69).
    k = min(LOGO_FIT[0] / logo.width, LOGO_FIT[1] / logo.height) * LOGO_SCALE
    nw, nh = max(1, round(logo.width * k)), max(1, round(logo.height * k))
    lr = logo.resize((nw, nh), Image.LANCZOS)
    # 가로는 화면 한가운데(원본 획 중심은 그보다 5px 오른쪽), 세로는 정본 중심.
    cx, cy = (SCREEN_W - nw) // 2, round(LOGO_CY - nh / 2)
    canvas = Image.fromarray(base).convert("RGBA")
    canvas.alpha_composite(lr, (cx, cy))
    comp = warm_gold(np.array(canvas.convert("RGB")))

    # 🔴 **바뀐 자리만 쓴다.** 상자를 통째로 다시 양자화하면 손대지도 않은 배경 화소가
    #   비슷한 다른 색인으로 갈려 상자 경계가 드러난다(이 레포 단골 사고 — 새턴 이름판에서
    #   같은 걸 겪었다). 지운 자리 ∪ 로고가 덮는 자리만 갱신한다.
    touched = mask.copy()
    touched[cy : cy + nh, cx : cx + nw] |= np.array(lr)[:, :, 3] > 0
    # 🔴 팔레트에서 낭비되는 자리를 회수해 **로고에 필요한 금색**을 넣는다 — 안 그러면
    #   최근접이 주황 쪽으로 쏠린다(유저 인게임 지적 2026-08-23).
    newpix, free = reclaim_clut(clut, pix)
    newclut = clut.copy()
    for i, c in zip(free, pick_gold(comp[y0:y1, x0:x1], clut, len(free)), strict=False):
        newclut[i] = c
    q = quantize_region(comp[y0:y1, x0:x1], newclut)
    sel = touched[y0:y1, x0:x1]
    newpix[y0:y1, x0:x1][sel] = q[sel]
    return newpix, newclut


def med_gap(row_lum, near, x):
    """주변(near) 중앙값 대비 그 픽셀이 얼마나 어두운가."""
    return float(np.median(row_lum[near]) - row_lum[x])


# 🔴 **알약도 새로 그린다**(유저 확정 2026-08-23, 게임선택 판과 같은 방식). 원본 알약은
#   금색 세로 그라디언트에 줄무늬가 있어 지저분하고, 획만 덮어 칠하니 잔재·잡티가 계속 나왔다.
#   단색 + 1px 테두리로 다시 그린다. ⚠ 원본엔 테두리가 없어서 1px 로만 얹는다.
#   색은 원본 금색의 **p70**이다 — 미선택 #d0b058 · 선택 #f8f050.
#   ⚠ 최빈·중앙값을 쓰면 탁해 보인다 — 원본은 위가 밝은 세로 그라디언트라 분포에 어두운
#     아래쪽이 절반이나 섞인다. 눈에 남는 건 밝은 쪽이라 p70 이 맞다.
PILL_BODY = {False: (0xD0, 0xB0, 0x58), True: (0xF8, 0xF0, 0x50)}
PILL_BORDER_F = 0.55  # 테두리 = 본체 색 × 이 값
PILL_RESIDUE = 2  # 알약 바깥 이만큼을 배경으로 되메운다(원본 안티에일리어스 잔재)
# 글자색도 상태별로 — 원본 실측(미선택은 거의 검정, 선택은 밝은 회녹).
PILL_INK = {False: (0x10, 0x10, 0x10), True: (0x50, 0x50, 0x38)}


def render_buttons(tim):
    """ED1/ED2 TIM 의 알약 넷을 **새로 그린다** — 단색 + 1px 테두리 + 한글."""
    w, h = tim["w"], tim["h"]
    pix = np.frombuffer(tim["pix"], np.uint8).reshape(h, w).copy()
    clut = clut_rgb(tim["clut"])
    prof = np.asarray(PILL_PROF)
    ph = len(prof)
    newpix = pix.copy()
    for i, (x0, y0) in enumerate(PILL_AT):
        sel = i >= 2  # 앞 둘은 화면에 놓인 미선택, 뒤 둘은 스프라이트 칸의 선택 상태
        body = np.array(PILL_BODY[sel], np.int16)
        border = tuple(int(v * PILL_BORDER_F) for v in body)
        text = _sub("처음부터" if i % 2 == 0 else "이어하기")
        _assert_glyphs(text)
        im = Image.new("RGB", (PILL_W, ph), tuple(int(v) for v in body))
        inside = np.zeros((ph, PILL_W), bool)
        for r, t in enumerate(prof):
            inside[r, t : PILL_W - t] = True
        edge = inside & ~(
            np.pad(inside, 1)[:-2, 1:-1]
            & np.pad(inside, 1)[2:, 1:-1]
            & np.pad(inside, 1)[1:-1, :-2]
            & np.pad(inside, 1)[1:-1, 2:]
        )
        a = np.asarray(im).copy()
        a[edge] = border
        im = Image.fromarray(a)
        sp = Image.new("RGBA", (PILL_W * 4, ph * 4), tuple(PILL_INK[sel]) + (0,))
        _draw_text(sp, text, tuple(PILL_INK[sel]) + (255,), wfrac=0.86, hfrac=0.70)
        im = Image.alpha_composite(im.convert("RGBA"), sp.resize((PILL_W, ph), Image.BOX)).convert(
            "RGB"
        )
        q = quantize_region(np.asarray(im), clut)
        # ⚠ **알약 바깥 1px 링도 되메운다** — 원본 알약의 안티에일리어스가 우리 실루엣
        #   바깥으로 삐져나와 잔재로 남는다(실측: p0 8화소 · p1 48화소, 전부 1px 안).
        #   ⚠ 그 자리는 알약이 아니라 **배경**이다 — 링 바깥의 성한 화소에서 끌어온다.
        pad = PILL_RESIDUE
        oy0, ox0 = max(0, y0 - pad), max(0, x0 - pad)
        oy1, ox1 = min(h, y0 + ph + pad), min(w, x0 + PILL_W + pad)
        big = np.zeros((oy1 - oy0, ox1 - ox0), bool)
        big[y0 - oy0 : y0 - oy0 + ph, x0 - ox0 : x0 - ox0 + PILL_W] = inside
        ring = binary_dilation(big, iterations=pad) & ~big
        if ring.any():
            src = clut[pix[oy0:oy1, ox0:ox1]].astype(np.float32)
            _, ind = distance_transform_edt(
                binary_dilation(big, iterations=pad), return_indices=True
            )
            fill = src[ind[0], ind[1]]
            rq = quantize_region(fill.astype(np.uint8), clut)
            newpix[oy0:oy1, ox0:ox1][ring] = rq[ring]
        blk = newpix[y0 : y0 + ph, x0 : x0 + PILL_W]
        blk[inside] = q[inside]
    return newpix


def plate_color(rgb, ix0, ix1, iy0, iy1):
    """이 셀의 **판 바탕색**(글자·밝은 테를 뺀 최빈색)."""
    sub = rgb[iy0:iy1, ix0:ix1].astype(int)
    lum = sub.sum(2)
    ink = lum < np.median(lum) * 0.55
    far = ~binary_dilation(ink, iterations=HALO_EXCL)
    px = sub[far]
    if not len(px):
        return None
    u, cnt = np.unique(px.reshape(-1, 3), axis=0, return_counts=True)
    return u[cnt.argmax()]


def cell_ink_color(rgb, ix0, ix1, iy0, iy1):
    """이 셀의 **원본 글자색**.

    🔴 `TEXT_DARK`(8,8,8) 하나로 네 셀을 칠하고 있었는데 원본은 상태별로 다르다 —
      실측: 흰 판(미선택)은 **진초록** #245737(밝기 178), 초록 판(선택)은 #0d0d0d(41).
      새까맣게 칠하니 미선택 글자가 원본보다 훨씬 무겁고, 선택 상태의 대비가 죽었다
      (유저 지적 2026-08-23 「텍스트가 빛 받은 느낌이 없다」). 알약은 `pill_ink_color`
      로 이미 상태별로 뽑고 있었는데 판만 빠져 있었다.
    """
    sub = rgb[iy0:iy1, ix0:ix1].astype(int)
    lum = sub.sum(2)
    core = lum <= np.percentile(lum, 12)  # 획 한복판 (안티에일리어스 배제)
    if not core.any():
        return None
    return tuple(int(v) for v in sub[core].mean(0).round())


def cell_glow(rgb, ix0, ix1, iy0, iy1):
    """이 셀에 **밝은 테**가 있으면 그 색, 없으면 None.

    ⚠ 색을 박지 않는다 — 셀마다 초록이 조금씩 다르다(실측 #8bb79e · #80ae93).
      원본에서 떠 온다. 판정도 원본으로 한다(흰 셀 0% vs 초록 셀 55~60%).
    """
    sub = rgb[iy0:iy1, ix0:ix1].astype(int)
    lum = sub.sum(2)
    med = np.median(lum)
    ink = lum < med * 0.55
    ring = binary_dilation(ink, iterations=1) & ~ink
    bright = ring & (lum > med * 1.10)
    if not ring.any() or bright.sum() < ring.sum() * 0.25:
        return None
    return sub[bright].mean(0).astype(int)


def _write_changed(pix, comp, clut, boxes):
    """🔴 **바뀐 자리만 쓴다.** 상자를 통째로 다시 양자화하면 손대지도 않은 배경 화소가
    비슷한 다른 색인으로 갈려 **알약·판 둘레에 잡티**로 보인다(유저 지적 2026-08-23 —
    실측: 원본이 금색이 아니던 화소 887개가 바뀌었다). 이 레포 단골 사고다.
    """
    newpix = pix.copy()
    orig = clut[pix]
    for ix0, ix1, iy0, iy1, pad in boxes:
        pl, pr, pt, pb = _pad4(pad)
        sl = (slice(iy0 - pt, iy1 + pb), slice(ix0 - pl, ix1 + pr))
        ch = (comp[sl] != orig[sl]).any(2)
        if not ch.any():
            continue
        q = quantize_region(comp[sl], clut)
        newpix[sl][ch] = q[ch]
    return newpix


# 🔴 **게임선택 판은 새로 그린다**(유저 확정 2026-08-23). 원본은 넷이 제각각이다 —
#   배경 질감이 다르고(σ 204~227), 왼쪽 테두리만 굵고, ED1/ED2 의 같은 상태끼리 배경색과
#   판 크기가 다르다(96/97/96/100). 선택을 오갈 때 버튼이 흔들려 보인다.
#   그래서 **규격을 하나로 못 박고** 단색 배경 + 균일 테두리 + 라운드로 다시 그린다.
#   ⚠ 셀 세로 간격은 정확히 30px 이다. 판은 그 격자 위에 같은 크기로 앉힌다.
#   ⚠ 라운드 모서리는 **테두리 색으로 채운다** — 스프라이트는 사각형으로 통째로 복사되니
#     잘라낸 자리에 화면 뒤 배경을 비출 수가 없다. 어두운 지도 위라 둥글게 읽힌다.
PLATE_FONT = 16  # 새턴 선택판과 같은 크기 — 네오둥근모의 설계 크기
PLATE_X = (321, 419)  # 판 가로 (끝 포함). 원본 넷을 다 덮는다
PLATE_TOPS = (4, 34, 64, 94)  # 30px 격자
PLATE_H = 25
PLATE_RADIUS = 4
BOLD_X = 1  # 판 글자를 가로로 이만큼 불린다 — 굵은 네오둥근모가 없어 합성한다
# 🔴 테두리는 **버튼 안쪽에 진한 녹색**으로 그린다(유저 확정 2026-08-23).
#   까맣게, 그리고 가장자리에 그렸더니 화면에서 세 번 다 안 보였다 — 엔진이 스프라이트를
#   2px 넘게 잘라 간다. 안쪽으로 들이면 잘릴 일이 없고, 밝은 판에 검정보다 어울린다.
PLATE_EDGE_RGB = (0x00, 0x00, 0x08)  # 판 맨 바깥 (엔진이 잘라 갈 수 있다)
# 🔴 테두리는 **상태별로 다르다**(유저 확정 2026-08-23) — 미선택은 진하게, 선택은 밝게.
#   같은 색으로 두니 선택을 오가도 안 변해 어색했다.
# ⚠ 키는 「판이 어두운가」다 — **어두운 판이 미선택**이다. 원본 주석(`cell0 Ⅰsel`)대로
#   밝은 판이 선택이고, 유저도 「선택일 때 테두리가 밝아야 한다」고 확인했다(2026-08-23).
PLATE_BORDER_RGB = {False: (0xA8, 0xC8, 0xB8), True: (0x6F, 0x9A, 0x82)}
PLATE_INSET = 1  # 판 가장자리에서 이만큼 안쪽. 0 이면 엔진이 잘라 가 안 보인다
PLATE_BORDER_W = 2  # 테두리 굵기 — 버튼처럼 읽힌다(유저 확정 2026-08-23)
# ⚠ 볼록 엠보싱도 해 봤는데 모서리 색이 어색해 **단색 2px** 로 되돌렸다(유저 확정 2026-08-23).


PLATE_BG = {False: (0xEE, 0xF0, 0xEE), True: (0x9A, 0xC0, 0xA9)}  # 미선택 / 선택
PLATE_INK = {False: (0x24, 0x57, 0x37), True: (0x0D, 0x0D, 0x0D)}
# 어느 셀이 선택 상태인가 — 원본 판이 어두운 초록이면 선택이다(실측: 흰 656 · 초록 328)
PLATE_TEXT = ("영웅전설I", "영웅전설I", "영웅전설II", "영웅전설II")


def render_coll_buttons(tim, pix, clut_override=None):
    """컬렉션 TIM 의 게임선택 판 넷을 **새로 그린다**."""
    clut = clut_rgb(tim["clut"]) if clut_override is None else clut_override
    comp = clut[pix].astype(np.uint8)
    x0, x1 = PLATE_X
    w = x1 - x0 + 1
    newpix = pix.copy()
    for (_cx0, _cx1, cy0, cy1, raw_text, _dx, _dy), top in zip(COLL_TEXT, PLATE_TOPS, strict=True):
        # ⚠ **로마숫자 Ⅰ·Ⅱ 는 네오둥근모에 없다**(두부로 나온다) — ASCII 로 바꿔 쓴다.
        text = _sub(raw_text)
        _assert_glyphs(text)
        sel = float(comp[cy0:cy1, _cx0:_cx1].astype(int).sum(2).mean()) < 450
        y0 = top
        h = PLATE_H
        # 🔴 **테두리는 가장자리에서 1px 안쪽에 그린다.** 맨 바깥에 그렸더니 화면에 아예
        #   안 보였고(엔진이 1px 을 잘라 간다), 엔진 칸까지 들여 그렸더니 이번엔 테두리
        #   **바깥에 밝은 여백**이 한 겹 보였다(유저 인게임 확인 2026-08-23, 둘 다).
        #   맨 바깥 1px 도 테두리 색으로 채워 두면 잘리든 안 잘리든 테두리로 보인다.
        im = Image.new("RGB", (w, h), PLATE_BG[sel])
        d = ImageDraw.Draw(im)
        k = PLATE_INSET
        # 🔴 테두리는 **두 겹** — 바깥 검정, 그 안쪽에 진한 녹색(유저 확정 2026-08-23).
        #   검정 한 겹만 가장자리에 두면 엔진이 잘라 가 안 보였고, 녹색만 안쪽에 두면 그
        #   바깥에 밝은 여백이 남았다. 두 겹이면 원본의 어두운 경계도 살고 잘려도 녹색이 남는다.
        mk = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mk).rounded_rectangle(
            [k, k, w - 1 - k, h - 1 - k], radius=PLATE_RADIUS, fill=255
        )
        arr = np.asarray(im).copy()
        arr[np.asarray(mk) == 0] = PLATE_EDGE_RGB  # 안쪽 라운드 바깥은 전부 어둡게
        im = Image.fromarray(arr)
        d = ImageDraw.Draw(im)
        bd = PLATE_BORDER_RGB[sel]
        d.rounded_rectangle(
            [k, k, w - 1 - k, h - 1 - k],
            radius=PLATE_RADIUS,
            outline=bd,
            width=PLATE_BORDER_W,
        )
        f = ImageFont.truetype(FONT_PATH, PLATE_FONT, layout_engine=BASIC_LAYOUT)
        # 🔴 **가로로 1px 불려 굵게 쓴다**(유저 확정 2026-08-24, 새턴과 같은 처리).
        #   네오둥근모엔 굵은 자형이 없어 합성한다 — 밝은 판에 짙은 글자라 얇은 획이 눌렸다.
        #   ⚠ 중앙정렬은 **불린 폭**으로 잰다. 원래 폭으로 재면 오른쪽으로 1px 쏠린다.
        #   ⚠ 안티에일리어스는 살린다 — 문턱으로 자르면 획이 계단진다.
        mt = Image.new("L", (w, h), 0)
        mtd = ImageDraw.Draw(mt)
        bb = mtd.textbbox((0, 0), text, font=f)
        mtd.text(
            ((w - (bb[2] - bb[0] + BOLD_X)) // 2 - bb[0], (h - (bb[3] - bb[1])) // 2 - bb[1]),
            text,
            fill=255,
            font=f,
        )
        base = np.asarray(mt).astype(np.float32)
        ta = base.copy()
        for kx in range(1, BOLD_X + 1):
            ta = np.maximum(ta, np.roll(base, kx, axis=1))
        al = (ta / 255)[..., None]
        arr2 = np.asarray(im).astype(np.float32) * (1 - al)
        arr2 += np.array(PLATE_INK[sel], np.float32) * al
        im = Image.fromarray(arr2.round().astype(np.uint8))
        newpix[y0 : y0 + h, x0 : x1 + 1] = quantize_region(np.asarray(im), clut)
    return newpix


def tim_bytes(buf, off, newpix, newclut=None):
    """원본 TIM 바이트에서 픽셀 블록(과 선택적으로 CLUT)을 교체한 새 바이트열."""
    t = parse_tim(buf, off)
    cbsize = struct.unpack_from("<I", buf, off + 8)[0]
    pix_off = 8 + cbsize + 12
    n = t["w"] * t["h"]
    blob = bytearray(buf[off : off + pix_off + n])
    blob[pix_off : pix_off + n] = newpix.astype(np.uint8).tobytes()
    if newclut is not None:
        cw = struct.unpack_from("<H", buf, off + 16)[0]
        ch = struct.unpack_from("<H", buf, off + 18)[0]
        blob[20 : 20 + cw * ch * 2] = rgb_to_clut(newclut).tobytes()[: cw * ch * 2]
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
        lpix, lclut = render_logo(coll)
        pix = render_coll_buttons(coll, lpix, lclut)
        n = write_user_data(
            f, COLL_OFF // 2048, tim_bytes(buf, COLL_OFF, pix, lclut), label="타이틀 로고 TIM"
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
