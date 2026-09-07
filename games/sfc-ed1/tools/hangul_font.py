"""sfc-ed1 한글 글꼴 뱅크 — Neo둥근모 16×16 을 1bpp 32B 글리프 열로 굽는다 (D1 = A: 16×16 두 칸).

글리프 번호는 **레퍼토리 문자열의 순서**다(코드포인트 오름차순 · 결정적). 2바이트 한글 코드는
`선두 $11+ (n>>8)` · `인덱스 n&$FF` 로 이 번호를 가리킨다(status.md 8절). 이 파일은 글리프 비트만 만든다 —
어느 글자가 필요한지는 번역 정본이 정하고, 지금은 PS1 ED1 번역본으로 크기를 재는 용도다.

판정(스킬 font-strategy §4): 모든 글리프의 잉크가 16×16 안에 있어야 하고 빈 글리프가 없어야 한다.
"""

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

# 글꼴은 **고를 수 있다**(D4 — 유저 확정 2026-09-05: **인게임 = 갈무리 · 오프닝/엔딩 = Neo둥근모**.
# 다른 게임 트랙과 같은 규약이다. ⚠ Galmuri 상류에 **16px 은 없다**(7·9·11·14뿐) — 16셀엔 Galmuri14 가 맞다).
#   neodgm      — Neo둥근모 16×16 TTF. 셀을 꽉 채운다(새턴 트랙 확정 글꼴)
#   Galmuri14   — 14×14 BDF. 16 셀에 2px 여유 · Galmuri 집안 계열
#   Galmuri11   — 11×11 BDF. PS1 트랙 글꼴이지만 16 셀에 넣으면 자간이 5px 떠 성글다
# ⚠ 셀은 16×16 고정(D1=A)이라 **설계 크기가 셀보다 크면 안 된다** — 축소는 받침을 무너뜨린다
# (`shared/fonts/README.md`).
# 기본 = 인게임 글꼴. 오프닝/엔딩은 뱅크 $1E 가 **따로 적재**하므로(status 8절) 그쪽만 neodgm 으로 굽는다.
FONT_NAME = os.environ.get("SFC_KR_FONT", "Galmuri11-Condensed")
OPENING_FONT = "neodgm"
# dy 는 **원본 가나의 기준선**에 맞춘다 — 시트 전수 실측(2026-09-06)으로 가나 158자 중 155자가
# **행 13** 에서 끝난다(윗줄은 큰 가나가 1, 대부분 4~5). 아랫줄을 13 에 맞추면 원문과 한글이 같은 줄에 선다.
# ⚠ 예전 값(Galmuri14 −3 · Galmuri11 −1)은 **Neo둥근모의 겉모습에 맞춘 것**이라 한 줄씩 어긋나 있었다
# (14 는 1px 아래 · 11 은 1px 위). 눈이 아니라 잰 값으로 맞춘다.
# `w` = 셀 가로(8 = 반각 한 칸 · 16 = 전각 두 칸). D1=B 로 바꾸면서 생긴 칸이다.
FONTS = {
    # 🟢 D1=B 확정(유저 2026-09-06) — 완성형 11,172자가 **전부 폭 7px** 라 8칸에 그대로 든다
    #    (8px 초과 0 · 빈 글리프 0 · 숫자·영문·부호도 전부). 우겨넣는 게 아니라 설계가 반각이다.
    # dy −1: **원판 가나와 밑선을 맞춘 값**(2026-09-07 화면 실측). 원판 가나는 칸의 행 0~12 를 쓰고
    # 우리 글꼴은 11행이라, dy −1 이어야 잉크가 행 2~12 로 **아랫줄이 같아진다**.
    # 🔴 예전 −2 는 행 1~11 이라 밑선이 2px 떠서, 게임이 그리는 **커서(안 건드린 것)가 낮아 보였다**
    #    — 유저 제보 「커서 위치가 메뉴 중앙에 안 온다」의 실체다. 커서는 원판과 **완전히 같았다**
    #    (화면 y 95~101 동일). 움직인 건 우리 글자 쪽이었다.
    "Galmuri11-Condensed": {"path": "Galmuri11-Condensed.bdf", "kind": "bdf", "dy": 0, "w": 8},
    "neodgm": {"path": "neodgm.ttf", "kind": "ttf", "size": 16, "dy": 0, "w": 16},  # 잉크 y1~13
    "Galmuri14": {"path": "Galmuri14.bdf", "kind": "bdf", "dy": -4, "w": 16},  # 잉크 y0~13 · x1~14
    "Galmuri11": {"path": "Galmuri11.bdf", "kind": "bdf", "dy": 0, "w": 16},  # 잉크 y3~13
    "GalmuriMono11": {"path": "GalmuriMono11.bdf", "kind": "bdf", "dy": 0, "w": 16},
}
FONT = common.ROOT / "shared" / "fonts" / FONTS[FONT_NAME]["path"]
CELL = 16  # 세로는 늘 16(글자 한 칸 = 타일 t + t+$10)
CELL_W = FONTS[FONT_NAME].get("w", 16)  # 가로 — 8 이면 한 자가 **한 칸**이다
BASE = "0123456789 !?…。、「」HMEPGOLDCAB"  # 게임이 1바이트로 이미 갖는 글자 — 뱅크에 안 넣는다(참고용)


