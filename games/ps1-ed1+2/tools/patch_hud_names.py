"""상태창 HUD 이름판 한글화 — 0x566800 TIM(220x215 8bpp)의 캐릭터명을 한글로 (graphics-text 트랙).

파티 상태창(scan_tim으로 색출)은 각 패널 좌상단에 캐릭터명이 **노란 카타카나 그래픽**으로 박혀
있다(セリオス/リュナン/ロー/ゲイル/ソニア). 폰트 재삽입으로 못 바꾸므로 픽셀을 교체:
 1. 이름 영역(x2~43, EP 라벨 x44+ 앞)을 배경 남색(idx39)으로 인페인트
 2. Galmuri9(9px 비트맵)로 한글 조판 → 글자=노랑(idx16), 그림자=idx46(원본과 동일)
 3. 원본 CLUT 유지, 픽셀만 교체 → RMW-safe write-back(꼬리 섹터 보존)

EP/HP/MP/Lv/Gold/숫자·프레임은 그대로 둔다. 번역명은 **잠정**(최종검수 나중).
실행 순서: patch_gfx_cards 후(TARGET=KR Pilot). 팔레트 인덱스는 0x566800 실측(2026-07-14).
"""

import os
import struct

import hangul_font
import numpy as np
from common import BUILD_DIR, write_user_data
from scan_tim import parse_tim, to_rgb, user_stream

TIM_OFF = 0x566800  # ED1PARTS.DAT 내, 섹터정렬(LBA 2765)
TARGET = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR Pilot).bin")
BG, MAIN, SHADOW = 39, 16, 46  # 남색 배경 / 노랑 글자 / 그림자 (실측)
PITCH = 9  # Galmuri9 글자 간격(원본 카타카나 ~9px)
NAME_X = 6  # 이름 시작 x (원본과 동일)
NAME_X_MAX = 43  # EP 라벨(x44+) 앞 한계 — 인페인트/폭 상한

# (이름 잉크 top y, 일본어 원문, 한글 잠정). ink_top은 scan 검출값. 배치 oy=ink_top-2(11행 baseline).
NAMES = [
    (6, "セリオス", "세리오스"),
    (49, "リュナン", "류난"),
    (93, "ロー", "로우"),
    (135, "ゲイル", "게일"),
    (178, "ソニア", "소니아"),
]

_glyphs, _ascent = hangul_font.load_bdf(hangul_font.GALMURI11_BDF.replace("Galmuri11", "Galmuri9"))
# 라벨(あと→남다)용 7px 폰트 — 라벨 UV 창이 14px(7×2)라 9px 글리프는 잘림
_glyphs7, _ascent7 = hangul_font.load_bdf(
    hangul_font.GALMURI11_BDF.replace("Galmuri11", "Galmuri7")
)


