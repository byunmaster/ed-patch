"""ED3 인게임 폰트 — 읽기·쓰기의 유일한 통로.

**자리를 어떻게 찾았나**(2026-09-03): `ED3.EXE` 를 디스어셈블해 대본 코드를 읽는 자리를
찾았다. `0x80018AB4` 부터가 그 계산이다 —

    lhu   a0, (v1)          ; a0 = 다음 16비트 코드
    sll   a1, a2, 3         ; ×8
    addu  a1, a1, a0        ; ×9
    sll   a0, a1, 1         ; ×18          ← 글리프 18바이트
    lui   a1, 0x800a
    addiu a1, a1, -0x1e90   ; 0x8009E170   ← 폰트 베이스
    addu  a0, a1, a0        ; 글리프 = 베이스 + 코드×18
    addiu v1, v1, 2         ; 다음 코드로

⇒ **색인이 곧 문자 코드다.** 한자 슬롯을 한글로 덮고 그 코드로 인코딩하면 화면에 나온다.

기하는 새턴 ED3 `KANJI12.FON` 과 같다 — **12행 × 12비트 밀착 패킹(18B)**. 그래서
`shared.fonts.pack18/unpack18` 이 그대로 붙는다(둘째 소비자가 실재한다).

⚠ **검증은 실물로 했다** — 인게임 VRAM 에서 뽑은 ク·リ·ス 와 대조했고, 새턴 12×12 폰트와
  **잉크량 상관 0.969**(표본 35자)다. 「코드가 그렇게 계산한다」만으로는 레이아웃이 안 정해진다.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import common

from shared import fonts

EXE_TADDR = 0x80010000  # PS-EXE t_addr (양쪽 같다)
EXE_HDR = 0x800  # 파일 앞 헤더
GLYPH_BYTES = 18
ROWS = CELL = 12  # 저장 격자 — 18B = 12행 × 12비트 밀착 패킹
# 12열이 전부 그려진다 — 다만 **이웃한 두 열이 짝으로 뒤바뀌어 저장된다**(`_swap_pairs`).
DRAW_W = 12
HANGUL_W = 11  # Galmuri11 의 폭 — 12칸 안에 왼쪽 정렬하면 오른쪽 1px 가 자간이 된다
PITCH = 12  # 화면에서 한 글자가 차지하는 가로 칸 (원본 일본어 줄에서 실측)

# 디스크마다 실행파일과 폰트 베이스가 다르다 — **둘 다 디스어셈블로 읽었다.**
#   ED3: 0x80018AB4  `코드×18 + 0x8009E170`
#   ED4: 0x800164F0  `코드×18 + 0x80070BD4`   (ぁあぃいぅう 렌더로 확인)
FONTS = {
    "ed3": {"exe": "/ED3.EXE", "ram": 0x8009E170, "site": 0x80018AB4},
    "ed4": {"exe": "/SLPS_015.40", "ram": 0x80070BD4, "site": 0x800164F0},
}
EXE_PATH = FONTS["ed3"]["exe"]  # 하위 호환
FONT_RAM = FONTS["ed3"]["ram"]
FONT_OFF = FONT_RAM - EXE_TADDR + EXE_HDR  # 0x08E970


def font_off(disc="ed3"):
    return FONTS[disc]["ram"] - EXE_TADDR + EXE_HDR


def exe_bytes(disc="ed3"):
    lba, size = common.iso_files(disc)[FONTS[disc]["exe"]]
    return common.read_lba(disc, lba, size), lba, size


def _swap_pairs(bits):
    """🔴 **이웃한 두 열이 짝을 지어 뒤바뀌어 저장된다** (0↔1, 2↔3, …, 10↔11).

    탐침으로 실측했다(2026-09-03). 빈 글리프에 비트 하나씩만 켜고 화면을 봤다:

        비트 0        → 1열        비트 11 → 10열
        비트 12       → **1행** 1열 (⇒ 행 간격 12비트)
        비트 0~10     → 0~9열 + 11열 (10열은 꺼짐)
        비트 0~11     → 0~11열 깨끗이

    4bpp 로 펼칠 때 니블 순서가 뒤집히는 흔한 자국이다. 이 변환을 넣으니 원본 다섯 글자가
    VRAM 실물과 **차이 0/660 픽셀**로 맞았다(넣기 전엔 76).

    ⚠ 이걸 모르면 **한글 획이 한 칸씩 옆으로 튄다.** 한자는 획이 두꺼워 티가 안 나서
      오래 못 봤다 — 「원본과 11% 다른데 글자는 읽힌다」가 그 증상이었다.
    자기 역함수라 읽기·쓰기가 같은 함수를 쓴다.
    """
    b = np.array(bits, dtype=np.uint8, copy=True)
    for c in range(0, CELL, 2):
        b[:, [c, c + 1]] = b[:, [c + 1, c]]
    return b


def read_glyph(exe, code, disc="ed3"):
    """(12,12) 0/1 — 원본 글리프(꼬리 두 열을 되돌려 **화면에 나오는 그대로**)."""
    off = font_off(disc)
    raw = fonts.unpack18(exe[off : off + (code + 1) * GLYPH_BYTES], code, ROWS, CELL)
    return _swap_pairs(raw)


def write_glyph(buf, code, bits, disc="ed3"):
    """bytearray 안의 글리프 하나를 덮어쓴다(꼬리 두 열을 게임 규약으로 바꿔서)."""
    o = font_off(disc) + code * GLYPH_BYTES
    grid = np.zeros((ROWS, CELL), dtype=np.uint8)
    src = np.asarray(bits, dtype=np.uint8)
    grid[: src.shape[0], : src.shape[1]] = src[:ROWS, :CELL]
    buf[o : o + GLYPH_BYTES] = fonts.pack18(_swap_pairs(grid), ROWS, CELL)


def glyph_count(exe, disc="ed3"):
    """폰트가 몇 글리프까지 이어지나 — **연속으로 비지 않은** 마지막 자리까지.

    ⚠ 이건 상한 추정이지 계약이 아니다. 뒤쪽은 다른 자료가 이어질 수 있으니
      **덮어쓰기 전에 그 코드가 대본에 안 쓰이는지**를 따로 확인한다.
    """
    off = font_off(disc)
    n = 0
    blanks = 0
    while off + (n + 1) * GLYPH_BYTES <= len(exe):
        g = exe[off + n * GLYPH_BYTES : off + (n + 1) * GLYPH_BYTES]
        blanks = blanks + 1 if not any(g) else 0
        if blanks > 64:
            return n - 64
        n += 1
    return n


def render(bits, width=DRAW_W):
    """화면에 나오는 그대로(12칸)."""
    return "\n".join("".join("█" if v else "·" for v in row[:width]) for row in bits)


def hangul_glyph(ch, dy=fonts.GALMURI11_DY):
    """한글 한 글자 → (12,12) 0/1. Galmuri11 BDF 에서 무손실로 뽑는다.

    ⚠ TTF 렌더를 안 쓰는 이유는 `shared/fonts/__init__.py` 머리말에 있다(머신마다 배치가
      달라져 빌드가 비결정적이 된다).

    🔴 **dy 는 `fonts.GALMURI11_DY`(=-3) 다.** 한 칸 내렸다가(-2) 한글만 **베이스라인이
       1픽셀 아래로 밀렸다** — 원본 글리프는 0~10행을 쓴다(실측). 같은 줄에 일본어가 섞이면
       바로 보인다.
    """
    f = fonts.galmuri("Galmuri11")
    return f.bits(ch, dy=dy, rows=ROWS, width=HANGUL_W)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3", choices=tuple(FONTS))
    ap.add_argument("--chars", default="一口日王クリス")
    ap.add_argument("--codes", type=lambda s: [int(x, 0) for x in s.split(",")])
    a = ap.parse_args()
    exe, _, _ = exe_bytes(a.disc)
    print(
        f"{a.disc} 폰트 @파일 0x{font_off(a.disc):06X} (RAM 0x{FONTS[a.disc]['ram']:08X}) · "
        f"글리프 {GLYPH_BYTES}B · 추정 {glyph_count(exe, a.disc):,}자"
    )
    import textenc

    m = textenc.charmap(a.disc)
    rev = {v: k for k, v in m.items()}
    codes = a.codes or [rev[c] for c in a.chars if c in rev]
    for code in codes:
        print(f"0x{code:03X} {m.get(code, '?')}")
        print(render(read_glyph(exe, code, a.disc)))
