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
# 🔴 **폰트의 끝도 코드에 적혀 있다** (2026-09-07 실측). 렌더러는 글리프 18B 를 「바이트→4bpp
#   네 바이트」 전개표로 펼치는데, 그 표가 **폰트 배열 바로 뒤**에 붙어 있다 —
#   ED3 `0x800A620C`(`0x80018B4C`) · ED4 `0x800793F4`(`0x80016618`). 베이스에서 18 로 나누면
#   1829(+2B 여백) · 1936 — 그 자리가 곧 「마지막 글리프 + 1」이다.
#   ⚠ 그 뒤는 전개표·멤버 이름 문자열(`FT0000`·`MT7002`…)·아이콘 픽셀 같은 **살아 있는
#   자료**다. 예전 `font_end` 는 「글리프다운 밀도가 끊기면 끝」으로 1900·1990 을 냈고, 그
#   차이만큼(ED3 71자 · ED4 51자) 한글을 **전개표 위에 구워** 대사창 전체가 색색 잡음이 됐다.
FONTS = {
    "ed3": {"exe": "/ED3.EXE", "ram": 0x8009E170, "site": 0x80018AB4, "table": 0x800A620C},
    "ed4": {"exe": "/SLPS_015.40", "ram": 0x80070BD4, "site": 0x800164F0, "table": 0x800793F4},
}


def font_slots(disc="ed3"):
    """폰트 배열의 칸 수 = (전개표 − 베이스) // 18. 원본 없이 계산된다.

    ⚠ ED3 은 마지막 글리프(1828) 뒤에 **2바이트 여백**을 두고 표가 온다(1829×18 = 0x800A620A,
      표 0x800A620C) — 그래서 내림이다. ED4 는 딱 떨어진다(1936).
    """
    ram, table = FONTS[disc]["ram"], FONTS[disc]["table"]
    return (table - ram) // GLYPH_BYTES


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


def font_end(exe, disc="ed3"):
    """폰트 배열이 끝나는 자리(마지막 글리프 색인 + 1) = `font_slots`.

    ⚠ 예전엔 「글리프다운 자리가 24개 연속으로 끊기면 끝」으로 **추정**했다. 폰트 뒤의
      전개표·문자열이 우연히 글리프답게 보여 ED3 1900 · ED4 1990 을 냈고, 그 자리에 한글을
      구워 렌더러의 전개표를 덮었다(2026-09-07). 지금은 코드에 적힌 값만 쓴다 — `exe` 는
      옛 호출부 호환으로 남겨 둔다.
    """
    return font_slots(disc)


def glyphy(exe, code, disc="ed3"):
    """이 자리가 글리프다운가 — 잉크가 상식적이고 **마지막 행이 비어 있다**.

    원본 글리프는 12행 중 0~10 행만 쓴다(실측). 폰트 끝 직전의 아이콘 픽셀(ED4 1924~1935 에
    4bpp 자료가 섞여 있다)은 이 둘을 못 맞춘다 — 빈 자리를 고를 때 이걸로 거른다.
    """
    g = read_glyph(exe, code, disc)
    ink = int(g.sum())
    return 8 <= ink <= 100 and not g[ROWS - 1].any()


_glyphy = glyphy  # 옛 이름


def render(bits, width=DRAW_W):
    """화면에 나오는 그대로(12칸)."""
    return "\n".join("".join("█" if v else "·" for v in row[:width]) for row in bits)


def _galmuri_bits(ch, dy=fonts.GALMURI11_DY):
    return fonts.galmuri("Galmuri11").bits(ch, dy=dy, rows=ROWS, width=HANGUL_W)


def _period_bits():
    """대사 마침표 「.」 — 원판 `？`·`！` 의 점과 같은 꼴: 가로 2 × 세로 1px, 9행(마스터 11-16 「원판의 ? ! 에 맞춰서 마침표를」, 규칙 1-3). 「…」 점이 같은 모양을 쓴다."""
    return np.array([[1 if c == "#" else 0 for c in row.ljust(CELL, ".")] for row in _period_rows()], dtype=np.uint8)


def _period_rows():
    return ("",) * 9 + ("..##", "", "")


