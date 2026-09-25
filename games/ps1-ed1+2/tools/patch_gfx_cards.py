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
# 🔴 **제목은 원문 번역이다**(유저 확정 2026-08-24). 정발 표기(만트라 DOS)를 쓰다가 자체
#   번역 방침에 맞춰 갈아탔다 — 열둘 중 일곱이 바뀌었다. 바뀐 까닭은 각 줄 주석에.
# ⚠ **새턴도 같이 바꾼다** — `ss-ed1+2/script/ui.json` 의 `cards`. 새턴은 카드가 문자열이라
#   수법만 다르고 문안은 하나여야 한다.
# 🔴 장 번호는 **전각 숫자**(U+FF11~)로 쓴다(마스터 확정 2026-09-15) — Neo둥근모에서
# 반각 숫자(advance 8px)가 한글(16px)의 절반이라 「제1장」줄에서 숫자만 작아 보인다.
# 실측: `1`(반각)=8px vs `１`(전각)=16px=한글과 동일. 「서장」·「종장」은 숫자가 없어 무관.
# ⚠ 새턴도 같이 바꾼다 — `ss-ed1+2/script/ui.json` 의 `cards`(문안은 하나여야 한다).
CARDS = [
    (0x57F800, "제１장", "왕자의 여행"),  # 王子の旅立ち — 정발은 「왕자」가 빠져 있었다.
    # ⚠ 旅立ち 는 「길을 나섬」이라 엄밀히는 「여행길」에 가깝다. 유저가 짧은 쪽을 골랐다(08-24)
    (0x582000, "제２장", "침묵의 주문"),  # 沈黙の呪文
    (0x584800, "제３장", "국왕의 증표"),  # 国王のあかし — あかし = 증표. ⚠ 옛 주석의 「王家」는 오기
    (0x587000, "제４장", "매혹된 국왕"),  # 魅せられた国王 — 魅せられた = 매혹된
    (0x589800, "제５장", "요사한 빛의 탑"),  # 妖しき光の塔 — 妖しき는 구어가 아니다
    (0x58C000, "종장", "그리고 영웅들의 전설"),  # そして英雄たちの伝説
    (0x918800, "서장", "평화로운 나날"),  # 平和な日々 — 日々 = 나날
    (0x91B000, "제１장", "열려버린 나락"),  # 開かれた奈落 — 정발 「열려진」은 이중피동.
    # ⚠ 원문엔 〜てしまった 가 없어 「열린」이 축자다. 유저가 어감을 살리는 쪽을 골랐다(08-24)
    (0x91D800, "제２장", "영웅들의 행방"),  # 英雄たちの行方
    (0x920000, "제３장", "용의 알"),  # 竜の卵
    (0x922800, "제４장", "암흑의 지배자"),  # 暗黒の支配者
    (0x925000, "종장", "기도, 그리고 희망"),  # 祈り、そして希望 — 祈り = 기도
]
WHITE = 1  # 흰 글자 팔레트 인덱스 (192x45 챕터 카드 공통, 실측)


