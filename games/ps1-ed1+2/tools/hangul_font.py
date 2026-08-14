"""
한글 비트맵 폰트 변환기: TTF/TTC 폰트를 게임 글리프 포맷(11행 × 16비트, 22B)으로 변환.

게임 한자 글리프는 11×11px 영역을 사용(폭 최대 16 저장, ~1px 획). 한글 음절을
같은 셀에 렌더해 22바이트 글리프로 패킹한다. 렌더 크기/오프셋은 폰트별로 조정.

미리보기: python hangul_font.py preview  → out/hangul_preview.png

메모(2026-07-09): 11px 한글 가독성 확인됨. 돋움체/굴림체(비트맵 스트라이크)가
게임 획 두께와 잘 맞으나 굴림/돋움은 상용 폰트. **배포판은 오픈 라이선스 픽셀
폰트(Galmuri11 · Neo둥근모 등, 11px 설계)로 교체 예정** — 받침 처리·라이선스 모두 유리.
현재 FONTS는 시스템 폰트 기반 프로토타입.
"""

import os
import sys

import numpy as np
from common import OUT_DIR
from PIL import Image, ImageDraw, ImageFont

# ⚠ 레이아웃 엔진을 못 박는다 — Pillow 는 Raqm(HarfBuzz)이 있으면 그걸 기본으로 쓰는데,
# 같은 Pillow·FreeType 이어도 Raqm 유무로 **글자 배치가 달라진다**(macOS 휠 없음 / 리눅스 휠 있음).
# 그러면 같은 입력에도 머신마다 다른 이미지가 나온다(2026-08-09 실측: START.DAT 8섹터).
BASIC_LAYOUT = ImageFont.Layout.BASIC


ROWS = 11
WIDTH = 16  # 저장 폭(비트). 실제 표시는 11~12px
CELL = 11  # 게임 글리프 유효 셀


def render_glyph(ch, font, size, dx=0, dy=0, threshold=128):
    """ch를 CELL 높이에 맞춰 렌더 → (ROWS, WIDTH) 0/1 배열."""
    img = Image.new("L", (WIDTH, ROWS), 0)
    d = ImageDraw.Draw(img)
    d.text((dx, dy), ch, fill=255, font=font)
    a = np.array(img, dtype=np.uint8)
    return (a >= threshold).astype(np.uint8)


def pack22(bits):
    """(ROWS, WIDTH>=16) 0/1 → 22바이트 (행당 2B, MSB 우선)."""
    padded = np.zeros((ROWS, 16), dtype=np.uint8)
    padded[:, : bits.shape[1]] = bits[:, :16]
    return np.packbits(padded, axis=1).tobytes()


def load_font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index, layout_engine=BASIC_LAYOUT)


# ---- BDF (비트맵 폰트 원본) 파서 — Galmuri 등 도트 무손실 추출 ----