# 🔴 **반각 부호 모양**(마스터 11-14 「전각부호를 반각으로 만들때 원본의 부호모양을 최대한 살렸으면」, 규칙 1-9). 전진 6px 안에 그린다(엔진 반 칸).
#    `? ( ) -` 는 원판 전각 글리프(？ （ ） －)의 잉크를 그대로 — 좌우 빈 열만 덜고 6px 칸 가운데(`-` 는 원판 7열이라 6열 · `)` 는 `(` 의 좌우 대칭).
#    `.` 는 한국식 바닥 점 — 원판 `！` 의 점(2×1px, 9행)과 같은 크기·높이. `,` 는 그 점에 왼쪽 아래로 꼬리(10·11행).
#    `&` `%` 는 여기 없다 — 원판 전각 글리프(＆ 0x1b · ％ 0x1a)를 그대로 쓴다(`hangul_map.ORIG_FULL`). `!` 는 Galmuri 그대로(원판과 거의 같다).
#    `?` 는 원판 6열 폭이라 오른쪽 여백이 없다 — 뒤에는 늘 공백(6px)이 온다.
HALF_PUNCT = {
    ".": ("",) * 9 + ("..##",),  # 원판 `？`·`！` 점(2×1px, 9행)과 같다 — 실측 11-16(원판 롬 글리프)
    ",": ("",) * 9 + ("..##", "..#", ".#"),  # 마침표와 같은 점 머리 + 왼쪽 아래 꼬리
    "!": ("", ".#", ".#", ".#", ".#", ".#", ".#", ".#", "", ".##"),  # 원판 `！` 잉크 그대로(줄기 1~7행 · 점 9행 — 같은 줄 `?` 와 점 높이가 같다. Galmuri 는 점이 10행이라 1px 계단, 마스터 11-16 기준선 검사)
    "?": ("", ".####.", "#....#", "#....#", "....#.", "...#..", "..#...", "..#...", "", "..##"),
    "(": ("...#", "..#", "..#", ".#", ".#", ".#", ".#", ".#", "..#", "..#", "...#"),
    ")": ("..#", "...#", "...#", "....#", "....#", "....#", "....#", "....#", "...#", "...#", "..#"),  # `(` 와 좌우 대칭(원판 ） 코드 12 와 같은 비트맵이 되면 글리프 중복 게이트가 운다)
    "-": ("",) * 5 + ("######",),
}


def hangul_glyph(ch, dy=fonts.GALMURI11_DY):
    """한글 한 글자 → (12,12) 0/1. Galmuri11 BDF 에서 무손실로 뽑는다.

    ⚠ TTF 렌더를 안 쓰는 이유는 `shared/fonts/__init__.py` 머리말에 있다(머신마다 배치가
      달라져 빌드가 비결정적이 된다).

    🔴 **dy 는 `fonts.GALMURI11_DY`(=-3) 다.** 한 칸 내렸다가(-2) 한글만 **베이스라인이
       1픽셀 아래로 밀렸다** — 원본 글리프는 0~10행을 쓴다(실측). 같은 줄에 일본어가 섞이면
       바로 보인다.
    """
    if ch == "…":  # Galmuri 의 `…` 는 점이 가운데 행이다 — 바닥 행으로 다시 만든다
        return ellipsis_glyph()
    if ch in HALF_PUNCT:
        rows = list(HALF_PUNCT[ch]) + [""] * (ROWS - len(HALF_PUNCT[ch]))
        return np.array([[1 if c == "#" else 0 for c in row.ljust(CELL, ".")] for row in rows], dtype=np.uint8)
    return _galmuri_bits(ch, dy)


# 🔴 **한 글자를 두 칸에 반씩 나눈 전용 글리프**(마스터 판정 2026-09-27, 커맨드 창 「시 스 템」).
#    메뉴는 코드당 12px 고정이고 공백도 12px 라 「시 스 템」(5코드·60px)이 4칸 창을 넘는다.
#    그래서 가운데 글자를 반 칸(6px) 밀어 두 칸에 걸쳐 굽는다 — [시][스◐][◑스][템] = 4코드·48px.
#    ⚠ 도트는 **새로 안 그린다** — 그 글자의 Galmuri11 글리프를 그대로 잘라 옮긴다.
#    사용 영역 문자(U+E000~)라 문안·배정·굽기가 한글과 같은 길(글리프 자리 게이트)을 탄다.
SPLIT = {"": ("스", "L"), "": ("스", "R")}
SPLIT_SHIFT = PITCH // 2  # 반 칸


