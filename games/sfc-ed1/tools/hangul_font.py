"""sfc-ed1 한글 글꼴 뱅크 — Neo둥근모 16×16 을 1bpp 32B 글리프 열로 굽는다 (D1 = A: 16×16 두 칸).

글리프 번호는 **레퍼토리 문자열의 순서**다(코드포인트 오름차순 · 결정적). 2바이트 한글 코드는
`선두 $11+ (n>>8)` · `인덱스 n&$FF` 로 이 번호를 가리킨다(status.md 8절). 이 파일은 글리프 비트만 만든다 —
어느 글자가 필요한지는 번역 정본이 정하고, 지금은 PS1 ED1 번역본으로 크기를 재는 용도다.

판정(스킬 font-strategy §4): 모든 글리프의 잉크가 16×16 안에 있어야 하고 빈 글리프가 없어야 한다.
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

FONT = common.ROOT / "shared" / "fonts" / "neodgm.ttf"
CELL = 16
BASE = "0123456789 !?…。、「」HMEPGOLDCAB"  # 게임이 1바이트로 이미 갖는 글자 — 뱅크에 안 넣는다(참고용)


def render(ch: str, font) -> list[int]:
    """16행 × 16비트(MSB 왼쪽) — 1bpp 32B 글리프."""
    from PIL import Image, ImageDraw

    im = Image.new("L", (CELL * 2, CELL * 2), 0)
    ImageDraw.Draw(im).text((CELL // 2, CELL // 2), ch, font=font, fill=255)
    px = im.load()
    rows = []
    for y in range(CELL):
        v = 0
        for x in range(CELL):
            if px[CELL // 2 + x, CELL // 2 + y] > 127:
                v |= 0x8000 >> x
        rows.append(v)
    # 셀 밖 잉크 검사
    for y in range(CELL * 2):
        for x in range(CELL * 2):
            if px[x, y] > 127 and not (
                CELL // 2 <= x < CELL // 2 + CELL and CELL // 2 <= y < CELL // 2 + CELL
            ):
                raise ValueError(f"셀 밖 잉크: {ch!r} ({x - CELL // 2},{y - CELL // 2})")
    return rows


def bank(chars: str) -> tuple[bytes, list[str]]:
    from PIL import ImageFont

    font = ImageFont.truetype(str(FONT), CELL)
    rep = sorted(set(chars))
    out = bytearray()
    for ch in rep:
        rows = render(ch, font)
        if not any(rows):
            raise ValueError(f"빈 글리프: {ch!r}")
        for v in rows:
            out += v.to_bytes(2, "big")
    return bytes(out), rep


def to_2bpp_tiles(glyph: bytes) -> bytes:
    """1bpp 16×16 → SNES 2bpp 타일 4장(좌상·우상·좌하·우하 = t, t+1, t+$10, t+$11 자리에 놓는다).
    평면 1 은 전부 1 — 원본 글꼴 적재($00:91F5)와 같은 규약(잉크 = 색 3, 바탕 = 색 2)."""
    rows = [int.from_bytes(glyph[2 * y : 2 * y + 2], "big") for y in range(CELL)]
    out = bytearray()
    for ty in (0, 8):
        for tx in (0, 8):
            for r in range(8):
                p0 = (rows[ty + r] >> (8 - tx)) & 0xFF
                out += bytes([p0, 0xFF])
    return bytes(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--from-ps1", action="store_true", help="PS1 ED1 번역본의 음절로 크기를 잰다(임시 레퍼토리)"
    )
    ap.add_argument("--chars", help="레퍼토리 문자열 파일(UTF-8)")
    ap.add_argument("--out", help="글리프 뱅크(.bin) 출력 경로")
    ap.add_argument("--preview", help="시트 PNG 출력 경로")
    a = ap.parse_args()
    if a.from_ps1:
        src = common.ROOT / "games" / "ps1-ed1+2" / "script"
        txt = "".join(p.read_text(encoding="utf-8") for p in sorted(src.glob("ED1*.json")))
        chars = "".join(re.findall(r"[가-힣]", txt))
    elif a.chars:
        chars = Path(a.chars).read_text(encoding="utf-8")
    else:
        ap.error("--from-ps1 또는 --chars")
    data, rep = bank(chars)
    print(
        f"글리프 {len(rep):,} · 1bpp {len(data):,}B · 2bpp {len(rep) * 64:,}B · sha1 {hashlib.sha1(data).hexdigest()[:12]}"
    )
    if a.out:
        Path(a.out).write_bytes(data)
    if a.preview:
        from PIL import Image

        cols = 32
        rows_n = (len(rep) + cols - 1) // cols
        im = Image.new("1", (cols * CELL, rows_n * CELL), 1)
        px = im.load()
        for n, _ch in enumerate(rep):
            g = data[32 * n : 32 * n + 32]
            for y in range(CELL):
                v = int.from_bytes(g[2 * y : 2 * y + 2], "big")
                for x in range(CELL):
                    if v & (0x8000 >> x):
                        px[(n % cols) * CELL + x, (n // cols) * CELL + y] = 0
        im.save(a.preview)


if __name__ == "__main__":
    main()
