"""ED4 인게임 폰트 — 글리프 읽기·쓰기. 구조는 공용(`shared.ps1.glyph`), 여기엔 **ED4 레이아웃**과 한글 글리프 뽑기만 둔다.

`SLPS_015.40` 의 `0x800164F0` 이 코드를 읽어 `글리프 = 0x80070BD4 + 코드 × 18` 로 그린다(디스어셈블 확정).
🔴 **저장 규약(ED4)**: 열 짝 교환 **없음** · 글자 몸통 **1~11행**(ED3 은 교환 있음·0~10행 — ED3 규약으로 ED4 를 읽으면 글자가 그럭저럭 보이는 채로 틀린다).
🔴 **폰트의 끝도 코드에 적혀 있다** — 렌더러 전개표(`0x800793F4`)가 배열 바로 뒤라 `(표 − 베이스) // 18 = 1936` 이 칸 수다.
   그 뒤는 전개표·문자열·아이콘 픽셀 같은 **살아 있는 자료**다 — 거기에 한글을 구우면 대사창 전체가 색색 잡음이 된다.
"""

from shared import fonts
from shared.ps1 import glyph

LAYOUT = glyph.ED4
GLYPH_BYTES = glyph.GLYPH_BYTES
ROWS = CELL = glyph.ROWS
HANGUL_W = 11  # Galmuri11 의 폭
TOP = LAYOUT.top


def font_off():
    """폰트 배열의 **파일** 오프셋."""
    return LAYOUT.off()


def font_slots():
    """폰트 칸 수(= 마지막 글리프 색인 + 1)."""
    return LAYOUT.slots()


def read_glyph(exe, code):
    """(12,12) 0/1 — 화면에 나오는 그대로."""
    return glyph.read_glyph(exe, code, LAYOUT)


def write_glyph(buf, code, bits):
    """bytearray 안의 글리프 하나를 덮어쓴다(저장 규약으로 되돌려서). 폰트 밖 칸이면 실패."""
    glyph.write_glyph(buf, code, bits, LAYOUT)


def hangul_glyph(ch, dy=fonts.GALMURI11_DY):
    """한글 한 글자 → (12,12) 0/1. Galmuri11 BDF 에서 무손실로 뽑는다(TTF 렌더는 머신마다 달라 비결정적)."""
    return fonts.galmuri("Galmuri11").bits(ch, dy=dy, rows=ROWS, width=HANGUL_W)
