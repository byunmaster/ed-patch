"""안 B 의 **파이썬 모델**(S2) — 반각을 칸 스프라이트가 아니라 **타일 비트맵 합성**으로 한다.

배경(`root-work`/`root-cause.md` 7~8절): 엔진은 「칸 = 12px 격자 + VRAM 타일(배경+글자 한 몸)」이다. 스프라이트 x·w·h 를 바꾸면(예전 방식)
배경이 글자와 함께 끌려가 구멍·겹침·줄 끝 조각이 생긴다. 그래서 스프라이트는 영원히 고정하고, **글자를 픽셀 위치에 맞춰 타일에 합성**한다:
6px 글자(공백·부호)는 한 칸의 절반만 차지하고, 12px 글자가 칸 경계를 걸치면 오른쪽 조각은 다음 타일로 넘긴다.

저장 규약(실측 `font.py`): 글리프 = 12행 × 12비트 **밀착 패킹 18B**(MSB 우선) — 행은 저장 순서(이웃 열 쌍이 뒤바뀐 채)다.
짝 단위 이동은 짝을 안 깨므로(6px = 3쌍) **저장 순서 그대로** 비트를 밀어도 화면에선 같은 만큼 옆으로 간 것과 같다 → 12비트 행 정수로 다룬다.
이 모델이 asm 훅(S3)의 기준(oracle)이다.
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


class Line:
    """줄 하나의 합성 상태 — 현재 픽셀 위치 `pos`(0 부터)와 지금 만드는 타일(`cur`, 12행)."""

    def __init__(self):
        self.pos = 0
        self.cur = [0] * ROWS

    def put(self, glyph_rows, adv):
        """글자 하나(12행 정수)를 현재 위치에 놓고 `adv`px(0·6·12) 전진한다.

        반환: [(타일 번호, 12행)] — 이 글자 때문에 **다시 써야 하는 타일**(왼쪽 · 걸치면 오른쪽).
        adv 0(안 그림 — 「(으)」 가 받침 없음)이면 글자도 안 놓고 현재 타일만 돌려준다.
        """
        t, o = divmod(self.pos, CELL)
        if adv == 0:
            return [(t, list(self.cur))]
        left = [(self.cur[r] | (glyph_rows[r] >> o)) & MASK for r in range(ROWS)]
        spill = [(glyph_rows[r] << (CELL - o)) & MASK for r in range(ROWS)] if o else [0] * ROWS
        out = [(t, left)]
        if o:
            out.append((t + 1, spill))
        self.pos += adv
        self.cur = left if self.pos // CELL == t else spill
        return out
