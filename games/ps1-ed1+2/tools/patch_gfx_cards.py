"""
챕터 카드 그래픽 재작성 — 192x45 8bpp TIM의 일본어를 한국어로 (graphics-text 트랙).

폰트 재삽입(reinsert_kr_pilot)으로 못 바꾸는 '이미지에 박힌 글자'를 그림 자체로 교체.
파이프라인 (2026-07-09 PoC 검증):
 1. 클린 플레이트 — 빨강 배너 안의 흰 글자/그림자를 같은 행 최근접 빨강으로 인페인트
 2. 한글 조판 — Neo둥근모(픽셀 폰트)로 2줄(장 표기 / 제목), 폭 자동맞춤·중앙정렬
 3. 팔레트 인덱스 재인코딩 — 본문=흰(idx 1), 그림자=최근접 어두운 인덱스 (RGB 왕복 없음)
 4. 원본 CLUT 유지한 채 픽셀만 교체 → 디스크 write-back + EDC (write_user_data)

번역: DOS 정발판 공식 챕터 제목 확인 후 확정 권장(현재는 초벌). 실행 순서: reinsert 후.
출력: 대상 디스크(기본 work/Eiyuu Densetsu (KR Pilot).bin) 제자리 패치.
"""

import os
import struct

import numpy as np
from common import BUILD_DIR, ROOT, write_user_data
from PIL import Image, ImageDraw, ImageFont
from scan_tim import parse_tim, to_rgb, user_stream

# ⚠ 레이아웃 엔진을 못 박는다 — Pillow 는 Raqm(HarfBuzz)이 있으면 그걸 기본으로 쓰는데,
# 같은 Pillow·FreeType 이어도 Raqm 유무로 **글자 배치가 달라진다**(macOS 휠 없음 / 리눅스 휠 있음).
# 그러면 같은 입력에도 머신마다 다른 이미지가 나온다(2026-08-09 실측: START.DAT 8섹터).
BASIC_LAYOUT = ImageFont.Layout.BASIC


FONT = os.path.join(ROOT, "..", "..", "shared", "fonts", "neodgm.ttf")
TARGET = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR Pilot).bin")

# (TIM 오프셋, 장 표기, 제목) — 오프셋은 scan_tim 인벤토리에서.
# 제목은 DOS 정발판(만트라) 공식 챕터 제목 (2026-07-09 확정).
CARDS = [
    (0x57F800, "제1장", "여행의 시작"),  # 王子の旅立ち
    (0x582000, "제2장", "침묵의 주문"),  # 沈黙の呪文
    (0x584800, "제3장", "국왕의 증명"),  # 王家のあかし
    (0x587000, "제4장", "홀려버린 국왕"),  # 魅せられた国王
    (0x589800, "제5장", "요상한 빛의 탑"),  # 妖しき光の塔
    (0x58C000, "종장", "그리고 영웅들의 전설"),  # そして英雄たちの伝説
    (0x918800, "서장", "평화로운 날"),  # 平和な日々
    (0x91B000, "제1장", "열려진 나락"),  # 開かれた奈落
    (0x91D800, "제2장", "영웅들의 행방"),  # 英雄たちの行方
    (0x920000, "제3장", "용의 알"),  # 竜の卵
    (0x922800, "제4장", "암흑의 지배자"),  # 暗黒の支配者
    (0x925000, "종장", "기원, 그리고 희망"),  # 祈り、そして希望
]
WHITE = 1  # 흰 글자 팔레트 인덱스 (192x45 챕터 카드 공통, 실측)


def rgb_of(clut, i):
    v = int(clut[i])
    return ((v & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3)


def clean_plate(pix, clut):
    """빨강 배너 안의 비-빨강(글자/그림자)을 같은 행 최근접 빨강으로 채움."""
    h, w = pix.shape

    def is_red(i):
        r, g, b = rgb_of(clut, i)
        return r > 55 and g < 55 and b < 55

    out = pix.copy()
    for y in range(h):
        reds = [x for x in range(w) if is_red(int(pix[y, x]))]
        if not reds:
            continue
        redset = set(reds)
        for x in range(min(reds), max(reds) + 1):
            if x not in redset:
                out[y, x] = pix[y, min(reds, key=lambda rx: abs(rx - x))]
    return out, (min(reds) if reds else 0)


def fit_font(text, max_w, start=16, lo=9):
    """폭 max_w에 맞는 최대 폰트 크기."""
    for size in range(start, lo - 1, -1):
        f = ImageFont.truetype(FONT, size, layout_engine=BASIC_LAYOUT)
        bb = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=f)
        if bb[2] - bb[0] <= max_w:
            return f, bb
    f = ImageFont.truetype(FONT, lo, layout_engine=BASIC_LAYOUT)
    return f, ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=f)


