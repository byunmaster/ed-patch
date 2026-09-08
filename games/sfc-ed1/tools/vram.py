"""sfc-ed1 VRAM 판독 — emucap 이 뜬 VRAM 덤프에서 「어느 타일이 실제로 쓰이나」를 센다.

타일 예산 질문(대사 동적 슬롯 + 메뉴 상주 글리프 = 356 > 300)을 인게임 사실로 바꾸는 도구다.
글꼴은 VRAM 워드 `$1000 + 8·타일`(= 바이트 $2000 + 16·타일)에 2bpp 로 올라간다(`$00:91F5`).

쓰기:
    emucap read_memory(memory_type="snesVideoRam", address=0, length=0x10000) → 파일로 저장
    python3 tools/vram.py --dump work/derived/vram.bin [--png x.png]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text

FONT_VRAM_BYTE = 0x2000  # 워드 $1000 × 2
TILE_BYTES = 16  # 2bpp 8×8


def tiles(vram: bytes, base: int = FONT_VRAM_BYTE, count: int = 0x200) -> list[bytes]:
    return [vram[base + TILE_BYTES * t : base + TILE_BYTES * (t + 1)] for t in range(count)]


def classify(vram: bytes, count: int = 0x200) -> dict:
    """빈 타일(잉크 0) · 채운 타일을 가른다. 평면 1 이 전부 1 인 원본 규약도 확인한다."""
    used, empty, odd = [], [], []
    for t, tl in enumerate(tiles(vram, count=count)):
        p0 = tl[0::2]
        p1 = tl[1::2]
        if any(p0):
            used.append(t)
        else:
            empty.append(t)
        if any(x != 0xFF for x in p1):
            odd.append(t)
    return {"used": used, "empty": empty, "plane1_not_ff": odd}


def render(vram: bytes, out: str, cols: int = 32, count: int = 0x200, scale: int = 2) -> None:
    from PIL import Image

    rows = (count + cols - 1) // cols
    im = Image.new("L", (cols * 8, rows * 8), 255)
    px = im.load()
    for t, tl in enumerate(tiles(vram, count=count)):
        tx, ty = (t % cols) * 8, (t // cols) * 8
        for r in range(8):
            a, b = tl[2 * r], tl[2 * r + 1]
            for x in range(8):
                v = ((a >> (7 - x)) & 1) | (((b >> (7 - x)) & 1) << 1)
                px[tx + x, ty + r] = 255 - v * 85
    im.resize((im.width * scale, im.height * scale), Image.NEAREST).save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--dump", required=True, help="emucap read_memory(snesVideoRam) 로 받은 64KB 덤프"
    )
    ap.add_argument("--png", help="타일 시트 PNG")
    ap.add_argument("--count", type=lambda x: int(x, 0), default=0x200)
    a = ap.parse_args()
    v = Path(a.dump).read_bytes()
    c = classify(v, a.count)
    print(
        f"글꼴 영역 타일 {a.count}: 쓰임 {len(c['used'])} · 빈 {len(c['empty'])} · 평면1≠$FF {len(c['plane1_not_ff'])}"
    )
    runs = []
    for t in c["empty"]:
        if runs and runs[-1][1] == t - 1:
            runs[-1][1] = t
        else:
            runs.append([t, t])
    print(
        "빈 타일 런:",
        " ".join(f"{a_:03X}-{b:03X}({b - a_ + 1})" for a_, b in runs if b - a_ >= 3)[:400],
    )
    print(
        "코드로 환산:",
        ", ".join(f"{text.TABLE.get(c_, '?')}={c_:02X}" for c_ in ())
        or "(타일→코드는 text.TILE_TABLE 역함수)",
    )
    if a.png:
        render(v, a.png, count=a.count)
        print("→", a.png)
