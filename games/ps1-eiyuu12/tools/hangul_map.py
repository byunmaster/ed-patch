"""
한글 인코딩 매핑: 완성형(KS X 1001) 2,350음절 ↔ PS1 한자 슬롯.

설계: 한자 1급 블록(JIS 인덱스 1410~, 슬롯 약 2,965개) 앞쪽 2,350칸에
완성형 음절을 가나다순(=KS X 1001 코드순)으로 배정.
  음절 i번째  →  JIS 인덱스 1410+i  →  SJIS 2바이트 (게임 텍스트에 쓸 코드)
게임의 SJIS→글리프 매핑(font_map.py)을 그대로 타므로 코드 수정 불필요.
"""

from font_map import JIS_KANJI1_INDEX, jis_index, kanji_glyph_ed_offset, kanji_glyph_ram


def ksx1001_syllables():
    """완성형 2,350음절, 코드순(=가나다순)."""
    out = []
    for lead in range(0xB0, 0xC9):
        for trail in range(0xA1, 0xFF):
            try:
                out.append(bytes([lead, trail]).decode("cp949"))
            except UnicodeDecodeError:
                pass
    assert len(out) == 2350, len(out)
    return out


SYLLABLES = ksx1001_syllables()
SYL_INDEX = {ch: i for i, ch in enumerate(SYLLABLES)}


def kuten_to_sjis(ku, ten):
    j1, j2 = ku + 0x20, ten + 0x20
    if j1 % 2:  # 홀수 구
        s1 = (j1 + 1) // 2 + 0x70
        s2 = j2 + 0x1F + (1 if j2 >= 0x60 else 0)
    else:
        s1 = j1 // 2 + 0x70
        s2 = j2 + 0x7E
    if s1 >= 0xA0:
        s1 += 0x40
    return (s1 << 8) | s2


def jis_index_to_sjis(idx):
    ku, ten = idx // 94 + 1, idx % 94 + 1
    return kuten_to_sjis(ku, ten)


def syllable_sjis(ch):
    """한글 음절 → 게임 텍스트에 쓸 SJIS 코드."""
    return jis_index_to_sjis(JIS_KANJI1_INDEX + SYL_INDEX[ch])


def encode_kr(text):
    """한국어 문자열 → 게임 텍스트 바이트열 (음절=슬롯 SJIS 2B, 공백=0x20, \\n=0x0A)."""
    out = bytearray()
    for ch in text:
        if ch == " ":
            out.append(0x20)
        elif ch == "\n":
            out.append(0x0A)
        elif ch in SYL_INDEX:
            out += syllable_sjis(ch).to_bytes(2, "big")
        else:
            raise ValueError(f"인코딩 불가 문자: {ch!r} (완성형 밖)")
    return bytes(out)


def slot_ed_offset(i):
    """i번째 음절 슬롯의 ED.EXE 파일 오프셋 (글리프 기록 위치)."""
    return kanji_glyph_ed_offset(jis_index_to_sjis(JIS_KANJI1_INDEX + i))


if __name__ == "__main__":
    # 라운드트립 검증: 전 슬롯의 SJIS가 font_map 역변환과 일치하는지
    ok = all(
        jis_index(jis_index_to_sjis(JIS_KANJI1_INDEX + i)) == JIS_KANJI1_INDEX + i
        for i in range(2350)
    )
    print(f"jis_index 라운드트립 2350슬롯: {'OK' if ok else 'FAIL'}")
    print(f"가={syllable_sjis('가'):#06x} (亜 슬롯=0x889f 기대)  힝={syllable_sjis('힝'):#06x}")
    print(
        f"슬롯0 파일오프셋=0x{slot_ed_offset(0):X}, RAM=0x{kanji_glyph_ram(jis_index_to_sjis(JIS_KANJI1_INDEX)):08X}"
    )
    print(f"encode_kr('안녕 왕자') = {encode_kr('안녕 왕자').hex()}")