def render_mask(w, h, cx, panel_w, line1, line2):
    """2줄(장 표기/제목) 마스크. 반환: 본문 mask (bool)."""
    mask = np.zeros((h, w), dtype=bool)
    # y +3px: 텍스트 블록(~33px)이 배너(45px) 수직 중앙에 오도록 (원 3/20은 위 3px·아래 9px로 쏠림)
    for text, size0, ty in ((line1, 15, 6), (line2, 16, 23)):
        f, bb = fit_font(text, panel_w - 12, start=size0)
        tw = bb[2] - bb[0]
        im = Image.new("L", (w, h), 0)
        ImageDraw.Draw(im).text((cx - tw // 2 - bb[0], ty), text, fill=255, font=f)
        mask |= np.array(im) > 90
    return mask


def build_card(tim, line1, line2):
    """원본 TIM(dict) → 새 픽셀 인덱스 (clean plate + 한글)."""
    w, h, clut = tim["w"], tim["h"], tim["clut"]
    pix = np.frombuffer(tim["pix"], dtype=np.uint8).reshape(h, w).copy()
    shadow = min(range(256), key=lambda i: sum((a - 32) ** 2 for a in rgb_of(clut, i)))
    clean, _ = clean_plate(pix, clut)

    def is_red(i):
        r, g, b = rgb_of(clut, i)
        return r > 55 and g < 55 and b < 55

    reds = [x for y in range(h) for x in range(w) if is_red(int(pix[y, x]))]
    px0, px1 = min(reds), max(reds)
    mask = render_mask(w, h, (px0 + px1) // 2, px1 - px0, line1, line2)
    sh = np.zeros_like(mask)
    sh[1:, 1:] = mask[:-1, :-1]
    out = clean.copy()
    out[sh & ~mask] = shadow
    out[mask] = WHITE
    return out


def patch(target=TARGET, preview=None):
    if not os.path.exists(target):
        raise SystemExit(f"대상 디스크 없음: {target} — 먼저 reinsert_kr_pilot.py 실행")
    buf = user_stream()  # 원본에서 카드 TIM 읽기 (clean plate 정확성)
    previews = []
    with open(target, "r+b") as f:
        for off, l1, l2 in CARDS:
            tim = parse_tim(buf, off)
            assert tim and (tim["w"], tim["h"]) == (192, 45), f"0x{off:X} TIM 오류"
            new_pix = build_card(tim, l1, l2)
            # 원본 TIM 바이트에서 픽셀만 교체 후 write-back (CLUT 유지)
            bsize = struct.unpack_from("<I", buf, off + 8)[0]
            pix_off = 8 + bsize + 12
            tim_len = pix_off + tim["w"] * tim["h"]
            blob = bytearray(buf[off : off + tim_len])
            blob[pix_off : pix_off + tim["w"] * tim["h"]] = new_pix.astype(np.uint8).tobytes()
            # write_user_data 전제 검증: 섹터 정렬 + 마지막 부분 섹터는 0패딩으로 덮임
            if off % 2048:
                raise SystemExit(f"TIM 0x{off:X}: 섹터 비정렬 — write_user_data 사용 불가")
            tail = buf[off + tim_len : off + (tim_len + 2047) // 2048 * 2048]
            if any(tail):
                raise SystemExit(f"TIM 0x{off:X}: 꼬리 섹터 잔여가 0이 아님 — RMW 필요")
            n = write_user_data(f, off // 2048, blob)
            print(f"  0x{off:X} {l1} {l2} → 섹터 {n}개")
            if preview is not None:
                previews.append(build_preview(tim, new_pix))
    if preview is not None and previews:
        save_contact(previews, preview)
    print(f"챕터 카드 {len(CARDS)}장 패치 완료 → {os.path.basename(target)}")


def build_preview(tim, new_pix):
    t2 = dict(tim, pix=new_pix.astype(np.uint8).tobytes())
    return to_rgb(t2)


def save_contact(imgs, path):
    w, h = 192, 45
    sheet = Image.new("RGB", (w * 2 + 12, (h + 6) * len(imgs) // 2 + 6), (10, 10, 10))
    for i, im in enumerate(imgs):
        x = (i % 2) * (w + 8) + 4
        y = (i // 2) * (h + 6) + 4
        sheet.paste(im, (x, y))
    sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST).save(path)
    print(f"미리보기 → {path}")


if __name__ == "__main__":
    patch()
