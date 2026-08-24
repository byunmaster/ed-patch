"""비트맵 폰트 — BDF 무손실 추출 + 게임 글리프 패킹. 플랫폼 공용.

**11×11 획을 16비트 폭 11행(22B)에 담는 격자**가 PS1 과 새턴에서 똑같다 —
PS1 은 `ED.EXE` 안의 한자 글리프, 새턴은 `/11KANJI.FON`(4,375 × 22B)이다. 그래서
BDF 를 읽어 `pack22()` 로 굽는 이 층이 둘 다의 입력이 된다(둘째 소비자가 실재해서
`shared/` 로 올렸다 — 루트 `CLAUDE.md` 「YAGNI」).

    from fonts import galmuri, convert_chars
    convert_chars("가나다")        # {문자: 22바이트}

⚠ **TTF 렌더는 여기 없다.** Pillow 는 Raqm(HarfBuzz) 유무로 같은 입력에도 배치가 달라져
  머신마다 다른 바이트가 나온다(2026-08-09 실측). BDF 는 도트가 파일에 그대로 박혀 있어
  그 위험이 없다 — 배포 폰트를 Galmuri(OFL)로 고른 이유이기도 하다. TTF 프로토타입은
  쓰는 데가 하나뿐이라 `ps1-ed1+2/tools/hangul_font.py` 에 남겨 뒀다.
"""

import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

ROWS = 11  # 글리프 행 수
WIDTH = 16  # 저장 폭(비트). 실제 표시 셀은 11~12px
CELL = 11  # 게임 글리프 유효 셀


def pack22(bits, rows=ROWS):
    """(rows, ≥16) 0/1 → 행당 2B, MSB 우선. 22B(11행) 격자의 정본."""
    padded = np.zeros((rows, 16), dtype=np.uint8)
    padded[:, : bits.shape[1]] = bits[:, :16]
    return np.packbits(padded, axis=1).tobytes()


def load_bdf(path):
    """BDF → `{코드포인트: (w, h, xoff, yoff, [행 비트값])}`, ascent."""
    glyphs = {}
    ascent = None
    with open(path, encoding="utf-8", errors="replace") as f:
        cp = bbx = rows = None
        for line in f:
            t = line.split()
            if not t:
                continue
            if t[0] == "FONT_ASCENT":
                ascent = int(t[1])
            elif t[0] == "ENCODING":
                cp = int(t[1])
            elif t[0] == "BBX":
                bbx = tuple(int(v) for v in t[1:5])
            elif t[0] == "BITMAP":
                rows = []
            elif t[0] == "ENDCHAR":
                if cp is not None and cp >= 0 and bbx:
                    glyphs[cp] = (*bbx, rows or [])
                cp = bbx = rows = None
            elif rows is not None:
                rows.append(int(t[0], 16))
    return glyphs, ascent


class BdfFont:
    """`(rows, width)` 0/1 배열을 내는 BDF 래퍼."""

    def __init__(self, path):
        self.path = path
        self.glyphs, self.ascent = load_bdf(path)

    def has(self, ch):
        return ord(ch) in self.glyphs

    def bits(self, ch, dx=0, dy=0, rows=ROWS, width=WIDTH):
        g = self.glyphs.get(ord(ch))
        out = np.zeros((rows, width), dtype=np.uint8)
        if not g:
            return out
        w, h, xo, yo, gr = g
        top = self.ascent - (yo + h) + dy
        nbits = ((w + 7) // 8) * 8
        for r, v in enumerate(gr):
            y = top + r
            if not 0 <= y < rows:
                continue
            for x in range(w):
                if v & (1 << (nbits - 1 - x)):
                    px = x + xo + dx
                    if 0 <= px < width:
                        out[y, px] = 1
        return out


# ── 프로덕션 폰트: Galmuri (OFL, 11×11 — 게임 셀과 같은 격자) ────────────────
GALMURI11_BDF = os.path.join(HERE, "Galmuri11.bdf")
GALMURI11_DY = -3  # ascent 14 → 셀 0~10행 정렬 (전 글리프 top행 3 확인됨)

_CACHE = {}


def galmuri(name="Galmuri11"):
    """이름으로 BDF 하나 — 같은 파일은 한 번만 읽는다(4,000 글리프짜리다)."""
    if name not in _CACHE:
        _CACHE[name] = BdfFont(os.path.join(HERE, f"{name}.bdf"))
    return _CACHE[name]


def convert_chars(chars, bdf=None, dy=GALMURI11_DY, rows=ROWS):
    """문자 집합 → `{문자: 22바이트 글리프}`. 재삽입기의 폰트 빌드 입력.

    ⚠ 잉크가 없는 글리프는 **조용히 빈칸이 된다** — 부르는 쪽이 판단하도록 이름을 돌려준다.
    """
    bdf = bdf or galmuri()
    out, missing = {}, []
    for ch in chars:
        bits = bdf.bits(ch, dy=dy, rows=rows)
        if not bits.any() and not ch.isspace():
            missing.append(ch)
        out[ch] = pack22(bits, rows=rows)
    return out, missing