# 🔴 **말줄임은 「…」 전각 한 글자, 점 셋은 한국식 바닥(마침표와 같은 행)**(마스터 10-08, 공통 번역 규칙). 원판 코드표엔 `…` 가 없고 일본식 `・`(코드 3,
#    4~5행 가운데 점)만 있다 — 그 **코드 3 자리를 바닥 점 셋 글리프로 다시 굽고** `…` 를 거기 매단다(`hangul_map.PUNCT_ED3`): 새 슬롯이 필요 없다.
#    안 옮긴 일본어 줄의 `・・・` 도 가운데 점이 아니라 이 모양으로 나온다(가운데 점은 어느 게임에서도 안 나온다).
ELLIPSIS_CODE = {"ed3": 3}  # 원본 `・` 글리프 코드(ED4 는 아직 확인 전 — 안 건드린다)
ELLIPSIS_DOT_STEP = 4  # 점 사이 간격(px) — 점은 2열 폭이고 마침표(2~3열)에서 한 열 당겨 1~2·5~6·9~10열


def ellipsis_glyph():
    """「…」 — 대사 마침표 「.」(2×2 네모점, 바닥 행)와 같은 점을 4px 간격으로 셋 찍은 전각 칸 글리프."""
    g = np.asarray(_period_bits(), dtype=np.uint8)
    g = np.roll(g, -1, axis=1)  # 마침표는 2~3열(반 칸 가운데) — 전각 칸에선 1~2열부터 찍는다
    out = np.zeros_like(g)
    for k in range(3):
        sh = k * ELLIPSIS_DOT_STEP
        out[:, sh:] |= g[:, : g.shape[1] - sh]
    return out


