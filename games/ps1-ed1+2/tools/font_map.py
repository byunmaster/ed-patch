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

# ── 게임별 폰트 블록 (2026-08-14 실측) ──────────────────────────────────────────
# 디스크에 실행파일이 둘이고(`ED.EXE` LBA 257 · `ED2.EXE` LBA 756) **각자 폰트를 들고 있다.**
# 그래서 ED1 에만 한글을 구우면 ED2 는 글자가 안 나온다 — 시스템 UI 도 SCN 대사도.
#
# 자리는 추측하지 않고 **바이트로 찾았다** — ED.EXE 원본의 亜 글리프 220B 를 떠서 ED2.EXE
# 에서 검색하니 한 곳에 걸렸고, 거기서 **68,293B(글리프 3,104자)가 연속 일치**한다.
# 가나 블록도 같은 방법으로 잡았는데 **두 블록의 오프셋 차이가 정확히 같다**(0x24668) —
# 폰트 배치가 통째로 그만큼 옮겨져 있을 뿐 구조는 동일하다는 뜻이다.
#
# ⚠ **원본에서 읽어야 한다.** 우리 빌드는 그 슬롯을 한글로 덮어쓰므로 산출물에서 뜨면
# 한글 글리프를 찾는 꼴이 된다(루트 CLAUDE.md 「원본이 어땠는가는 originals 에서」).
# 두 EXE 다 `t_addr = 0x80010000` · 헤더 0x800B 라 RAM↔파일 변환식은 한 벌로 족하다.
FONT_BASE = {
    "ED1": {"exe": "ED.EXE", "lba": 257, "kanji": 0x800F48A8, "kana": 0x800F1BA0},
    "ED2": {"exe": "ED2.EXE", "lba": 756, "kanji": 0x800D0240, "kana": 0x800CD538},
}
GLYPH_FIT = 3104  # 연속 일치가 보장된 글리프 수 — 우리가 쓰는 2,350 슬롯이 든다
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


def kanji_glyph_ram(sjis, game="ED1"):
    """한자 1급 SJIS → 글리프 RAM 주소. `game` 으로 실행파일을 고른다."""
    assert is_kanji1(sjis), f"0x{sjis:04X}는 한자 1급 범위 밖"
    base = FONT_BASE[game]["kanji"]
    return base + (jis_index(sjis) - JIS_KANJI1_INDEX) * GLYPH_STRIDE


def ram_to_ed_file(ram):
    """RAM 주소 → ED.EXE 파일 내 오프셋."""
    return ram - ED_TEXT_ADDR + ED_FILE_BASE


def kanji_glyph_ed_offset(sjis, game="ED1"):
    """한자 1급 SJIS → 그 게임 실행파일 안의 오프셋 (재삽입기가 쓸 값)."""
    return ram_to_ed_file(kanji_glyph_ram(sjis, game))


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
