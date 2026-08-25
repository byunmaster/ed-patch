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
import sys

import hangul_font
import numpy as np
from common import BUILD_DIR, write_user_data
from scan_tim import parse_tim, to_rgb, user_stream

# ── 게임별 이름판 (2026-08-16) ────────────────────────────────────────────────
# ED2 도 **같은 크기(220x215)·같은 팔레트·같은 라벨 배치**의 TIM 을 쓴다 —
# `ED2PARTS.DAT` 0xC000(디스크 LBA 4611 = 0x901800). `あと/EP`·`毒黙呪眠乱守跳`·`気絶`
# 영역이 ED1 과 픽셀까지 같아, 갈리는 건 **이름 넉 줄뿐**이다(ED2 파티는 4명).
# ⚠ 폰 QA 에서 HUD 가 `アトラス`·`あと` 로 남아 있었다 — 문자열이 아니라 그림이라
# SJIS 검출기가 원리상 못 본다(디스크 전 파일 스캔 0곳).
TIM_OFF = 0x566800  # ED1PARTS.DAT 내, 섹터정렬(LBA 2765)
TIM_OFF_ED2 = 0x901800  # ED2PARTS.DAT 0xC000, 섹터정렬(LBA 4611)
TARGET = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR Pilot).bin")
BG, MAIN, SHADOW = 39, 16, 46  # 남색 배경 / 노랑 글자 / 그림자 (실측)
PITCH = 9  # Galmuri9 글자 간격(원본 카타카나 ~9px)
NAME_X = 6  # 이름 시작 x (원본과 동일)
# ⚠ 43 이었는데 **실측하니 EP 는 x46 부터**다(x41~45 는 두 TIM 다 비어 있다 — 자간을
#   비례로 바꾸며 `아트라스`(39px)가 안 들어가 다시 쟀다, 2026-08-25). 인페인트도 같이 넓힌다.
NAME_X_MAX = 46  # EP 라벨(x46+) 앞 한계 — 인페인트/폭 상한