# 🔴 **대사 속 숫자 0~9 · 「Goa·Pia」 글자(G o a P i)는 원판 소지금 창 글꼴 모양이다**(마스터 10-25 「ed3 은 b 가 가장 보기 깔끔」 — 대사 Galmuri 글리프는
#    7~8px 라 6px 전진에 서로 겹쳐 「Goa」가 붙어 보였다). 원판 소지금 창·상태 패널·능력치 열이 쓰는 글꼴이고, 12×12 글꼴 표에는 없는 별도 반각 글꼴이다
#    (저장 위치는 못 찾았다 — 값을 RAM 에 써서 숫자 0~9 를 전부 띄우고 원 해상도 화면 픽셀에서 뽑았다, 같은 글자를 여러 자리에서 뽑아 비트 일치 확인).
#    폭 5px + 여백 1px(= 6px 전진), 높이 10행이 한글 바닥선에 맞는다(칸의 1~10행). `#` = 켠 점. 나머지 영문(A I z C …)은 Galmuri 그대로.
#    ⚠ 마스터가 10-21 에 도트판에서 찍은 「i」(줄기만 있는 모양)를 이 안이 **대체**한다(마스터 10-25 판정 — 원판 소지금 창 모양 그대로).
HUD_DOTS = {
    "0": (
        ".###.",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        ".###.",
    ),
    "1": (
        "..#..",
        ".##..",
        "#.#..",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "#####",
    ),
    "2": (
        ".###.",
        "#...#",
        "#...#",
        "....#",
        "...#.",
        "..#..",
        ".#...",
        "#....",
        "#....",
        "#####",
    ),
    "3": (
        ".###.",
        "#...#",
        "#...#",
        "....#",
        "..##.",
        "....#",
        "#...#",
        "#...#",
        "#...#",
        ".###.",
    ),
    "4": (
        "..##.",
        "..##.",
        ".#.#.",
        ".#.#.",
        "#..#.",
        "#..#.",
        "#..#.",
        "#####",
        "...#.",
        "...#.",
    ),
    "5": (
        "#####",
        "#....",
        "#....",
        "#....",
        "####.",
        "....#",
        "....#",
        "#...#",
        "#...#",
        ".###.",
    ),
    "6": (
        ".###.",
        "#...#",
        "#....",
        "#....",
        "####.",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        ".###.",
    ),
    "7": (
        "#####",
        "#...#",
        "#...#",
        "....#",
        "....#",
        "...#.",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
    ),
    "8": (
        ".###.",
        "#...#",
        "#...#",
        "#...#",
        ".###.",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        ".###.",
    ),
    "9": (
        ".###.",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        ".####",
        "....#",
        "....#",
        "#...#",
        ".###.",
    ),
    "G": (
        ".....",
        ".###.",
        "#...#",
        "#...#",
        "#....",
        "#.###",
        "#...#",
        "#...#",
        "#...#",
        ".###.",
    ),
    "o": (
        ".....",
        ".....",
        ".....",
        ".....",
        ".###.",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        ".###.",
    ),
    "a": (
        ".....",
        ".....",
        ".....",
        ".....",
        "###..",
        "...#.",
        ".###.",
        "#..#.",
        "#..#.",
        ".####",
    ),
    "P": (
        ".....",
        "####.",
        "#...#",
        "#...#",
        "#...#",
        "####.",
        "#....",
        "#....",
        "#....",
        "#....",
    ),
    "i": (
        ".....",
        ".....",
        ".....",
        "..#..",
        ".....",
        ".##..",
        "..#..",
        "..#..",
        "..#..",
        ".###.",
    ),
}
# 🔴 **대사 속 「」 『』 는 반 칸(6px) 글리프다**(마스터 도안 B판 10-26 — PS1 IV·새턴 III·PS1 III 공통, 12×12 칸에서 여는 쪽 = 0~5열 · 닫는 쪽 = 6~11열).
#    반 칸 글자는 칸의 **왼쪽 6열**만 그리므로 닫는 쪽은 6~11열을 0~5열로 옮겨 굽는다. 가로줄이 4px 그대로라 잘려 짧아 보이지 않는다.
#    대사 조각에서만 `build.encode_member` 가 이 부호를 사설 글자로 바꿔 인코딩한다(UI·이름 속 부호는 원판 전각 그대로).
KAGI = {"\ue011": "「", "\ue012": "」", "\ue013": "『", "\ue014": "』"}
# 목록 창(소지품·상점)은 공백 코드도 전각 12px 로 그려 반각 틈을 못 낸다(대사창 훅만 반각) — 「검사교본 1」 의 틈(마스터 11-08·11-09 「띄어쓰기는 반각」)은
# **왼쪽 반 칸이 빈 숫자 글리프**(한 칸 12px 안에 6px 빈칸 + 숫자)로 만든다. 대사창은 원래 「반각 공백 6 + 숫자 6」 이라 화면이 같다.
LEAD_DIGITS = {"\ue021": "1", "\ue022": "2", "\ue023": "3"}
# 「사피 제N권」 — 「⎵제」(반 칸 빈 + 제 왼쪽 반) · 「제 오른쪽 반 + 숫자」 두 칸으로 「⎵제N」 을 반 칸 밀어 한 칸 폭 틈을 반각으로 만든다(권 은 그대로)
JE_LEAD = "\ue031"
JE_DIGIT = {chr(0xE040 + n): str(n) for n in range(1, 10)}
SERIES_GLYPHS = {**LEAD_DIGITS, JE_LEAD: None, **JE_DIGIT}  # 늘 굽는 사설 글자(문안엔 안 나오고 build 가 코드로 꽂는다)
KAGI_DOTS = {
    "「」": (
        "####........",
        "#...........",
        "#...........",
        "#...........",
        "#........#..",
        "#........#..",
        "#........#..",
        ".........#..",
        ".........#..",
        ".........#..",
        "......####..",
        "............",
    ),
    "『』": (  # v2 — 가로 5칸(마스터 10-27, 새턴 III 은 별도 B2s)
        "#####.......",
        "#...#.......",
        "#.###.......",
        "#.#.........",
        "#.#.....###.",
        "#.#.....#.#.",
        "###.....#.#.",
        "........#.#.",
        "......###.#.",
        "......#...#.",
        "......#####.",
        "............",
    ),
}
HUD_ROW0 = 1  # 칸 안 첫 행(한글 잉크 0~10행 중 바닥선 10행에 숫자 10행의 끝이 닿도록)

