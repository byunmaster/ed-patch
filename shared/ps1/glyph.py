"""PS1 GMF 인게임 폰트 글리프 읽기·쓰기 — **디스크마다 갈리는 값은 `Layout` 으로 받는다**(ED3·ED4 공통 구조).

렌더러는 코드를 읽어 `글리프 = 폰트 RAM 베이스 + 코드 × 18` 로 그린다. 색인이 곧 문자 코드라 한자 슬롯을 한글로 덮고 그 코드로 인코딩하면 화면에 나온다.
기하는 **12행 × 12비트 밀착 패킹(18B)** — `shared.fonts.pack18`.

🔴 **저장 규약이 디스크마다 다르다**(실측 2026-09-03):
  ED3: 열 짝 교환 O(이웃한 두 열이 뒤바뀌어 저장 — 4bpp 전개 때 니블 순서) · 글자 몸통이 0~10행
  ED4: 열 짝 교환 X · 글자 몸통이 1~11행
⚠ 한쪽 규약으로 다른 쪽을 읽으면 글자가 그럭저럭 보이는 채로 틀린다 — 그래서 `Layout` 을 인자로 **명시**하게 한다(기본값 없음).
🔴 **폰트의 끝도 코드에 적혀 있다** — 렌더러 전개표 RAM 이 배열 바로 뒤라 `(표 − 베이스) // 18` 이 칸 수다. 그 뒤는 살아 있는 자료라 거기 구우면 안 된다.
"""

from dataclasses import dataclass

import numpy as np

from shared import fonts

GLYPH_BYTES = 18
ROWS = CELL = 12
EXE_TADDR = 0x80010000  # PS-EXE t_addr (두 디스크 같다)
EXE_HDR = 0x800  # 파일 앞 헤더


@dataclass(frozen=True)
class Layout:
    ram: int  # 폰트 배열 RAM 베이스
    table: int  # 렌더러 전개표 RAM = 배열의 끝
    swap: bool  # 이웃한 두 열이 짝으로 뒤바뀌어 저장되나
    top: int  # 글자 몸통이 시작하는 저장 행

    def off(self):
        """폰트 배열의 **파일** 오프셋."""
        return self.ram - EXE_TADDR + EXE_HDR

    def slots(self):
        """폰트 칸 수(= 마지막 글리프 색인 + 1)."""
        return (self.table - self.ram) // GLYPH_BYTES


ED3 = Layout(ram=0x8009E170, table=0x800A620C, swap=True, top=0)
ED4 = Layout(ram=0x80070BD4, table=0x800793F4, swap=False, top=1)


def swap_pairs(bits):
    """이웃한 두 열의 짝 교환(0↔1, 2↔3, …) — 자기 역함수라 읽기·쓰기가 같은 함수를 쓴다."""
    b = np.array(bits, dtype=np.uint8, copy=True)
    for c in range(0, CELL, 2):
        b[:, [c, c + 1]] = b[:, [c + 1, c]]
    return b


def read_glyph(exe, code, lay):
    """(12,12) 0/1 — 화면에 나오는 그대로(저장 규약을 되돌린 뒤 윗줄을 맞춘다). 두 디스크가 같은 틀로 돌려 주므로 글리프끼리 바로 대조된다."""
    off = lay.off()
    raw = fonts.unpack18(exe[off : off + (code + 1) * GLYPH_BYTES], code, ROWS, CELL)
    g = swap_pairs(raw) if lay.swap else np.array(raw, dtype=np.uint8, copy=True)
    if lay.top:
        g = np.roll(g, -lay.top, axis=0)
        g[-lay.top :] = 0
    return g


def write_glyph(buf, code, bits, lay):
    """bytearray 안의 글리프 하나를 덮어쓴다(그 디스크의 저장 규약으로 되돌려서). 폰트 밖 칸이면 실패."""
    if not 0 <= code < lay.slots():
        raise ValueError(f"글리프 코드 {code} 가 폰트 밖이다(0~{lay.slots() - 1})")
    o = lay.off() + code * GLYPH_BYTES
    grid = np.zeros((ROWS, CELL), dtype=np.uint8)
    src = np.asarray(bits, dtype=np.uint8)
    h = min(src.shape[0], ROWS - lay.top)
    grid[lay.top : lay.top + h, : src.shape[1]] = src[:h, :CELL]
    buf[o : o + GLYPH_BYTES] = fonts.pack18(swap_pairs(grid) if lay.swap else grid, ROWS, CELL)
