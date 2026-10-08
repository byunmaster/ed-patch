"""sfc-ed1 챕터 제목 — 그래픽 타일을 **롱 주소 17개**로 조립하는 표를 읽는다.

`第1章 王子の旅立ち` 는 글꼴이 아니라 **2bpp 그래픽**이다(status 12.1). 화면 행 2~3 · 열 1~17 의
17칸을 BG2 에 깔고, 칸마다 8×16 조각을 **뱅크 $18 의 조각 창고**에서 하나씩 DMA 한다.
그 「어느 조각인가」가 이 표다 — 장마다 **17 × 3바이트 롱 주소**, 보폭 51.

    [0..1] 第 (전 장 공유)   [2] 숫자   [3..4] 章 (공유)   [5..] 장 이름   나머지 빈 조각

⇒ **한글로 갈려면 조각을 우리 것으로 굽고 이 주소만 바꾸면 된다.** 색인이 아니라 주소라
   빈 자리 아무 데나 놓아도 된다.

    python3 tools/chapters.py            # 표를 읽어 장별 조각 주소
    python3 tools/chapters.py --png OUT  # 현재(일본어) 제목을 PNG 로
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: F401, I001  (common 보다 먼저 — shared/text 와 이름이 겹친다)
import common

TABLE = 0x00A814  # 장 0 의 첫 조각 주소
CELLS = 17  # 한 장이 쓰는 칸(= 조각) 수
STRIDE = 3 * CELLS  # 51
BLANK = 0x18FBFC  # 빈 조각(글자 없이 밑줄만)
WIDTH = CELLS * 8  # 136px


def entries(rom: bytes, n: int = 8) -> list[list[int]]:
    """장별 조각 주소 17개. 빈 조각으로만 이뤄진 항목이 나오면 거기서 멈춘다."""
    out = []
    for k in range(n):
        base = common.snes2off(TABLE + STRIDE * k)
        row = [
            rom[base + 3 * i] | (rom[base + 3 * i + 1] << 8) | (rom[base + 3 * i + 2] << 16)
            for i in range(CELLS)
        ]
        banks = {KR_BANK_LO >> 16}  # 조각은 뱅크 $18 에만 있다
        if all(a == BLANK for a in row) or any(a >> 16 not in banks for a in row):
            break
        out.append(row)
    return out


def render(rom: bytes, row: list[int]):
    """조각 17개 → 136×16 이미지(2bpp 4색). 조각 하나 = 위 타일 + 그 16타일 뒤(=아래)."""
    from PIL import Image

    im = Image.new("L", (WIDTH, 16), 0)
    px = im.load()
    for c, addr in enumerate(row):
        for half in (0, 1):
            o = common.snes2off(addr + half * 0x100)  # 아래 절반은 시트 한 줄(16타일 = $100) 뒤
            for y in range(8):
                p0, p1 = rom[o + 2 * y], rom[o + 2 * y + 1]
                for x in range(8):
                    v = ((p0 >> (7 - x)) & 1) | (((p1 >> (7 - x)) & 1) << 1)
                    px[c * 8 + x, half * 8 + y] = v * 85
    return im


# ── 한글 굽기 ────────────────────────────────────────────────────────────────────────────
# 조립 표가 **색인이 아니라 롱 주소**라 우리 조각을 빈 뱅크에 놓고 주소만 바꾸면 된다.
# ⚠ 아래 절반은 **위 조각 + $100**(시트가 16타일/줄)이라 우리 배치도 그 관계를 지켜야 한다 —
#   장마다 4줄(=$400)을 잡고 0·1줄에 칸 0~15, 2·3줄에 칸 16 을 둔다.
# 🔴 **조각은 뱅크 $18 에 있어야 한다**(실기 2026-09-06). 표에 3바이트 롱 주소가 들어 있는데도
#   전송 루틴이 **뱅크 바이트를 안 쓴다** — 확장 뱅크($2E)에 두면 화면이 깨진다.
#   ⇒ 원본 일본어 조각 자리를 **재활용**한다(고유 71개 = 2,272B) + 뱅크 안 빈 자리(47개).
KR_BANK_LO, KR_BANK_HI = 0x188000, 0x190000
FONT = "Galmuri11.bdf"
DY = -2  # 흰 획 행 1~11 · 테두리 0~12 (원본 흰 획 0~11 과 아랫줄이 같다)


DIGIT_SHIFT = 2  # (11-7)//2 — 숫자 글리프(원본 폭 7px 급)를 11px 칸 안에서 가운데로


# 🔴 2026-09-15 마스터 확정 — 장 제목 숫자는 전각(11px, 다른 글자와 같은 칸)으로 간다.
# 원본 JP 는 숫자가 7px 로 한자보다 좁았다(위 12.1 절 실측) — 그런데 그건 **원문 줄 자체가
# 가나·숫자(좁음)·한자(네모)로 폭이 섞여 있어서** 자연스러웠던 것이다. 우리 줄은 전부 한글이라
# 네모꼴 일색이라 **숫자 하나만 좁으면 그것만 튄다.** 원본이 그 폭을 쓴 이유가 우리 줄엔 없다
# — 그래서 좁혀 둔 채로 안 두고 넓힌다(다음에 「원본은 좁은데 왜 넓혔지」로 되돌리지 않는다).
# ⚠ 이 특례는 **장 제목(chapters.py)에만** 있다 — `grep isdigit tools/*.py` 로 확인, 다른
# 숫자 표시(HUD·메뉴 등)는 이 코드를 안 거친다.
def _metrics(txt: str, f, gap: int, sw: int) -> tuple[set, int]:
    """(흰 획 점 집합, 폭). 글자 폭은 11(숫자도) — 숫자는 잉크를 칸 안에서 가운데로 미룬다."""
    white, x = set(), 0
    for ch in txt:
        if ch == " ":
            x += sw
            continue
        bits = f.bits(ch, dy=DY, rows=16, width=16)
        shift = DIGIT_SHIFT if ch.isdigit() else 0
        for yy in range(16):
            for xx in range(11):
                if bits[yy][xx]:
                    white.add((x + xx + shift, yy))
        x += 11 + gap
    return white, x - gap


def fit(txt: str, f) -> tuple[set, int, tuple[int, int]]:
    """폭이 136 을 넘으면 **자간 → 공백** 순으로 조인다(원본도 비례폭이라 제목마다 다르다)."""
    for gap, sw in ((1, 6), (0, 6), (0, 5), (0, 4), (0, 3)):
        white, w = _metrics(txt, f, gap, sw)
        if w <= WIDTH:
            return white, w, (gap, sw)
    raise SystemExit(f"제목이 {WIDTH}px 에 안 들어간다: {txt!r}")


def cell_bytes(white: set, cell: int) -> tuple[bytes, bytes]:
    """칸 하나(8×16)를 2bpp 위·아래 타일 바이트로. 색 3=흰 획 · 1=테두리·밑줄 · 2=바탕."""

    def color(x, y):
        if y >= 14:
            return 1 if y == 14 else 3  # 밑줄 2px — 전 칸 공통
        if (x, y) in white:
            return 3
        if any((x + u, y + v) in white for u in (-1, 0, 1) for v in (-1, 0, 1)):
            return 1
        return 2

    halves = []
    for half in (0, 1):
        b = bytearray()
        for y in range(8):
            p0 = p1 = 0
            for x in range(8):
                c = color(cell * 8 + x, half * 8 + y)
                if c & 1:
                    p0 |= 0x80 >> x
                if c & 2:
                    p1 |= 0x80 >> x
            b += bytes([p0, p1])
        halves.append(bytes(b))
    return halves[0], halves[1]


def pool(rom: bytes) -> list[int]:
    """쓸 수 있는 조각 자리 — **원본 제목이 쓰던 자리**(한글로 갈면 필요 없다) + 뱅크 $18 빈 자리.
    조각 하나는 `a` 와 `a+$100` 을 함께 먹으므로 둘 다 비어야 한다."""
    reuse = sorted({a for r in entries(rom) for a in r if a != BLANK})
    o0 = common.snes2off(KR_BANK_LO)
    b = rom[o0 : o0 + 0x8000]

    def blank(a: int) -> bool:
        o = common.snes2off(a) - o0
        return all(b[o + i] in (0, 0xFF) for i in range(16))

    # ⚠ **빈 조각($18:FBFC)의 두 절반은 건드리면 안 된다** — 안 쓰는 칸이 전부 이걸 가리킨다.
    #   16정렬로 훑으면 그 자리를 덮는 슬롯이 생겨 제목 뒤에 쓰레기가 붙는다(실기로 드러났다).
    reserved = set()
    for half in (0, 0x100):
        for i in range(16):
            reserved.add(BLANK + half + i)

    def clean(a: int) -> bool:
        return not any((a + i) in reserved or (a + 0x100 + i) in reserved for i in range(16))

    extra = [
        a
        for a in range(KR_BANK_LO, KR_BANK_HI - 0x110, 0x10)
        if a not in reuse and clean(a) and blank(a) and blank(a + 0x100)
    ]
    return reuse + extra


def bake(out: bytearray, rom: bytes) -> dict:
    """한글 제목을 뱅크 $18 에 굽고 조립 표의 주소를 우리 것으로 돌린다."""
    import json

    sys.path.insert(0, str(common.ROOT))
    from shared.fonts import BdfFont

    import namesrc

    data = namesrc.chapters()
    f = BdfFont(str(common.ROOT / "shared" / "fonts" / FONT))
    slots = pool(rom)
    n = 0
    done = []
    for k, t in enumerate(data["titles"]):
        white, w, (gap, sw) = fit(t["kr"], f)
        cells = -(-w // 8)  # 글자가 실제로 닿는 칸 수 — 나머지는 원본 빈 조각을 가리킨다
        if n + cells > len(slots):
            raise SystemExit(f"조각 자리가 모자란다: {n + cells} > {len(slots)}")
        for c in range(CELLS):
            e = common.snes2off(TABLE + STRIDE * k + 3 * c)
            if c >= cells:
                out[e : e + 3] = BLANK.to_bytes(3, "little")
                continue
            a = slots[n]
            n += 1
            top, bot = cell_bytes(white, c)
            o = common.snes2off(a)
            out[o : o + 16] = top
            o2 = common.snes2off(a + 0x100)
            out[o2 : o2 + 16] = bot
            out[e : e + 3] = a.to_bytes(3, "little")
        done.append({"kr": t["kr"], "px": w, "cells": cells, "gap": gap, "space": sw})
    return {"titles": done, "slots_used": n, "slots": len(slots)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--png", help="현재 제목을 이 경로에 세로로 이어 붙여 쓴다")
    ap.add_argument("--fit", action="store_true", help="한글 제목의 폭·자간을 잰다")
    a = ap.parse_args()
    rom = common.rom_bytes()
    if a.fit:
        import json

        sys.path.insert(0, str(common.ROOT))
        from shared.fonts import BdfFont

        f = BdfFont(str(common.ROOT / "shared" / "fonts" / FONT))
        import namesrc

        for t in namesrc.chapters()["titles"]:
            _w, px, (gap, sw) = fit(t["kr"], f)
            print(f"  {px:4d}/{WIDTH}px  자간{gap} 공백{sw}  {t['kr']}")
        return
    rows = entries(rom)
    for k, row in enumerate(rows):
        uniq = [common.fmt(x) for x in row if x != BLANK]
        print(f"{k + 1}장 @{common.fmt(TABLE + STRIDE * k)} 조각 {len(uniq)}/{CELLS}: {uniq[:6]} …")
    if a.png:
        from PIL import Image

        out = Image.new("L", (WIDTH, 16 * len(rows)), 0)
        for k, row in enumerate(rows):
            out.paste(render(rom, row), (0, k * 16))
        out.resize((WIDTH * 4, 16 * len(rows) * 4), Image.NEAREST).save(a.png)
        print("→", a.png)


if __name__ == "__main__":
    main()