# 🔴 **원판 전각 라틴 코드표에 없는 대문자 Ｌ**(마스터 10-27 — 「ＬＡ」, 약어는 원판 전각 꼴). 원판 Ｅ(코드 0x2B)에서 줄기(2열·1~8행)와 바닥 막대(9행 2~7열)만 남겼다 —
#    같은 줄기 위치·같은 1px 굵기·같은 바닥선이라 새 도안이 아니라 원판 글리프의 부분집합이다. 12×12 전각 칸 그대로(반 칸 훅 목록 밖).
FULL_DOTS = {
    "Ｌ": (
        "............",
        "..#.........",
        "..#.........",
        "..#.........",
        "..#.........",
        "..#.........",
        "..#.........",
        "..#.........",
        "..#.........",
        "..######....",
        "............",
        "............",
    ),
}


def glyph_bits(ch):
    """굽을 글리프 한 칸 — 한글은 `hangul_glyph`, 나눈 글자는 그 글자를 반 칸 밀어 자른 조각."""
    if ch in KAGI:
        pair = next(k for k in KAGI_DOTS if KAGI[ch] in k)
        g = np.zeros((ROWS, CELL), dtype=np.uint8)
        for r, row in enumerate(KAGI_DOTS[pair]):
            for c, v in enumerate(row):
                if v == "#" and (c < 6) == (KAGI[ch] == pair[0]):
                    g[r, c % 6] = 1
        return g
    if ch == JE_LEAD or ch in JE_DIGIT:
        je = np.asarray(hangul_glyph("제"), dtype=np.uint8)
        g = np.zeros((ROWS, CELL), dtype=np.uint8)
        h = SPLIT_SHIFT
        if ch == JE_LEAD:
            g[: je.shape[0], h : 2 * h] = je[:, :h]  # 왼쪽 반 칸은 비우고 제 의 왼쪽 6열
        else:
            right = je[:, h:]  # 제 의 오른쪽(11 − 6 = 5열)
            g[: je.shape[0], : right.shape[1]] = right
            d = np.asarray(hangul_glyph(JE_DIGIT[ch]), dtype=np.uint8)
            w = min(d.shape[1], h)
            g[: d.shape[0], h : h + w] = np.maximum(g[: d.shape[0], h : h + w], d[:, :w])
        return g
    if ch in LEAD_DIGITS:
        g = np.zeros((ROWS, CELL), dtype=np.uint8)
        d = np.asarray(hangul_glyph(LEAD_DIGITS[ch]), dtype=np.uint8)
        w = min(d.shape[1], CELL - SPLIT_SHIFT)
        g[: d.shape[0], SPLIT_SHIFT : SPLIT_SHIFT + w] = d[:, :w]
        return g
    if ch in FULL_DOTS:
        g = np.zeros((ROWS, CELL), dtype=np.uint8)
        for r, row in enumerate(FULL_DOTS[ch]):
            g[r, : len(row)] = [c == "#" for c in row]
        return g
    if ch in HUD_DOTS:
        g = np.zeros((ROWS, HANGUL_W), dtype=np.uint8)
        for r, row in enumerate(HUD_DOTS[ch]):
            g[HUD_ROW0 + r, : len(row)] = [c == "#" for c in row]
        return g
    if ch not in SPLIT:
        return hangul_glyph(ch)
    base, side = SPLIT[ch]
    g = np.asarray(hangul_glyph(base), dtype=np.uint8)
    wide = np.zeros((g.shape[0], CELL * 2), dtype=np.uint8)
    wide[:, SPLIT_SHIFT : SPLIT_SHIFT + g.shape[1]] = g  # 두 칸 캔버스에 반 칸 밀어 놓는다
    return wide[:, :CELL] if side == "L" else wide[:, CELL:]


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
