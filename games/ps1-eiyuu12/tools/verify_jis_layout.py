"""
폰트 배열이 표준 JIS X 0208 순차 배열인지 검증.

가설: 글리프 주소 = FONT_BASE + jis_index * 24,
      jis_index = (ku-1)*94 + (ten-1),  (ku,ten = JIS 구점)
      あ(0x800F2DAC)로부터 역산한 FONT_BASE = 0x800F1324.

여러 문자(가나·한자)를 각자의 SJIS→JIS 구점으로 계산한 주소에서
글리프를 렌더해 실제 글자와 맞는지 눈으로 확인한다. 맞으면 매핑이 표준 →
한글 패치는 인덱스 루틴 역분석 없이 "한자 슬롯을 한글로 채우고 그 SJIS 코드로
인코딩"만으로 가능.
"""

import os

from common import OUT_DIR
from PIL import Image

MRAM = open(os.path.join(OUT_DIR, "mram.bin"), "rb").read()
FONT_BASE_RAM = 0x800F1324
GLYPH = 24


def sjis_to_jis_kuten(sjis):
    """SJIS 2바이트 → (ku, ten). 표준 변환."""
    hi, lo = sjis >> 8, sjis & 0xFF
    if hi >= 0xE0:
        hi -= 0x40
    hi -= 0x81
    if lo >= 0x80:
        lo -= 1
    lo -= 0x40
    ku = hi * 2 + 1
    ten = lo
    if lo >= 94:
        ku += 1
        ten = lo - 94
    return ku, ten + 1


def jis_index(sjis):
    ku, ten = sjis_to_jis_kuten(sjis)
    return (ku - 1) * 94 + (ten - 1)


def glyph_addr(sjis):
    return FONT_BASE_RAM + jis_index(sjis) * GLYPH


def render_glyph(sjis, scale=6):
    off = glyph_addr(sjis) - 0x80000000
    raw = MRAM[off : off + GLYPH]
    img = Image.new("L", (12, 12), 0)
    px = img.load()
    for r in range(12):
        v = (raw[r * 2] << 8) | raw[r * 2 + 1]
        for x in range(12):
            if v & (0x8000 >> x):
                px[x, r] = 255
    return img.resize((12 * scale, 12 * scale), Image.NEAREST)


def main():
    tests = {
        "あ": 0x82A0,
        "い": 0x82A2,
        "ん": 0x82F1,
        "王": 0x89A4,
        "子": 0x8E71,
        "兵": 0x95BA,
        "ア": 0x8341,
    }
    cols = len(tests)
    sheet = Image.new("L", (cols * 12 * 6 + (cols - 1) * 8, 12 * 6), 60)
    x = 0
    for ch, sjis in tests.items():
        ku, ten = sjis_to_jis_kuten(sjis)
        print(
            f"{ch}  SJIS 0x{sjis:04X} → 구점 {ku}-{ten}, index {jis_index(sjis)}, addr 0x{glyph_addr(sjis):08X}"
        )
        sheet.paste(render_glyph(sjis), (x, 0))
        x += 12 * 6 + 8
    out = os.path.join(OUT_DIR, "jis_layout_check.png")
    sheet.save(out)
    print(f"\n렌더 시트: {out}  (좌→우: {' '.join(tests)})")


if __name__ == "__main__":
    main()
