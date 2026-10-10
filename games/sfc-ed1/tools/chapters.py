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
FONT = "Galmuri11.bdf"  # 장 띠(그래픽)만 Galmuri11 일반 — 마스터 10-11 「메뉴 장카드 같은건 갈무리11 쓸까? 여긴 갈무리가 더 어울릴것 같은데」. 본문은 Condensed
# 세로 — Galmuri11 은 11행이라 DY=-2(흰 획 행 1~11, 바깥 테두리 행 0~12)로 앉힌다. 원판 띠 글자는 타일 행 0~11(12행)이다.
# DY=-3(행 0~10)으로 올려 보기도 했으나 **맨 아랫줄이 잘려 보인다**는 마스터 판정(10-11 「가운데걸로 하자 맨밑에는 좀 짤리네」)으로 -2 확정.
DY = -2
ADV = 12  # 글자 한 칸 진행(Galmuri11 한글·전각 숫자 DWIDTH 12)
HALF = 6  # 반각 공백
X0 = 3  # 첫 글자 시작 x — 원판 제1~5장 띠를 조립 표에서 재면 흰 획이 x=3(테두리 2)에서 시작한다(종장만 빽빽해 1). 마스터 10-11 「원본도 왼쪽에 딱 붙어?」
HEAD_GAP = 2 * HALF  # 「제１장」과 제목 사이 — 반각 두 칸(새턴·PS1 통일 꼴, 마스터 10-11)
FULLWIDTH_DIGITS = str.maketrans("0123456789", "０１２３４５６７８９")  # 번호 꼴은 정본 「제１장」(전각)
# 종장만 136px 에 안 들어간다(159) — 글리프 가로 11→10 압축(가운데 두 열 접기)·진행 10·간격 12(반각 2칸 유지)·공백 5 → 끝 x 135(B 안, 마스터 10-11)
SQUEEZE = {"종장": {"adv": 10, "space": 5}}


def _bits(f, ch: str, squeeze: bool) -> list:
    b = f.bits(ch, dy=DY, rows=16, width=16)
    if not squeeze or ch in ",.":
        return b
    return [list(r[:5]) + [r[5] or r[6]] + list(r[7:11]) + [0] * 6 for r in b]


def _metrics(txt: str, f, digit: set | None = None) -> tuple[set, int, int]:
    """(흰 획 점 집합, 시작 x, 끝 x). 「제N장」 머리는 전각 숫자, 머리와 제목 사이는 반각 두 칸, 제목 안 공백은 반각 한 칸(종장만 압축 꼴).
    왼쪽 정렬(원판 시작 x=3 에 맞춘다) — 원판도 왼쪽이다(마스터 10-11 「sfc 장띠는 원본따라가자」)."""
    head, _, rest = txt.partition(" ")
    sq = SQUEEZE.get(head)
    adv, space = (sq["adv"], sq["space"]) if sq else (ADV, HALF)
    parts = [(head.translate(FULLWIDTH_DIGITS), 0), (rest, HEAD_GAP)]
    x0 = X0
    white, x = set(), x0
    for p, g in parts:
        x += g
        for ch in p:
            if ch == " ":
                x += space
                continue
            if digit is not None and ch in "０１２３４５６７８９":  # 원판 띠 숫자 그림(반각 8px 칸)을 전각 칸(ADV) 가운데에 — 마스터 10-11 「sfc오른쪽 숫자원판으로 가자」
                for dx, dy in digit:
                    white.add((x + (ADV - 8) // 2 + dx, dy))
                x += adv
                continue
            bits = _bits(f, ch, bool(sq))
            for yy in range(16):
                for xx in range(12):
                    if bits[yy][xx]:
                        white.add((x + xx, yy))
            x += HALF if ch in ",." else adv
    return white, x0, x


def fit(txt: str, f, digit: set | None = None) -> tuple[set, int, int]:
    """(흰 획, 시작 x, 끝 x) — 136px 를 넘으면 멈춘다(종장은 압축 꼴로 135)."""
    white, x0, x = _metrics(txt, f, digit)
    if x > WIDTH:
        raise SystemExit(f"제목이 {WIDTH}px 에 안 들어간다: {txt!r}")
    return white, x0, x


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
    # 🔴 조각 a 는 a+$100 도 먹는다 — 빈 자리 목록에는 a 와 a+$100 이 **둘 다 시작 자리로** 올라 있어 둘을 다 쓰면 한 조각의 아랫절반을
    #   다른 조각의 윗절반이 덮는다(종장 「그리고 영웅들의 전설」 칸 6~9 가 칸 13~16 에 덮였다, 2026-10-11 마스터 장 카드 전수 점검).
    #   앞에서부터 고르며 이미 쓴 자리의 ±$100 은 건너뛴다.
    out, taken = [], set()
    for a in reuse + extra:
        if a in taken or a + 0x100 in taken or a - 0x100 in taken:
            continue
        out.append(a)
        taken.add(a)
    return out


def orig_digit_ink(rom: bytes, k: int) -> set:
    """원판 k+1 장 띠의 숫자 칸(칸 2, 반각 8px·굵은 꼴)의 흰 획 점 — 테두리·바탕은 안 가져온다(우리 굽기가 테두리를 다시 두른다)."""
    cell = render(rom, entries(rom)[k]).crop((16, 0, 24, 16))
    return {(x, y) for y in range(14) for x in range(8) if cell.getpixel((x, y)) == 255}


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
        white, x0, w = fit(t["kr"], f, orig_digit_ink(rom, k) if t["kr"].startswith("제") else None)
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
        done.append({"kr": t["kr"], "x0": x0, "end": w, "cells": cells})
    # 구조 계약 — 조각의 윗·아랫절반(a, a+$100)이 다른 조각과 겹치면 글자가 깨진다(종장 실측). 빌드가 조용히 통과하지 않게 센다.
    halves: dict[int, int] = {}
    for k in range(len(data["titles"])):
        for c in range(CELLS):
            e = common.snes2off(TABLE + STRIDE * k + 3 * c)
            a = int.from_bytes(out[e : e + 3], "little")
            if a == BLANK:
                continue
            for h in (a, a + 0x100):
                if halves.setdefault(h, k * CELLS + c) != k * CELLS + c:
                    raise SystemExit(f"장 제목 조각이 겹친다: {common.fmt(h)}")
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
            _w, x0, px = fit(t["kr"], f)
            print(f"  {x0:3d}~{px:3d}/{WIDTH}px  {t['kr']}")
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