def load_font():
    """선택된 글꼴을 연다 — TTF 는 PIL, BDF 는 공용 `shared.fonts.BdfFont`(도트 무손실)."""
    spec = FONTS[FONT_NAME]
    if spec["kind"] == "ttf":
        from PIL import ImageFont

        return ("ttf", ImageFont.truetype(str(FONT), spec["size"]), spec["dy"])
    sys.path.insert(0, str(common.ROOT))
    from shared.fonts import BdfFont

    return ("bdf", BdfFont(str(FONT)), spec["dy"])


def render(ch: str, font) -> list[int]:
    """16행 × `CELL_W` 비트(MSB 왼쪽). 반각이면 8비트(1bpp 16B) · 전각이면 16비트(32B).
    ⚠ **창은 늘 16×16 으로 떠서 잰다** — 글꼴 이름의 px 는 잉크가 시작하는 행이 아니라서
    창을 글꼴 크기로 잡으면 받침이 조용히 잘린다(2026-09-06 목업에서 두 번째로 밟았다)."""
    kind, f, dy = font if isinstance(font, tuple) else ("ttf", font, 0)
    top = 1 << (CELL_W - 1)
    if kind == "bdf":
        bits = f.bits(ch, dy=dy, rows=CELL, width=CELL)
        for y in range(CELL):  # 반각인데 칸을 넘으면 조용히 자르지 않고 운다
            for x in range(CELL_W, CELL):
                if bits[y][x]:
                    raise ValueError(f"셀({CELL_W}px) 밖 잉크: {ch!r} x={x}")
        rows = []
        for y in range(CELL):
            v = 0
            for x in range(CELL_W):
                if bits[y][x]:
                    v |= top >> x
            rows.append(v)
        return rows
    from PIL import Image, ImageDraw

    im = Image.new("L", (CELL * 2, CELL * 2), 0)
    ImageDraw.Draw(im).text((CELL // 2, CELL // 2 + dy), ch, font=f, fill=255)
    px = im.load()
    rows = []
    for y in range(CELL):
        v = 0
        for x in range(CELL_W):
            if px[CELL // 2 + x, CELL // 2 + y] > 127:
                v |= top >> x
        rows.append(v)
    for y in range(CELL * 2):
        for x in range(CELL * 2):
            if px[x, y] > 127 and not (
                CELL // 2 <= x < CELL // 2 + CELL and CELL // 2 <= y < CELL // 2 + CELL
            ):
                raise ValueError(f"셀 밖 잉크: {ch!r} ({x - CELL // 2},{y - CELL // 2})")
    return rows


def bank(chars: str) -> tuple[bytes, list[str]]:
    font = load_font()
    rep = sorted(set(chars))
    out = bytearray()
    n = CELL_W // 8  # 한 행의 바이트 수 — 반각 1 · 전각 2
    for ch in rep:
        rows = render(ch, font)
        if not any(rows):
            raise ValueError(f"빈 글리프: {ch!r}")
        for v in rows:
            out += v.to_bytes(n, "big")
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