def load_bdf(path):
    """BDF → {codepoint: (w, h, xoff, yoff, [행 비트값])}, ascent 반환."""
    glyphs = {}
    ascent = None
    with open(path, encoding="utf-8", errors="replace") as f:
        cp = bbx = None
        rows = None
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
    """render_glyph()와 같은 (ROWS, WIDTH) 0/1 배열을 내는 BDF 래퍼."""

    def __init__(self, path):
        self.glyphs, self.ascent = load_bdf(path)

    def bits(self, ch, dx=0, dy=0):
        g = self.glyphs.get(ord(ch))
        out = np.zeros((ROWS, WIDTH), dtype=np.uint8)
        if not g:
            return out
        w, h, xo, yo, rows = g
        top = self.ascent - (yo + h) + dy
        nbits = ((w + 7) // 8) * 8
        for r, v in enumerate(rows):
            y = top + r
            if not 0 <= y < ROWS:
                continue
            for x in range(w):
                if v & (1 << (nbits - 1 - x)):
                    px = x + xo + dx
                    if 0 <= px < WIDTH:
                        out[y, px] = 1
        return out


# ---- 프로덕션 폰트: Galmuri11 (OFL, 11×11 — 게임 셀과 동일 격자) ----

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
GALMURI11_BDF = os.path.join(REPO_ROOT, "shared", "fonts", "Galmuri11.bdf")
GALMURI11_DY = -3  # ascent 14 → 셀 0~10행 정렬 (전 글리프 top행 3 확인됨)


def galmuri11():
    return BdfFont(GALMURI11_BDF)


def convert_chars(chars, bdf=None, dy=GALMURI11_DY):
    """문자 집합 → {문자: 22바이트 글리프}. 재삽입기의 폰트 빌드 입력."""
    bdf = bdf or galmuri11()
    out = {}
    for ch in chars:
        bits = bdf.bits(ch, dy=dy)
        if not bits.any():
            print(f"경고: {ch!r} 글리프 없음")
        out[ch] = pack22(bits)
    return out


# ttc 내부 폰트 인덱스 (Windows 기본)
FONTS = {
    "gulim": (r"C:\Windows\Fonts\gulim.ttc", 0),  # 굴림
    "gulimche": (r"C:\Windows\Fonts\gulim.ttc", 1),  # 굴림체(고정폭, 비트맵)
    "dotum": (r"C:\Windows\Fonts\gulim.ttc", 2),  # 돋움
    "dotumche": (r"C:\Windows\Fonts\gulim.ttc", 3),  # 돋움체
    "batang": (r"C:\Windows\Fonts\batang.ttc", 0),
    "malgun": (r"C:\Windows\Fonts\malgun.ttf", 0),
}

SAMPLE = "가나다라마안녕하세요왕자의세리오스마을"


def preview():
    sizes = {"gulim": 12, "gulimche": 12, "dotum": 12, "dotumche": 12, "batang": 12, "malgun": 11}
    scale = 10
    n = len(SAMPLE)
    pad = 1
    rowh = ROWS * scale + 6
    sheet = Image.new("RGB", (n * (CELL * scale + pad) + 120, rowh * len(FONTS)), (30, 30, 40))
    draw = ImageDraw.Draw(sheet)
    for fi, (name, (path, idx)) in enumerate(FONTS.items()):
        size = sizes.get(name, 12)
        font = load_font(path, size, idx)
        y0 = fi * rowh
        draw.text((2, y0 + 2), f"{name} {size}px", fill=(200, 200, 120))
        for ci, ch in enumerate(SAMPLE):
            bits = render_glyph(ch, font, size)
            gi = Image.new("L", (CELL, ROWS), 0)
            px = gi.load()
            for r in range(ROWS):
                for x in range(CELL):
                    if bits[r, x]:
                        px[x, r] = 255
            big = gi.resize((CELL * scale, ROWS * scale), Image.NEAREST)
            sheet.paste(big, (120 + ci * (CELL * scale + pad), y0 + 2))
    out = os.path.join(OUT_DIR, "hangul_preview.png")
    sheet.save(out)
    print(f"saved {out}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "preview":
        preview()
    else:
        print(__doc__)


def font_block():
    """계획(`hangul_map.SYLLABLES`) 차례로 구운 폰트 블록 — **여기서만 만든다.**

    ⚠ 두 곳에서 따로 만들면 한쪽만 고쳐도 티가 안 난다. 계획↔산출물을 묶는 최소 장치다.
    """
    import hangul_map

    glyphs = convert_chars(hangul_map.SYLLABLES)
    return b"".join(glyphs[ch] for ch in hangul_map.SYLLABLES)


def verify_image_font(path):
    """이미지에 실린 폰트가 **지금 계획으로 구운 것과 같은가 — 실행파일 둘 다.**

    빌드 끝에 한 번 부른다. 낡은 이미지에 새 계획으로 덧쓴 자리를 잡는다 — 계획은 순수
    함수라 한 실행 안에서는 안 어긋나지만, 단독 실행·A/B 로 조각조각 갱신하면 어긋난다.

    ⚠ **ED2.EXE 도 본다**(2026-08-14). 실행파일이 둘이고 각자 폰트를 들고 있어서, 한쪽만
    검사하면 다른 쪽이 낡은 채로 통과한다 — 증상은 **그 게임에서만 글자가 깨지는 것**이라
    ED1 만 돌려 보면 영영 안 보인다.
    """
    import hashlib

    import hangul_map
    from common import extract
    from font_map import FONT_BASE

    blk = font_block()
    for game, spec in FONT_BASE.items():
        off = hangul_map.slot_ed_offset(0, game)
        size = {"ED1": 1021952, "ED2": 872448}[game]
        got = bytes(extract(spec["lba"], size, path=path))[off : off + len(blk)]
        if got != blk:
            raise SystemExit(
                f"⚠ {spec['exe']} 의 폰트가 지금 계획과 다르다 — 계획 {hangul_map.PLAN_SHA1} 로"
                f" 구운 블록({hashlib.sha1(blk).hexdigest()[:16]}) 과 이미지"
                f"({hashlib.sha1(got).hexdigest()[:16]}) 가 어긋난다.\n"
                "  낡은 이미지에 새 계획으로 덧썼을 수 있다 — `build.py` 로 전 체인을 다시 돌 것."
            )
    return True