# (이름 잉크 top y, 일본어 원문, 한글 잠정). ink_top은 scan 검출값. 배치 oy=ink_top-2(11행 baseline).
NAMES = [
    (6, "セリオス", "세리오스"),
    (49, "リュナン", "류난"),
    (93, "ロー", "로우"),
    (135, "ゲイル", "게일"),
    (178, "ソニア", "소니아"),
]
# ED2 — 잉크 top 실측(6/49/92/135). 순서는 렌더로 확인했다(アトラス→ランドー→フローラ→シンディ).
NAMES_ED2 = [
    (6, "アトラス", "아트라스"),
    (49, "ランドー", "란도"),
    (92, "フローラ", "플로라"),
    (135, "シンディ", "신디"),
]
GAMES = {"ED1": (TIM_OFF, NAMES), "ED2": (TIM_OFF_ED2, None)}  # None → NAMES_ED2 (아래서 채움)
GAMES["ED2"] = (TIM_OFF_ED2, NAMES_ED2)

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
# ⚠ x0 은 **잉크 시작(x=110)과 같아야** 한다. 108 로 두면 x108(idx33)·x109(idx1) 세로
# 테두리를 배경으로 덮는다 — 시트에서 그 자리가 로우 패널 구간이라 **인게임에서 로우 칸만
# 오른쪽 테두리가 사라졌다**(유저 QA 2026-08-04). 원본은 x108/109 전 행이 테두리 단색이고
# あと 글자는 x110 부터다.
# ⚠ `ink_top` 이 110 이었다 — **창은 109 부터인데 한 줄을 비워 두고 있었다.** 원본 `あと` 는
#   9행이지만 바로 아래 `ＥＰ` 는 **10행**(y119~128)이라 나란히 놓으면 잔량만 작아 보인다
#   (유저 지적 2026-08-25). 109 로 올려 10행을 다 쓴다.
ATO = {"y0": 109, "y1": 118, "x0": 110, "x1": 125, "ink_top": 109, "x": 110}
ATO_MAIN, ATO_SHADOW = 35, 37
# 남·다 **6×10** 커스텀 도트 — UV 12px 창 전용. `(잉크, 음영)` 한 쌍씩.
# 🔴 **음영을 유도하지 않고 손으로 적는다**(2026-08-25, 새턴과 같은 규약). 「안쪽」이 어디인지는
#    자모마다 다르다 — 원본 `ＥＰ` 가 **테두리는 밝고 속이 어두운** 2px 획이라 맨 아래 획엔
#    아래쪽 음영이 없다. 자모별 규칙(유저 확정):
#      ㄴ: 세로 오른쪽만(가로 위는 뺀다) · ㄷ: 아래·오른·위 · ㅁ: **좌우만**(위아래는 뺀다)
#      · ㅏ: 가지 아래만 — **ㅣ 에는 안 넣는다**(오른쪽 한 열이 차면 옆 글자와 붙어 보인다)
# ⚠ **ㅏ 의 가지는 세로줄 오른쪽**이다 — 왼쪽에 붙이면 ㅓ 가 되어 「남다」가 「넘더」로 읽힌다.
ATO_GLYPHS = [
    (  # 남
        (
            "#...#.",
            "#...#.",
            "#...##",
            "#...#.",
            "###.#.",
            "......",
            "#####.",
            "#...#.",
            "#...#.",
            "#####.",
        ),
        (
            ".+....",
            ".+....",
            ".+....",
            ".+...+",
            "......",
            "......",
            "......",
            ".+.+..",
            ".+.+..",
            "......",
        ),
    ),
    (  # 다
        (
            "###.#.",
            "#...#.",
            "#...##",
            "#...#.",
            "#...#.",
            "#...#.",
            "#...#.",
            "#...#.",
            "#...#.",
            "###.#.",
        ),
        (
            "......",
            ".++...",
            ".+....",
            ".+...+",
            ".+....",
            ".+....",
            ".+....",
            ".+....",
            ".++...",
            "......",
        ),
    ),
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
    (150, "혼", 24),  # 乱 — 정발 표기(음차 `란` 아님)
    (160, "수", 50),
    (170, "반", 50),  # 跳ね返す = 반사(리파크) — 정발 표기
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


def inner_shadow(bits):
    """`bits` → **속으로만 들어가는 음영 좌표**(한 칸 아래).

    🔴 원본 `ＥＰ`·`ＨＰ`·`ＭＰ` 는 획이 2px 라 **바깥 테두리가 밝고 속이 어둡다**.
       그래서 **맨 아래 획에는 아래쪽 음영이 없다**(유저 지적 2026-08-25). 1px 획으로
       그 관계를 흉내 내는 규칙은 하나다 — 한 칸 아래에 음영을 넣되, **그 열에 아직 더
       아래쪽 잉크가 남아 있을 때만.** `+1,+1` 대각선으로 깔면 글자 아래로 한 줄이 삐져나온다.
    """
    last = np.where(bits.any(0), bits.shape[0] - 1 - bits[::-1].argmax(0), -1)
    ys, xs = np.nonzero(bits)
    m = ys + 1 < last[xs]
    return ys[m] + 1, xs[m]


def pack_name(s, font7=False):
    """이름 → bool 비트맵. **자간은 「잉크 폭 + 틈 1」**이다(고정 피치가 아니다).

    🔴 Galmuri9 한글은 글자마다 잉크 폭이 다르다 — `세`·`오`·`스` 는 9px 인데 `리` 는 8px 다.
       피치를 고정하면 **`리` 뒤만 틈이 2px** 가 되어 「리 오」 사이가 벌어져 보인다
       (유저 지적 2026-08-25).
    🔴 **`오`+`스` 처럼 가로바끼리 만나는 자리도 특별대우하지 않는다**(유저 확정 2026-08-26).
       둘 다 9px 짜리 가로바라 1px 을 두면 **19px 한 줄**로 읽히는 건 사실이고, 그래서
       **깎는 안 넷과 벌리는 안 셋을 다 만들어 실기에서 봤다.** 결론은 「손 안 댄 게 낫다」다.
       ⚠ **다시 손대려거든 여기부터 읽을 것** — 두 축 다 막혀 있다.
         · **깎기**: `ㅗ` 의 세로줄이 9px 글리프의 **정중앙**이라 바가 제 축에 대칭이려면
           **폭이 홀수**여야 한다 → 9(붙는다) 아니면 7(짧아 보인다) 뿐이고 **8 은 반드시
           반 칸 기운다.**
         · **벌리기**: `세리오스` 는 잉크가 9+8+9+9 = 35px 인데 이름칸이 40px 이라 **자간에
           쓸 게 5px** 뿐이다. 자간이 셋이니 `2,2,2`(6px)가 안 되고 **하나는 반드시 1px** 이다.
       (새턴도 같다 — `ss-ed1+2/tools/patch_gfx_hud.py:draw`)
    """
    cells = []
    for ch in s:
        one = render_name(ch, pitch=PITCH, font7=font7)
        cols = np.nonzero(one.any(0))[0]
        cells.append(one[:, cols.min() : cols.max() + 1] if cols.size else one[:, :1])
    width = sum(c.shape[1] for c in cells) + (len(cells) - 1)
    bm = np.zeros((cells[0].shape[0], width), dtype=bool)
    at = 0
    for c in cells:
        bm[:, at : at + c.shape[1]] = c
        at += c.shape[1] + 1
    return bm


def build_pix(tim, names=None):
    """원본 TIM 픽셀 → 이름 5개 + あと 라벨 + 상태이상 라벨 교체한 새 인덱스맵."""
    w, h = tim["w"], tim["h"]
    pix = np.frombuffer(tim["pix"], dtype=np.uint8).reshape(h, w).copy()
    for ink_top, _jp, kr in names or NAMES:
        bm = pack_name(kr)
        bh, bw = bm.shape
        if NAME_X + bw > NAME_X_MAX:
            print(f"경고: {kr!r}({bw}px) 이름칸 초과 — EP 라벨 침범 가능")
        oy = ink_top - 2  # 11행 셀 잉크가 y=ink_top부터 오도록
        pix[oy : oy + 13, 2:NAME_X_MAX] = BG  # 인페인트(원 카타카나 지움)
        sy, sx = inner_shadow(bm)  # 음영 먼저 — 「안쪽으로만」(위 주석)
        for y, x in zip(sy, sx, strict=True):
            if oy + y < h and NAME_X + x < w:
                pix[oy + y, NAME_X + x] = SHADOW
        for y in range(bh):  # 본문 노랑
            for x in range(bw):
                if bm[y, x] and oy + y < h and NAME_X + x < w:
                    pix[oy + y, NAME_X + x] = MAIN

    # あと → 남다 (정발 라벨). y0~y1·x0~x1만 인페인트(아래 EP·좌측 경계선 보존),
    # 잉크는 원본과 같은 y(ink_top)에서 시작 — UV 크롭이 딱 맞아도 잘리지 않게.
    a = ATO
    pix[a["y0"] : a["y1"] + 1, a["x0"] : a["x1"] + 1] = BG
    oy = a["ink_top"]  # 커스텀 도트는 셀 여백 없이 ink_top부터
    for ci, (ink, sh) in enumerate(ATO_GLYPHS):
        for layer, colr in ((sh, ATO_SHADOW), (ink, ATO_MAIN)):
            for ry, row in enumerate(layer):
                for rx, ch in enumerate(row):
                    x = a["x"] + ci * 6 + rx
                    if ch != "." and oy + ry <= a["y1"] and x <= a["x1"]:
                        pix[oy + ry, x] = colr

    patch_status_labels(pix)  # 상태이상 라벨(독~란·수·도·기절)
    return pix


def patch(target=TARGET, preview=None, game="ED1"):
    if not os.path.exists(target):
        raise SystemExit(f"대상 디스크 없음: {target} — build.py 체인(reinsert→gfx_cards) 먼저")
    tim_off, names = GAMES[game]
    buf = user_stream()  # 원본에서 TIM 읽기(clean 인페인트 정확성)
    tim = parse_tim(buf, tim_off)
    assert tim and (tim["w"], tim["h"]) == (220, 215), f"0x{tim_off:X} TIM 불일치"
    new_pix = build_pix(tim, names)
    # 픽셀만 교체, CLUT·헤더 유지. RMW-safe: TIM 시작~다음 섹터경계까지 통째로 blob(꼬리 보존).
    bsize = struct.unpack_from("<I", buf, tim_off + 8)[0]
    pix_off = 8 + bsize + 12
    tim_len = pix_off + tim["w"] * tim["h"]
    assert tim_off % 2048 == 0, "TIM 섹터 비정렬 — write_user_data 불가"
    end = tim_off + (tim_len + 2047) // 2048 * 2048  # 다음 섹터 경계
    blob = bytearray(buf[tim_off:end])  # 전체 섹터(꼬리 원본 보존)
    blob[pix_off : pix_off + tim["w"] * tim["h"]] = new_pix.astype(np.uint8).tobytes()
    with open(target, "r+b") as f:
        n = write_user_data(f, tim_off // 2048, blob, label=f"HUD 이름 TIM ({game})")
    print(
        f"HUD 이름판[{game}] {len(names)}명 → 0x{tim_off:X} (섹터 {n}개): "
        + ", ".join(k for _, _, k in names)
    )
    if preview:
        to_rgb(dict(tim, pix=new_pix.astype(np.uint8).tobytes())).resize((220 * 3, 215 * 3)).save(
            preview
        )
        print(f"미리보기 → {preview}")


if __name__ == "__main__":
    for g in sys.argv[1:] or ["ED1"]:
        patch(game=g)
