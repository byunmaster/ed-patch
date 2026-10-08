"""HUD 인물 이름(A6②) — 한글 8×8 글자 13자를 HUD 전용 타일에 굽고 이름 줄 틀을 다시 짠다.

HUD 오른쪽 위 이름은 대사 글꼴이 아니라 **HUD 전용 소형 타일**(BG2, 한 칸 한 자 8×8, 2bpp)이다
(2026-09-26 실기 — 세이브엔 글자가 없다). 이름마다 줄 틀 `$00:9A37 + 16·n`(8워드 = [빈][이름 6칸][L])이
타일 `$1C0~$1FF` 를 놓고, 그 타일 그림은 롬에 한 장씩 있다(VRAM 을 읽어 해시로 되짚음 — `TILE_SRC`).

도안 정본은 `textmap/hud_names_8x8.txt`(`--dump` 로 Galmuri7 에서 뽑는다 — 마스터 판정 09-26: 글꼴 원형 그대로,
**글꼴 기준선**(BDF yoff) 그대로라 오·스·로·소는 윗줄이 세·리와 같은 행이고 아래가 한 줄 짧다). 빌드는 그 파일만
읽는다(결정성). 색은 원본 규칙 — 3 = 글자 · 1 = 검은 테두리(글자 픽셀의 상하좌우 이웃) · 2 = 바탕, 0행은 비운다.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import namesrc

DOTS = common.GAME_DIR / "textmap" / "hud_names_8x8.txt"
FONT = "Galmuri7.bdf"
JP_NAMES = ("セリオス", "リュナン", "ロー", "ゲイル", "ソニア")  # 줄 틀 차례(원본 이름)
# 🔴 표기는 **사전에서 읽는다**(게임 폴더에 JP→KR 표를 두지 않는다 — 마스터 10-07). 사전이 바뀌면 여기가 따라가고,
#    한글 글자가 `TILES`(타일 13장)를 넘으면 `chars()` 가 알린다.
NAMES = [namesrc.resolve(jp, namesrc._NAME_ORDER)[0] for jp in JP_NAMES]
ROW_BASE = 0x009A37  # 이름 줄 틀 — 8워드 × 다섯
ROW_WORDS = 8
ROW_ORIG = [  # 원본 틀(검증용) — [빈][이름 칸 ×6][L]
    "2700f111f211f311f41127002700ae05",
    "2700f211c011c111c21127002700ae05",
    "2700fc11fd112700270027002700ae05",
    "2700c611c711c811270027002700ae05",
    "2700c311c411c511270027002700ae05",
]
BLANK = 0x0027
ATTR = 0x1000  # 팔레트 4 (원본 이름 타일 워드의 윗바이트 $11 중 $10)
# 한글 한 자가 들어갈 HUD 타일 — 원본 이름들이 쓰던 타일을 그대로 다시 쓴다(13장, 남는 $1C2·$1C8 는 안 쓴다)
TILES = {
    "세리오스": [0x1F1, 0x1F2, 0x1F3, 0x1F4],
    "류난": [0x1C0, 0x1C1],
    "로우": [0x1FC, 0x1FD],
    "게일": [0x1C6, 0x1C7],
    "소니아": [0x1C3, 0x1C4, 0x1C5],
}


def TILE_SRC(t: int) -> int:
    """HUD 타일 번호 → 그 그림이 있는 롬 자리(VRAM 을 읽어 롬에서 유일하게 찾은 값, 2026-09-26)."""
    if 0x1C0 <= t <= 0x1C8:
        return 0x18F02C + 16 * (t - 0x1C0)
    if 0x1F1 <= t <= 0x1FD:
        return 0x18F23C + 16 * (t - 0x1F1)
    raise ValueError(f"모르는 HUD 타일 ${t:03X}")


def chars() -> list[str]:
    out = []
    for n in NAMES:
        for c in n:
            if c not in out:
                out.append(c)
    return out


def dump() -> str:
    """Galmuri7 → 도트 텍스트. 글꼴 기준선 그대로, 13자 공통 한 번의 세로 이동으로 잉크 윗줄 최상단을 1행에."""
    sys.path.insert(0, str(common.GAME_DIR.parent.parent))
    from shared.fonts import BdfFont

    f = BdfFont(str(common.GAME_DIR.parent.parent / "shared" / "fonts" / FONT))
    cs = chars()
    raw = {c: f.bits(c, rows=16, width=8) for c in cs}
    top = min(min(y for y in range(16) if raw[c][y].any()) for c in cs)
    lines = []
    for c in cs:
        b = raw[c]
        rows = ["".join("#" if b[top - 1 + y][x] else "." for x in range(8)) for y in range(8)]
        if b[top + 7 :].any():
            raise SystemExit(f"{c} 가 8행을 넘는다")
        lines.append(c)
        lines += rows
    return "\n".join(lines) + "\n"


def load() -> dict[str, list[str]]:
    lines = DOTS.read_text(encoding="utf-8").splitlines()
    out: dict[str, list[str]] = {}
    i = 0
    while i < len(lines):
        c = lines[i]
        rows = lines[i + 1 : i + 9]
        if len(c) != 1 or len(rows) != 8 or any(len(r) != 8 or set(r) - {"#", "."} for r in rows):
            raise SystemExit(f"{DOTS.name} {i + 1}행: 「글자 + 8줄 × 8칸(#/.)」 꼴이 아니다")
        out[c] = rows
        i += 9
    if sorted(out) != sorted(chars()):
        raise SystemExit(f"{DOTS.name} 의 글자가 이름 13자와 다르다: {''.join(out)}")
    return out


def tile_bytes(rows: list[str]) -> bytes:
    g = [[3 if ch == "#" else 2 for ch in r] for r in rows]
    for y in range(8):
        for x in range(8):
            if g[y][x] != 3 and any(
                0 <= y + dy < 8 and 0 <= x + dx < 8 and rows[y + dy][x + dx] == "#"
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))
            ):
                g[y][x] = 1
    b = bytearray()
    for y in range(8):
        p0 = p1 = 0
        for x in range(8):
            p0 |= (g[y][x] & 1) << (7 - x)
            p1 |= (g[y][x] >> 1) << (7 - x)
        b += bytes([p0, p1])
    return bytes(b)


def glyph_of(tb: bytes) -> list[str]:
    """2bpp 타일 → 글자 픽셀(색 3)만 `#`."""
    return [
        "".join(
            "#" if (tb[2 * y] >> (7 - x)) & 1 and (tb[2 * y + 1] >> (7 - x)) & 1 else "."
            for x in range(8)
        )
        for y in range(8)
    ]


def bake(out: bytearray, rom: bytes) -> dict:
    dots = load()
    for n, name in enumerate(NAMES):
        ro = common.snes2off(ROW_BASE + 2 * ROW_WORDS * n)
        if bytes(rom[ro : ro + 2 * ROW_WORDS]).hex() != ROW_ORIG[n]:
            raise SystemExit(f"HUD 이름 줄 틀 {n} 이 예상과 다르다: {rom[ro : ro + 16].hex()}")
        ts = TILES[name]
        if len(ts) != len(name) or len(name) > 6:
            raise SystemExit(f"HUD 이름 {name!r} 칸 배정이 틀렸다")
        words = [BLANK] + [ATTR | t for t in ts] + [BLANK] * (6 - len(ts)) + [0x05AE]
        for i, w in enumerate(words):
            out[ro + 2 * i] = w & 0xFF
            out[ro + 2 * i + 1] = w >> 8
        for c, t in zip(name, ts, strict=True):
            so = common.snes2off(TILE_SRC(t))
            tb = tile_bytes(dots[c])
            out[so : so + 16] = tb
            if glyph_of(bytes(out[so : so + 16])) != dots[c]:
                raise SystemExit(f"HUD 이름 {c} 되읽기가 도트 파일과 다르다")
    return {"이름": NAMES, "글자": len(dots)}


def patch_ranges() -> list[tuple[int, int]]:
    r = [(common.snes2off(ROW_BASE), common.snes2off(ROW_BASE) + 2 * ROW_WORDS * len(NAMES))]
    for ts in TILES.values():
        for t in ts:
            o = common.snes2off(TILE_SRC(t))
            r.append((o, o + 16))
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dump", action="store_true", help=f"{FONT} 에서 도안을 뽑아 {DOTS.name} 에 쓴다"
    )
    a = ap.parse_args()
    if a.dump:
        DOTS.write_text(dump(), encoding="utf-8")
        print(f"→ {DOTS}")