def render_name(s, pitch=PITCH, font7=False):
    """이름 → bool 비트맵(높이=ascent, 폭=음절수×pitch). Galmuri 도트, baseline 정렬."""
    glyphs, ascent = (_glyphs7, _ascent7) if font7 else (_glyphs, _ascent)
    width = len(s) * pitch
    bm = np.zeros((ascent, width), dtype=bool)
    for ci, ch in enumerate(s):
        g = glyphs.get(ord(ch))
        if not g:
            print(f"경고: {ch!r} Galmuri9 글리프 없음")
            continue
        gw, gh, xo, yo, rows = g
        top = ascent - (yo + gh)
        nb = ((gw + 7) // 8) * 8
        for r, v in enumerate(rows):
            y = top + r
            if 0 <= y < ascent:
                for x in range(gw):
                    px = ci * pitch + xo + x
                    if v & (1 << (nb - 1 - x)) and 0 <= px < width:
                        bm[y, px] = True
    return bm


# EP 표시 모드="앞으로"일 때 HUD가 쓰는 잔량 라벨 「あと」 — 문자열이 아니라 이 TIM의
# 스프라이트 영역(우측)에 EP 라벨과 세로로 나란히 박힌 **그래픽**이다(에뮬 RAM 전수검색으로
# 문자열 부재 확정, 2026-07-14). 게임이 모드에 따라 EP/あと 부분을 UV로 잘라 그린다.
# あと 잉크 y110~118 · EP 잉크 y119~127 (x106-107은 경계선 스트라이프 — 보존).
# 본문=idx35(청록), 음영=idx37 (EP 라벨과 동일). 정발판 라벨 "남다"로 교체.
# UV 창 = x110~121(12px)·인게임 실측 확정: x108 배치→남 왼쪽 잘림, x110+7px피치→다 오른쪽 잘림.
# 12px에 2자 = 6px/자 → 전용 커스텀 도트(아래). 잉크 y110~116, 음영 +1(창 안 클립).
ATO = {"y0": 109, "y1": 118, "x0": 108, "x1": 125, "ink_top": 110, "x": 110}
ATO_MAIN, ATO_SHADOW = 35, 37
# 남·다 6×9 커스텀 도트 — UV 12px 창 전용. 세로는 창 높이(9행) 꽉 채워 HP/MP와 비슷한 키로.
ATO_GLYPHS = [
    [  # 남
        "#...#.",
        "#...#.",
        "#...##",
        "###.#.",
        "......",
        ".####.",
        ".#..#.",
        ".#..#.",
        ".####.",
    ],
    [  # 다
        "###.#.",
        "#...#.",
        "#...##",
        "#...#.",
        "#...#.",
        "#...#.",
        "#...#.",
        "###.#.",
        "....#.",
    ],
]


# HUD 상태이상 그래픽 라벨 — 같은 TIM에 문자열이 아니라 도트로 박혀 있다(필드 HUD가 사용,
# 유저 기절 스크린샷으로 발견 2026-07-26). 전투 HUD의 문자열판(ED.EXE 0xF91D8)과 별개.
# 1행 毒黙呪眠乱(빨강 idx24)+守跳(노랑 idx50/16): x110부터 **피치 10**, 잉크 y129~140.
# 2행 気絶(빨강): 気=x110~119·絶=x121~130, 잉크 y141~148(8행 — 9px 폰트는 잘림 → Galmuri7).
# 글리프끼리 맞닿아 색으로만 분리 가능 — 빨강/노랑 픽셀만 지우고(프레임·배경 보존) 다시 그린다.
# 라벨은 patch_sys_ui.STATUS_LABELS와 동일 표기(독·묵·주·잠·란) + 수·도(守=수비, 跳=도약 잠정).
STATUS_RED, STATUS_YELS = 24, (50, 16)
STATUS_ROW1 = [  # (x, 글자, 잉크색)
    (110, "독", 24),
    (120, "묵", 24),
    (130, "주", 24),
    (140, "잠", 24),
    (150, "란", 24),
    (160, "수", 50),
    (170, "도", 50),
]
FAINT = {"x": 110, "chars": "기절", "pitch": 10, "ink_top": 141, "y1": 148, "color": 24}


def _draw_bm(pix, bm, ox, oy, color, y_max=None, x_max=None):
    bh, bw = bm.shape
    for y in range(bh):
        for x in range(bw):
            if (
                bm[y, x]
                and (y_max is None or oy + y <= y_max)
                and (x_max is None or ox + x <= x_max)
            ):
                pix[oy + y, ox + x] = color


def patch_status_labels(pix):
    # 지우기: 상태 영역의 잉크색만 배경으로(글리프가 맞닿아 사각 인페인트 불가)
    band1 = pix[128:141, 108:182]
    band1[np.isin(band1, (STATUS_RED, *STATUS_YELS))] = BG
    band2 = pix[141:150, 108:136]
    band2[band2 == STATUS_RED] = BG
    for x, ch, color in STATUS_ROW1:
        bm = render_name(ch)  # 11행 셀, 잉크 2~10행
        _draw_bm(pix, bm, x, 129 - 2, color, y_max=140, x_max=x + 9)
    f = FAINT
    bm = render_name(f["chars"], pitch=f["pitch"], font7=True)  # 9행 셀(ascent7), 잉크 2~8행
    _draw_bm(pix, bm, f["x"], f["ink_top"] - 2, f["color"], y_max=f["y1"])


def build_pix(tim):
    """원본 TIM 픽셀 → 이름 5개 + あと 라벨 + 상태이상 라벨 교체한 새 인덱스맵."""
    w, h = tim["w"], tim["h"]
    pix = np.frombuffer(tim["pix"], dtype=np.uint8).reshape(h, w).copy()
    for ink_top, _jp, kr in NAMES:
        bm = render_name(kr)
        bh, bw = bm.shape
        if NAME_X + bw > NAME_X_MAX:
            print(f"경고: {kr!r}({bw}px) 이름칸 초과 — EP 라벨 침범 가능")
        oy = ink_top - 2  # 11행 셀 잉크가 y=ink_top부터 오도록
        pix[oy : oy + 13, 2:NAME_X_MAX] = BG  # 인페인트(원 카타카나 지움)
        for y in range(bh):  # 그림자 먼저(+1,+1)
            for x in range(bw):
                if bm[y, x] and oy + y + 1 < h and NAME_X + x + 1 < w:
                    pix[oy + y + 1, NAME_X + x + 1] = SHADOW
        for y in range(bh):  # 본문 노랑
            for x in range(bw):
                if bm[y, x] and oy + y < h and NAME_X + x < w:
                    pix[oy + y, NAME_X + x] = MAIN

    # あと → 남다 (정발 라벨). y0~y1·x0~x1만 인페인트(아래 EP·좌측 경계선 보존),
    # 잉크는 원본과 같은 y(ink_top)에서 시작 — UV 크롭이 딱 맞아도 잘리지 않게.
    a = ATO
    pix[a["y0"] : a["y1"] + 1, a["x0"] : a["x1"] + 1] = BG
    bm = np.zeros((len(ATO_GLYPHS[0]), 12), dtype=bool)  # 남다 6px×2 커스텀 도트
    for ci, rows in enumerate(ATO_GLYPHS):
        for ry, row in enumerate(rows):
            for rx, ch in enumerate(row):
                if ch == "#":
                    bm[ry, ci * 6 + rx] = True
    oy = a["ink_top"]  # 커스텀 도트는 셀 여백 없이 ink_top부터
    bh, bw = bm.shape
    for y in range(bh):  # 음영(+1,+1) — 라벨 창(y1) 밖은 스킵
        for x in range(bw):
            if bm[y, x] and oy + y + 1 <= a["y1"] and a["x"] + x + 1 <= a["x1"]:
                pix[oy + y + 1, a["x"] + x + 1] = ATO_SHADOW
    for y in range(bh):  # 본문 청록
        for x in range(bw):
            if bm[y, x] and oy + y <= a["y1"] and a["x"] + x <= a["x1"]:
                pix[oy + y, a["x"] + x] = ATO_MAIN

    patch_status_labels(pix)  # 상태이상 라벨(독~란·수·도·기절)
    return pix


def patch(target=TARGET, preview=None):
    if not os.path.exists(target):
        raise SystemExit(f"대상 디스크 없음: {target} — build.py 체인(reinsert→gfx_cards) 먼저")
    buf = user_stream()  # 원본에서 TIM 읽기(clean 인페인트 정확성)
    tim = parse_tim(buf, TIM_OFF)
    assert tim and (tim["w"], tim["h"]) == (220, 215), f"0x{TIM_OFF:X} TIM 불일치"
    new_pix = build_pix(tim)
    # 픽셀만 교체, CLUT·헤더 유지. RMW-safe: TIM 시작~다음 섹터경계까지 통째로 blob(꼬리 보존).
    bsize = struct.unpack_from("<I", buf, TIM_OFF + 8)[0]
    pix_off = 8 + bsize + 12
    tim_len = pix_off + tim["w"] * tim["h"]
    assert TIM_OFF % 2048 == 0, "TIM 섹터 비정렬 — write_user_data 불가"
    end = TIM_OFF + (tim_len + 2047) // 2048 * 2048  # 다음 섹터 경계
    blob = bytearray(buf[TIM_OFF:end])  # 전체 섹터(꼬리 원본 보존)
    blob[pix_off : pix_off + tim["w"] * tim["h"]] = new_pix.astype(np.uint8).tobytes()
    with open(target, "r+b") as f:
        n = write_user_data(f, TIM_OFF // 2048, blob)
    print(
        f"HUD 이름판 {len(NAMES)}명 → 0x{TIM_OFF:X} (섹터 {n}개): "
        + ", ".join(k for _, _, k in NAMES)
    )
    if preview:
        to_rgb(dict(tim, pix=new_pix.astype(np.uint8).tobytes())).resize((220 * 3, 215 * 3)).save(
            preview
        )
        print(f"미리보기 → {preview}")


if __name__ == "__main__":
    patch()
