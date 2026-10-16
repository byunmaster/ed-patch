"""HUD 그림 타일 — 인물 이름(아트라스 …)과 「あと」 라벨을 한글 8×8 타일로 굽는다(sfc-ed1 A6 와 같은 방식, 마스터 10-13).

HUD·전투 패널의 이름은 글자가 아니라 **8×8 4bpp 타일**이다. 롬 `$CB:3ADC` 부터 타일 세트(타일 n 은 `+32·(n-1)`)가 있고, 인물마다 이름 칸 네 개의
타일 번호를 `$C0:B525 + 4·인물` 표(`$C0:B4B0` 루틴이 줄 버퍼에 복사)가 정한다. 그래서
  ① 한글 음절을 갈무리7(7×7, BBX 기준선 그대로) 8×8 로 구워 이름 타일 12장($32~$3D) 자리에 넣고
  ② 이름 표를 한글 음절 번호로 다시 쓴다(인물 이름은 정본에서 읽는다 — 게임 폴더에 JP→KR 표를 두지 않는다).
색은 원본 규칙을 따른다 — 이름 타일: 5 = 글자 · 2 = 바깥선(글자 픽셀의 상하좌우 이웃) · 0 = 투명, 라벨(あと) 타일: 3 = 글자 · 2 = 바깥선.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

FONT = common.ROOT / "shared" / "fonts" / "Galmuri7.bdf"
TILE_BASE = 0xCB3ADC  # 타일 1 번
NAME_TABLE = 0xC0B525  # 인물 4 × 이름 타일 4
NAME_TABLE_ORIG = bytes.fromhex("32333435" "34363738" "393a3834" "3b363c3d")
NAME_TILES = list(range(0x32, 0x3E))  # 이름 글자 타일 12장
JP_NAMES = ("アトラス", "ランドー", "フローラ", "シンディ")  # 인물 차례(표 차례 — 원문 키일 뿐, 표기는 정본에서 읽는다)
LABEL_TILES = (0x12, 0x13)  # 「あと」


def _bdf() -> dict[int, tuple[list[int], int, int, int, int]]:
    out = {}
    cur = bb = rows = None
    for line in FONT.read_text(encoding="latin1").splitlines():
        if line.startswith("ENCODING"):
            cur = int(line.split()[1])
        elif line.startswith("BBX"):
            bb = tuple(map(int, line.split()[1:]))
        elif line.startswith("BITMAP"):
            rows = []
        elif line.startswith("ENDCHAR"):
            if cur is not None and rows is not None and bb:
                w = bb[0]
                out[cur] = ([int(r, 16) >> (len(r) * 4 - w) for r in rows], w, bb[1], bb[2], bb[3])
            cur = rows = None
        elif rows is not None and re.fullmatch(r"[0-9A-Fa-f]+", line.strip()):
            rows.append(line.strip())
    return out


def glyph8(ch: str) -> list[list[int]]:
    """글자 → 8×8 잉크(0/1) — 갈무리7 BBX 대로(아랫줄 = 기준선, 위에서 8−(yoff+h) 째 줄)."""
    bits, w, h, xo, yo = _bdf()[ord(ch)]
    g = [[0] * 8 for _ in range(8)]
    top = 8 - (yo + h)
    for i, r in enumerate(bits):
        for x in range(w):
            if (r >> (w - 1 - x)) & 1 and 0 <= top + i < 8 and 0 <= x + xo < 8:
                g[top + i][x + xo] = 1
    return g


def tile4bpp(ink: list[list[int]], c_ink: int, c_edge: int) -> bytes:
    """8×8 잉크 → 4bpp 타일(32B, SNES 평면: 0·1 면 줄별 교차 16B + 2·3 면 16B)."""
    px = [[0] * 8 for _ in range(8)]
    for y in range(8):
        for x in range(8):
            if ink[y][x]:
                px[y][x] = c_ink
    for y in range(8):
        for x in range(8):
            if not ink[y][x]:
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < 8 and 0 <= xx < 8 and ink[yy][xx]:
                        px[y][x] = c_edge
                        break
    out = bytearray(32)
    for y in range(8):
        for plane in range(4):
            v = 0
            for x in range(8):
                v = (v << 1) | ((px[y][x] >> plane) & 1)
            out[(plane // 2) * 16 + y * 2 + (plane % 2)] = v
    return bytes(out)


def tile_off(n: int) -> int:
    return common.snes2off(TILE_BASE) + 32 * (n - 1)


def plan(canon_lookup) -> tuple[dict[int, bytes], bytes]:
    """→ ({타일 번호: 4bpp 바이트}, 새 이름 표 16B). 이름은 `canon_lookup(원문)` 으로 읽는다."""
    names = []
    for jp in JP_NAMES:
        kr = canon_lookup(jp)
        if not kr:
            raise SystemExit(f"HUD 이름: 정본에 「{jp}」 가 없다 — 관리자에게 후보로")
        if len(kr) > 4:
            raise SystemExit(f"HUD 이름 {kr}: 4자를 넘는다 — 이름 칸이 네 개")
        names.append(kr)
    slot: dict[str, int] = {}
    for kr in names:
        for ch in kr:
            if ch not in slot:
                if len(slot) >= len(NAME_TILES):
                    raise SystemExit("HUD 이름 글자가 타일 12장을 넘는다")
                slot[ch] = NAME_TILES[len(slot)]
    table = bytearray()
    for kr in names:
        ids = [slot[c] for c in kr] + [0x00] * (4 - len(kr))
        table += bytes(ids)
    tiles = {t: tile4bpp(glyph8(ch), 5, 2) for ch, t in slot.items()}
    return tiles, bytes(table)


def label_tiles(text: str) -> dict[int, bytes]:
    """「あと」 라벨 두 타일(가로 16px)에 두 글자를 굽는다."""
    if len(text) != 2:
        raise SystemExit(f"HUD 라벨 {text!r}: 2자여야 한다(타일 둘)")
    return {t: tile4bpp(glyph8(ch), 3, 2) for t, ch in zip(LABEL_TILES, text)}


if __name__ == "__main__":
    for ch in "아트라스":
        print(ch)
        print("\n".join("".join("#" if v else "." for v in r) for r in glyph8(ch)))
