"""
SJIS → 폰트 글리프 위치 매핑. ED.EXE의 변환 루틴(0x800AE6C8~) 역분석 결과.

루틴 요약:
  - SJIS 2바이트를 합쳐 범위 판정으로 블록 베이스 선택
      0x8140~0x84BE (기호·영숫자·가나)  → RAM 0x800F1BA0  (로컬 인덱스는 별도 계산)
      0x889F~0x9872 (한자 1급, 亜~)     → RAM 0x800F48A8  (JIS 순차)
  - 글리프 주소 = 베이스 + 로컬인덱스 × 22   (글리프 = 11행 × 2바이트)

한자 블록은 표준 JIS X 0208 순차라 공식으로 계산 가능(한글 패치의 핵심 —
한자 슬롯을 한글로 덮어쓰고 해당 한자 SJIS 코드로 인코딩).
가나/기호 블록의 로컬 인덱스는 0x800AE768의 커스텀 계산이라 여기선 미구현.
"""

ED_TEXT_ADDR = 0x80010000
ED_FILE_BASE = 0x800  # ED.EXE text가 시작하는 파일 오프셋

KANJI_BASE_RAM = 0x800F48A8  # 亜 (JIS 16-1)
KANA_BASE_RAM = 0x800F1BA0  # 기호·가나 블록
GLYPH_STRIDE = 22  # 11행 × 2바이트
GLYPH_ROWS = 11
JIS_KANJI1_INDEX = (16 - 1) * 94  # 亜의 JIS 순차 인덱스 = 1410


def sjis_to_kuten(sjis):
    """SJIS 2바이트 → (구, 점). 표준 변환."""
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
    ku, ten = sjis_to_kuten(sjis)
    return (ku - 1) * 94 + (ten - 1)


def is_kanji1(sjis):
    return 0x889F <= sjis <= 0x9872


def is_kana_block(sjis):
    return 0x8140 <= sjis <= 0x84BE


def kanji_glyph_ram(sjis):
    """한자 1급 SJIS → 글리프 RAM 주소."""
    assert is_kanji1(sjis), f"0x{sjis:04X}는 한자 1급 범위 밖"
    return KANJI_BASE_RAM + (jis_index(sjis) - JIS_KANJI1_INDEX) * GLYPH_STRIDE


def ram_to_ed_file(ram):
    """RAM 주소 → ED.EXE 파일 내 오프셋."""
    return ram - ED_TEXT_ADDR + ED_FILE_BASE


def kanji_glyph_ed_offset(sjis):
    """한자 1급 SJIS → ED.EXE 파일 오프셋 (재삽입기가 쓸 값)."""
    return ram_to_ed_file(kanji_glyph_ram(sjis))


if __name__ == "__main__":
    # 프레임버퍼 매칭으로 확인된 주소와 대조 (王 0x800F593C, 子 0x800FA5B8, 오차 ±2)
    for ch, sjis, expect in [("王", 0x89A4, 0x800F593C), ("子", 0x8E71, 0x800FA5B8)]:
        got = kanji_glyph_ram(sjis)
        ku, ten = sjis_to_kuten(sjis)
        print(
            f"{ch} SJIS 0x{sjis:04X} 구점 {ku}-{ten} → RAM 0x{got:08X} "
            f"(파일 0x{kanji_glyph_ed_offset(sjis):X})  기대 0x{expect:08X}  "
            f"{'OK' if abs(got - expect) <= 2 else '!!'}"
        )
