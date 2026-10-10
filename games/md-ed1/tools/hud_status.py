"""HUD 상태이상 8칸(守跳毒眠黙乱気絶) — 롬 `0x1A50D2` 128B×8 을 한글 한 글자로 교체한다(마스터 10-10 「상태 한자」).

그림 = 16×16 4비트 타일 2×2(열 우선: 타일 t 의 x 오프셋 = (t//2)·8, y 오프셋 = (t%2)·8). 값 13 = 획 테두리,
12 = 글자(守·跳 둘은 6), 0 = 투명(원본 가장자리 몇 칸). 글자는 Galmuri11 한 글자를 **획을 한 칸 굵게**(오른쪽으로 번짐)
16×16 가운데에 놓는다 — 원본 한자가 2px 획이라 얇은 글꼴은 HUD 에서 약해 보인다. PS1 라벨(독·묵·잠·혼·수·반)과 같은 말:
守→수 · 跳→반 · 毒→독 · 眠→잠 · 黙→묵 · 乱→혼 · 気絶→기·절.

    python3 tools/hud_status.py --png out.png     # 미리보기(원본 ↔ 한글)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import hangul

BASE = 0x1A50D2
STRIDE = 128
N = 8
LABELS = ["수", "반", "독", "잠", "묵", "혼", "기", "절"]
BG = 13
INK = [6, 6, 12, 12, 12, 12, 12, 12]  # 원본 둘째 색(守·跳 는 6)


def _glyph16(ch: str) -> list[list[int]]:
    g = hangul._load_bdf(hangul.BDF, 11, 0, 0).get(ch)
    if g is None:
        raise SystemExit(f"hud_status: Galmuri11 에 {ch!r} 가 없다")
    bold = [[g[y][x] or (g[y][x - 1] if x else 0) for x in range(11)] + [g[y][10]] for y in range(11)]
    out = [[0] * 16 for _ in range(16)]
    for y in range(11):
        for x in range(12):
            out[y + 2][x + 2] = bold[y][x]
    return out


def icon(k: int) -> bytes:
    ink = _glyph16(LABELS[k])
    # 원본 한자 = 획(12) + **한 칸 테두리(13)** + 그 밖은 투명(0). 한자는 빽빽해 테두리가 사각형처럼 보일 뿐이라, 성근 한글에
    # 사각형 바탕을 깔면 검은 상자가 된다(마스터 10-10) — 테두리만 둘러 몬스터 머리 위 배경이 비치게 한다.
    def near(y, x):
        return any(
            ink[j][i] for j in range(max(0, y - 1), min(16, y + 2)) for i in range(max(0, x - 1), min(16, x + 2))
        )

    px = [[INK[k] if ink[y][x] else (BG if near(y, x) else 0) for x in range(16)] for y in range(16)]
    out = bytearray()
    for t in range(4):
        ox, oy = (t // 2) * 8, (t % 2) * 8
        for y in range(8):
            for x in range(0, 8, 2):
                out.append((px[oy + y][ox + x] << 4) | px[oy + y][ox + x + 1])
    return bytes(out)


def plan() -> list[tuple[str, int, bytes]]:
    return [("hud-status", BASE, b"".join(icon(k) for k in range(N)))]


def _decode(data: bytes, k: int) -> list[list[int]]:
    ch = data[k * STRIDE : (k + 1) * STRIDE]
    g = [[0] * 16 for _ in range(16)]
    for t in range(4):
        tile = ch[t * 32 : (t + 1) * 32]
        for y in range(8):
            for x in range(8):
                b = tile[y * 4 + x // 2]
                g[(t % 2) * 8 + y][(t // 2) * 8 + x] = (b >> 4) if x % 2 == 0 else (b & 15)
    return g


def preview(out: Path) -> None:
    from PIL import Image

    orig = common.rom()[BASE : BASE + N * STRIDE]
    new = plan()[0][2]
    pal = {0: (30, 30, 80), 13: (0, 0, 0), 12: (230, 40, 40), 6: (60, 120, 255)}
    im = Image.new("RGB", (N * 18, 36), (60, 60, 60))
    for row, data in enumerate((orig, new)):
        for k in range(N):
            g = _decode(data, k)
            for y in range(16):
                for x in range(16):
                    im.putpixel((k * 18 + x, row * 18 + y), pal.get(g[y][x], (255, 0, 255)))
    im.resize((im.width * 6, im.height * 6), Image.NEAREST).save(out)


if __name__ == "__main__":
    if "--png" in sys.argv:
        preview(Path(sys.argv[sys.argv.index("--png") + 1]))
