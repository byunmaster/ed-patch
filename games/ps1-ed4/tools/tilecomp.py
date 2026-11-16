"""반각 합성의 **파이썬 모델**(오라클) — ps1-ed3 `tilecomp` 을 ED4 저장 규약(이웃 열 교환 없음)에 맞춰 옮겼다.

엔진은 「칸 = 12px 격자 + VRAM 타일」이다. 칸을 움직이면 배경이 글자와 함께 끌려가 구멍·겹침이 나므로 **스프라이트는 안 건드리고 글자를 픽셀 위치에 맞춰 타일에 합성**한다:
6px 글자(공백·부호·숫자)는 한 칸의 절반만 차지하고, 12px 글자가 칸 경계를 걸치면 오른쪽 조각은 다음 타일로 넘긴다.

저장: 글리프 = 12행 × 12비트 밀착 18B(MSB 우선 = 왼쪽 픽셀). 3바이트 = 두 행. 6px 이동은 비트 시프트와 같다.
타일 → VRAM: 행마다 12px = 4bpp 6바이트(왼쪽 픽셀이 낮은 니블, 켜진 픽셀 = 색인 1) + 맨 아래 빈 줄 6바이트(13행) = 78B.
이 모델이 asm 훅(`halfwidth.py`)의 기준(oracle)이다.
"""

ROWS = 12
CELL = 12
MASK = 0xFFF


def unpack(b18):
    """18B → 12행(각 12비트). 3바이트 = 두 행."""
    rows = []
    for i in range(0, 18, 3):
        b0, b1, b2 = b18[i : i + 3]
        rows.append((b0 << 4) | (b1 >> 4))
        rows.append(((b1 & 0xF) << 8) | b2)
    return rows


def pack(rows):
    """12행 → 18B (`unpack` 의 역)."""
    out = bytearray()
    for i in range(0, 12, 2):
        r0, r1 = rows[i], rows[i + 1]
        out += bytes([r0 >> 4, ((r0 & 0xF) << 4) | (r1 >> 8), r1 & 0xFF])
    return bytes(out)


def expand(rows):
    """12행(12비트) → 타일 바이트 78B(4bpp, 13행) — 엔진의 전개표(`0x80070524`)와 같은 결과."""
    out = bytearray()
    for r in rows:
        for x in range(0, CELL, 2):
            lo = (r >> (CELL - 1 - x)) & 1
            hi = (r >> (CELL - 2 - x)) & 1
            out.append(lo | (hi << 4))
    return bytes(out) + bytes(6)


class Line:
    """줄 하나의 합성 상태 — 현재 픽셀 위치 `pos`(0 부터)와 지금 만드는 타일(`cur`, 12행)."""

    def __init__(self, pos=0):
        self.pos = pos
        self.cur = [0] * ROWS

    def put(self, glyph_rows, adv):
        """글자 하나(12행 정수)를 현재 위치에 놓고 `adv`px(6·12) 전진한다.

        반환: ([(타일 번호, 12행)…], 새 줄 상태) — 이 글자 때문에 **다시 써야 하는 타일**(왼쪽 · 걸치면 오른쪽).
        """
        t, o = divmod(self.pos, CELL)
        left = [(self.cur[r] | (glyph_rows[r] >> o)) & MASK for r in range(ROWS)]
        spill = [(glyph_rows[r] << (CELL - o)) & MASK for r in range(ROWS)] if o else [0] * ROWS
        out = [(t, left)]
        if (
            o and adv == CELL
        ):  # 반 칸 글자는 6px 안에 다 들어 오른쪽으로 안 샌다(잉크가 왼쪽 6px 인 글리프)
            out.append((t + 1, spill))
        self.pos += adv
        self.cur = left if self.pos // CELL == t else spill
        return out
