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

# 🔴 **저장 규약이 디스크마다 다르다** (2026-09-03 실측).
#   ED3: 열 짝 교환 O · 글자 몸통이 0~10행    ← 인게임 VRAM 과 0/660 픽셀로 검증됨
#   ED4: 열 짝 교환 X · 글자 몸통이 1~11행    ← ED3 글리프와 **바이트 완전일치**로 유도
#   ⇒ 두 조합 중 ED4 의 것만이 ED3 의 활자와 1,595자 완전일치를 낸다. 다른 조합(생·전치·
#     교환)에서는 공통 글리프가 16자뿐이었다 — 우연으로 나올 수가 없는 차이다.
#   ✅ **ED4 쪽도 인게임으로 확인했다**(2026-09-03) — 타이틀 메뉴 두 줄을 한글로 굽고 부팅해
#     「처음부터 시작 / 계속해서 시작」이 획 튐 없이 나오는 것을 봤다
#     (`build_poc.py --disc ed4`). 「썼다」와 「화면에 나온다」는 다른 말이다(체크리스트 10-B).
LAYOUT = {
    "ed3": {"swap": True, "top": 0},
    "ed4": {"swap": False, "top": 1},
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
    """(12,12) 0/1 — **화면에 나오는 그대로**(저장 규약을 되돌린 뒤 윗줄을 맞춘다).

    두 디스크의 결과를 **같은 틀**로 돌려 주므로 글리프끼리 바로 대조할 수 있다
    (`solve_charmap_glyph.py` 의 로제타가 이걸 쓴다).
    """
    lay = LAYOUT[disc]
    off = font_off(disc)
    raw = fonts.unpack18(exe[off : off + (code + 1) * GLYPH_BYTES], code, ROWS, CELL)
    g = _swap_pairs(raw) if lay["swap"] else np.array(raw, dtype=np.uint8, copy=True)
    if lay["top"]:
        g = np.roll(g, -lay["top"], axis=0)
        g[-lay["top"] :] = 0
    return g


def write_glyph(buf, code, bits, disc="ed3"):
    """bytearray 안의 글리프 하나를 덮어쓴다(그 디스크의 저장 규약으로 되돌려서)."""
    lay = LAYOUT[disc]
    o = font_off(disc) + code * GLYPH_BYTES
    grid = np.zeros((ROWS, CELL), dtype=np.uint8)
    src = np.asarray(bits, dtype=np.uint8)
    h = min(src.shape[0], ROWS - lay["top"])
    grid[lay["top"] : lay["top"] + h, : src.shape[1]] = src[:h, :CELL]
    buf[o : o + GLYPH_BYTES] = fonts.pack18(_swap_pairs(grid) if lay["swap"] else grid, ROWS, CELL)


def glyph_count(exe, disc="ed3"):
    """🔴 **쓰지 말 것** — 빈칸 연속으로 끝을 추정하면 폰트를 한참 지나친다.

    실측 2026-09-03: 이 함수가 ED3 5,413 · ED4 5,699 를 뱉었는데 **진짜 폰트는 ~1,900**
    이다. 그 뒤는 낱말 표와 문자열 풀이다 — 그 자리에 한글을 구우면 **이름·아이템 표를
    통째로 덮어쓴다.** 「빈 글리프가 64개 이어지면 끝」이라는 가정이 틀렸다(폰트 뒤의
    자료에도 0 이 드물다).

    ⇒ 자리를 셀 때는 `font_end` 를 쓴다. 이 함수는 옛 호출부를 위해 남겨 두고 상한만 준다.
    """
    return font_end(exe, disc)


def _glyphy(exe, code, disc):
    """이 자리가 글리프다운가 — 잉크가 상식적이고 **마지막 행이 비어 있다**.

    원본 글리프는 12행 중 0~10 행만 쓴다(실측). 폰트 밖 자료는 이 둘을 거의 못 맞춘다.
    """
    g = read_glyph(exe, code, disc)
    ink = int(g.sum())
    return 8 <= ink <= 100 and not g[ROWS - 1].any()


def font_end(exe, disc="ed3", gap=24, limit=3000):
    """폰트 배열이 끝나는 자리(마지막 글리프 색인 + 1).

    **글리프다운 자리가 `gap` 개 연속으로 끊기면** 거기서 끝난 것으로 본다.
    ⚠ 이것도 추정이다 — 그래서 `hangul_map` 은 여기에 더해 **원본이 쓰는 코드**를 빼고,
      게이트가 「배정한 자리를 원본도 쓰나」를 매번 다시 본다.
    """
    last, run = -1, 0
    for c in range(limit):
        if font_off(disc) + (c + 1) * GLYPH_BYTES > len(exe):
            break
        if _glyphy(exe, c, disc):
            last, run = c, 0
        else:
            run += 1
            if run >= gap:
                break
    return last + 1


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
