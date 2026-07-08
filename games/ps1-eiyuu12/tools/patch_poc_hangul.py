"""
개념증명: 폰트의 あ 글리프(24B)를 한글 「가」 12×12 비트맵으로 교체.

성공 기준: 게임 내 모든 あ가 「가」로 렌더링 — PS1 영웅전설에 한글 출력이
원리적으로 가능함을 증명. ED.EXE(ED1)와 ED2.EXE(ED2) 양쪽 모두 패치.
글리프 소스는 PoC용 시스템 굴림 12px (프로덕션은 Galmuri 계열 예정).
"""

import os
import shutil

import numpy as np
from common import ORIG_BIN as SRC
from common import OUT_DIR, SECTOR, USER_OFF, USER_SIZE, WORK_DIR, edc_compute, write_cue
from PIL import Image, ImageDraw, ImageFont

DST = os.path.join(WORK_DIR, "Eiyuu Densetsu (PoC Hangul).bin")
DST_CUE = os.path.join(WORK_DIR, "Eiyuu Densetsu (PoC Hangul).cue")

# あ 글리프의 (EXE LBA, EXE 내 파일 오프셋) — hunt_font_in_ram.py 결과
TARGETS = [
    ("ED.EXE", 257, 0xE35AC),
    ("ED2.EXE", 756, 0xBEF44),
]
GLYPH_BYTES = 24  # 12x12, 행당 2B(MSB), 하위 4비트 미사용


def render_hangul(ch):
    """시스템 굴림 12px로 ch의 12x12 1bpp 비트맵 생성."""
    font = ImageFont.truetype(r"C:\Windows\Fonts\gulim.ttc", 12)
    img = Image.new("1", (12, 12), 0)
    ImageDraw.Draw(img).text((0, 0), ch, fill=1, font=font)
    return np.array(img, dtype=np.uint8)


def pack_glyph(bits):
    """(12,12) 0/1 배열 → 행당 2B MSB 24바이트."""
    padded = np.zeros((12, 16), dtype=np.uint8)
    padded[:, :12] = bits
    return np.packbits(padded, axis=1).tobytes()


def ascii_art(raw):
    rows = []
    for r in range(12):
        v = (raw[r * 2] << 8) | raw[r * 2 + 1]
        rows.append("".join("#" if v & (0x8000 >> x) else "." for x in range(12)))
    return "\n".join(rows)


def main():
    # 기대되는 원본 あ 바이트: RAM 덤프(0x800F2DAC)에서 가져옴
    mram = open(os.path.join(OUT_DIR, "mram.bin"), "rb").read()
    a_expected = mram[0xF2DAC : 0xF2DAC + GLYPH_BYTES]
    print("원본 あ:")
    print(ascii_art(a_expected))

    ga = pack_glyph(render_hangul("가"))
    print("\n교체할 가:")
    print(ascii_art(ga))

    print("\n사본 생성 중...")
    shutil.copyfile(SRC, DST)
    with open(DST, "r+b") as f:
        for name, lba, off in TARGETS:
            sec_idx = lba + off // USER_SIZE
            in_user = off % USER_SIZE
            assert in_user + GLYPH_BYTES <= USER_SIZE, f"{name}: 섹터 경계 걸침"
            sec_base = sec_idx * SECTOR
            f.seek(sec_base)
            sec = bytearray(f.read(SECTOR))
            cur = bytes(sec[USER_OFF + in_user : USER_OFF + in_user + GLYPH_BYTES])
            assert cur == a_expected, f"{name}+0x{off:X}: 원본 불일치 ({cur.hex()})"
            sec[USER_OFF + in_user : USER_OFF + in_user + GLYPH_BYTES] = ga
            sec[2072:2076] = edc_compute(bytes(sec[16:2072])).to_bytes(4, "little")
            f.seek(sec_base)
            f.write(sec)
            print(f"{name} +0x{off:X} (섹터 {sec_idx}) 교체 + EDC 재계산")

    write_cue(DST_CUE, "Eiyuu Densetsu (PoC Hangul).bin")
    print(f"\n완료:\n  {DST}\n  {DST_CUE}")


if __name__ == "__main__":
    main()
