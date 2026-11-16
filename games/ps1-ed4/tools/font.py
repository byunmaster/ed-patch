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
    if ch == "…":  # Galmuri 의 `…` 는 점이 가운데 행이다(일본식) — 한국식 바닥 행으로 다시 만든다(공통 번역 규칙 「…」, 마스터 10-08·10-25)
        return ellipsis_glyph(dy)
    return fonts.galmuri("Galmuri11").bits(ch, dy=dy, rows=ROWS, width=HANGUL_W)


ELLIPSIS_DOT_STEP = 4  # 점 사이 간격(px)

# 🔴 **한 글자를 두 칸에 반씩 나눈 전용 글리프**(마스터 판정 2026-09-27 · ps1-ed3 의 필드 메뉴 「시 스 템」, ED4 10-25 「시스템을 ED3 처럼 둘로 나눠 그려서」).
#    메뉴는 코드당 12px 고정이고 공백도 12px 라 「시 스 템」(5코드·60px)이 4칸 창을 넘는다 — 가운데 글자를 반 칸(6px) 밀어 두 칸에 걸쳐 굽는다:
#    [시][스◐][◑스][템] = 4코드·48px. ⚠ 도트는 새로 안 그린다 — 그 글자의 Galmuri11 글리프를 그대로 잘라 옮긴다.
#    사용 영역 문자라 문안·배정·굽기가 한글과 같은 길을 탄다(`hangul.bake` 가 먼저 본다).
SPLIT = {"\ue010": ("스", "L"), "\ue011": ("스", "R")}
SPLIT_SHIFT = CELL // 2  # 반 칸


def split_glyph(ch):
    """나눈 글리프의 한쪽 → (12,12) 0/1. 원 글자를 24px 띠의 6px 자리에 놓고 왼쪽(L)·오른쪽(R) 12px 를 잘라 낸다."""
    import numpy as np

    base, side = SPLIT[ch]
    g = np.asarray(hangul_glyph(base), dtype=np.uint8)
    strip = np.zeros((ROWS, 2 * CELL), dtype=np.uint8)
    strip[:, SPLIT_SHIFT : SPLIT_SHIFT + g.shape[1]] = g
    return strip[:, :CELL] if side == "L" else strip[:, CELL:]


def ellipsis_glyph(dy=fonts.GALMURI11_DY):
    """「…」 — Galmuri11 `.`(마침표, 바닥 행)를 4px 간격으로 셋 찍은 전각 칸 글리프."""
    import numpy as np

    g = np.asarray(fonts.galmuri("Galmuri11").bits(".", dy=dy, rows=ROWS, width=HANGUL_W), dtype=np.uint8)
    out = np.zeros_like(g)
    for k in range(3):
        sh = k * ELLIPSIS_DOT_STEP
        out[:, sh:] |= g[:, : g.shape[1] - sh]
    return out


HALF_W = 6  # 반각 칸 폭(px) — 훅(`halfwidth.py`)이 잉크가 왼쪽 6px 안에 든다고 가정한다


def half_glyph(ch):
    """반각 한 글자 → (12,12) 0/1. Galmuri11 **Condensed**(잉크 ≤5px)로 뽑아 왼쪽 6px 에 둔다 — 보통 Galmuri11 의 숫자는 7px 라 6px 칸에 안 든다."""
    import numpy as np

    bits = fonts.galmuri("Galmuri11-Condensed").bits(
        ch, dy=fonts.GALMURI11_DY, rows=ROWS, width=HALF_W
    )
    out = np.zeros((ROWS, CELL), dtype=bits.dtype)
    out[:, :HALF_W] = bits
    return out