def rgb_of(clut, i):
    v = int(clut[i])
    return ((v & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3)


# ── 클린 플레이트 — 카드 여섯 장이 서로의 지우개다 (2026-08-24 재작성) ──────────
# 🔴 옛 방식(같은 행 최근접 빨강으로 메우기)은 두 가지를 망쳤다:
#   1. 배너 안쪽의 **가는 금색 테두리를 통째로 지웠다** — 금색은 「빨강」이 아니라 메움
#      대상이었다. 원본에 있는 선이 열두 장 전부에서 없어져 있었다.
#   2. 대각 결 무늬를 가로로 끌어 **흐릿한 줄 자국**이 남았다(카드끼리 1,579화소가 어긋난다).
# 지금은 새턴 챕터 판과 같은 수법을 쓴다 — **같은 CLUT 을 쓰는 카드 여섯 장의 최빈값**.
# 글자 자리가 서로 다르니 배너가 그대로 복원된다.
CORE_LUM = 600  # 이 밝기 위 = 이견 없는 글자 본색
INK_NEAR = 2  # 잉크 둘레 몇 px 까지를 「곁」으로 보나
INK_RATIO = 0.7  # 그 안에서만 나오면 잉크 부속. 실측 분포는 0.49 아래 / 0.88 위로 갈린다


def ink_indices(stack, clut):
    """잉크 색인을 **데이터에서** 뽑는다 — 흰 글자 둘레에서만 나오는 색이 잉크 부속이다."""
    from scipy.ndimage import binary_dilation

    lum = [sum(rgb_of(clut, i)) for i in range(256)]
    core = np.isin(stack, [i for i in range(256) if lum[i] > CORE_LUM])
    near = np.stack([binary_dilation(m, iterations=INK_NEAR) for m in core])
    got = set()
    for v in np.unique(stack):
        m = stack == v
        if (m & near).sum() / m.sum() >= INK_RATIO:
            got.add(int(v))
    return got


def clean_plate(pix_list, clut):
    """같은 CLUT 카드 여러 장 → 글자 없는 배너 하나.

    ⚠ 잉크만 빼고 최빈값을 잡으면 **글자 둘레 자국이 남는다** — 여러 장이 같은 자리에
      `第`·`章` 을 쓰기 때문이다. 마스크를 2px 부풀리고, 표본이 없으면 부풀리기 전으로
      물러선다(테두리가 글자에 닿는 자리). 그래도 없으면 최근접으로 메운다.
    """
    from scipy.ndimage import binary_dilation, distance_transform_edt

    stack = np.stack(pix_list)
    inks = ink_indices(stack, clut)
    ink = np.isin(stack, sorted(inks))
    grown = np.stack([binary_dilation(m, iterations=INK_NEAR) for m in ink])
    h, w = stack.shape[1:]
    bg = np.zeros((h, w), np.uint8)
    tier = np.zeros((h, w), np.uint8)

    def mode(v):
        val, cnt = np.unique(v, return_counts=True)
        return val[np.lexsort((val, -cnt))[0]]  # 동점은 작은 색인 — 결정성

    for y in range(h):
        for x in range(w):
            for t, m in ((1, grown), (2, ink)):
                v = stack[~m[:, y, x], y, x]
                if v.size:
                    bg[y, x], tier[y, x] = mode(v), t
                    break
            else:
                tier[y, x] = 3
    hole = tier == 3
    if hole.any():
        _, idx = distance_transform_edt(hole, return_indices=True)
        bg[hole] = bg[idx[0][hole], idx[1][hole]]
    left = sorted({int(v) for v in np.unique(bg)} & inks)
    if left:
        raise SystemExit(f"배너에 잉크 색인이 남았다 — {left}")
    return bg, int((tier == 2).sum()), int(hole.sum())


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
    # 🔴 두 줄 다 16px(마스터 확정 2026-09-15, B안). 원문 JP 잉크 실측(TIM 0x57F800 직접
    # 측정)은 두 줄 다 ~15px span 이었지만, **이 폰트에서 15px 는 이미 16px 를 뭉갠 것**이다
    # — 잉크 화소 중 회색(안티에일리어싱) 비율을 재면 14px 77% · 15px 68~70% · **16px 0%**
    # (Neo둥근모는 픽셀 폰트라 설계 크기 16 에서만 도트가 깨끗이 떨어진다). 장 표기 줄을
    # 15px 로 굽던 예전 빌드도 이미 뭉개진 상태였는데, 한글은 획이 단순해 안 티가 났고
    # 전각 숫자(굵고 곧은 획)에서 드러났다 — "원문보다 키운다"가 아니라 "있던 결함을
    # 없앤다"에 가깝다. 폭도 넉넉하다(가장 긴 장 표기 "제１장"=48px, 한도 161px).
    for text, size0, ty in ((line1, 16, 6), (line2, 16, 23)):
        f, bb = fit_font(text, panel_w - 12, start=size0)
        tw = bb[2] - bb[0]
        x = cx - tw // 2 - bb[0]
        im = Image.new("L", (w, h), 0)
        ImageDraw.Draw(im).text((x, ty), text, fill=255, font=f)
        arr = np.array(im) > 90
        mask |= arr
        # 🔴 가로 중앙 정렬 회귀 방지(마스터 지시 2026-09-15) — 폭이 바뀔 때마다(전각화 등)
        # 정렬이 안 흔들렸는지 값으로 확인한다(sfc-ed1 이 같은 날 폭만 바꾸고 정렬을 안 봐서
        # 숫자가 치우쳤던 사고와 같은 부류). 실측 잉크 중심이 cx 에서 1px 넘게 벗어나면 실패.
        rows_cols = np.where(arr)
        if rows_cols[1].size:
            ink_center = (rows_cols[1].min() + rows_cols[1].max()) / 2
            assert abs(ink_center - cx) <= 1, (
                f"가로 중앙 어긋남 — {text!r} 잉크중심={ink_center:.1f} cx={cx} (1px 초과)"
            )
    return mask


def banners(buf):
    """CLUT 별로 카드를 모아 깨끗한 배너를 하나씩 만든다 → `{clut 바이트: 배너}`.

    ED1·ED2 가 CLUT 이 달라 두 벌이 나온다. ⚠ **자리로 가르지 않는다** — CLUT 이 기준이다.
    """
    groups = {}
    for off, _l1, _l2 in CARDS:
        tim = parse_tim(buf, off)
        key = bytes(np.asarray(tim["clut"]).tobytes())
        h, w = tim["h"], tim["w"]
        groups.setdefault(key, (tim["clut"], []))[1].append(
            np.frombuffer(tim["pix"], dtype=np.uint8).reshape(h, w)
        )
    out = {}
    for key, (clut, px) in groups.items():
        bg, fell, filled = clean_plate(px, clut)
        out[key] = bg
        print(f"  배너 복원 — 카드 {len(px)}장 최빈값 · 물러섬 {fell} · 최근접 {filled}")
    return out


def build_card(tim, line1, line2, clean):
    """원본 TIM(dict) + 깨끗한 배너 → 새 픽셀 인덱스."""
    w, h, clut = tim["w"], tim["h"], tim["clut"]
    pix = np.frombuffer(tim["pix"], dtype=np.uint8).reshape(h, w).copy()
    shadow = min(range(256), key=lambda i: sum((a - 32) ** 2 for a in rgb_of(clut, i)))

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
    bg = banners(buf)
    previews = []
    with open(target, "r+b") as f:
        for off, l1, l2 in CARDS:
            tim = parse_tim(buf, off)
            assert tim and (tim["w"], tim["h"]) == (192, 45), f"0x{off:X} TIM 오류"
            new_pix = build_card(tim, l1, l2, bg[bytes(np.asarray(tim["clut"]).tobytes())])
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
            n = write_user_data(f, off // 2048, blob, label="챕터 카드 TIM")
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
