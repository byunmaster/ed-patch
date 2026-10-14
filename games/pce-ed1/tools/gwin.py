"""**월드를 안 멈추는 대사창 그림**(시제품) — 엔진 대사창과 같은 BG 타일·팔레트로 창을 BAT 에 직접 그린다.

엔진 대사창(실측 2026-10-12, 장면 2): BAT 열 3~24 · 행 11~20, 팔레트 8. 틀 타일 0x500~0x508 은 VRAM 에 늘 올라와 있고(창이 없을 때도 같다),
글자는 **픽셀 줄을 8px 타일 기둥으로 자른 것** — 줄 하나 = 타일 쌍(위 n · 아래 n+1) 기둥들, 번호는 0x660~0x6AF 를 차례로 쓴다.
타일 픽셀: 배경 = 색 1, 글자 = 색 15. 글리프 12×12 는 16px 줄의 2행부터 놓인다.
이 모듈은 문안 → (타일 바이트, BAT 단어)를 만든다. 런타임은 이걸 VRAM 에 쓰기만 한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font
import typeset

TILE0 = 0x660
ROW0, COL0 = 11, 3  # 창 왼쪽 위 모서리의 BAT 좌표
W, H = 22, 10  # 창 열 수 · 행 수(모서리 포함)
PAL = 0x8000
TEXT_COL0 = 4
LINE_ROWS = (12, 14, 16, 18)  # 화자 · 줄1 · 줄2 · 줄3 의 위쪽 행
FRAME = {"tl": 0x500, "tr": 0x501, "bl": 0x502, "br": 0x503, "l": 0x504, "r": 0x505, "t": 0x506, "b": 0x507, "fill": 0x508}


def adv(ch: str) -> int:
    return 4 if ch in typeset.NARROW else 12


def strip(line: str) -> tuple[list[int], int]:
    """줄 → (16행 비트맵 — 행마다 정수, 왼쪽이 최상위 · 8px 기둥 수). 끝 글자가 칸 밖으로 나가는 부분은 자른다."""
    w = sum(adv(c) for c in line)
    ncol = (w + 7) // 8
    pad = (w + 12 + 7) // 8 * 8  # 마지막 글자가 12px 로 그려져도 모자라지 않게
    rows = [0] * 16
    x = 0
    for c in line:
        if c != " ":
            g = font.glyph(c)
            for r in range(12):
                v = int.from_bytes(g[r * 2 : r * 2 + 2], "big") >> 4  # 12비트, 왼쪽이 최상위
                rows[2 + r] |= v << (pad - x - 12)
        x += adv(c)
    return [v >> (pad - ncol * 8) for v in rows], ncol


def expand(strips: bytes) -> bytes:
    """글자 타일 압축본(타일마다 8B — 줄 8행의 글자 비트) → 4bpp 타일 32B. 배경 색 1(plane0 은 늘 1) · 글자 색 15."""
    out = bytearray()
    for k in range(0, len(strips), 8):
        t = strips[k : k + 8]
        for y in range(8):
            out += bytes([0xFF, t[y]])  # plane0 · plane1
        for y in range(8):
            out += bytes([t[y], t[y]])  # plane2 · plane3
    return bytes(out)


def blank_bat() -> dict[tuple[int, int], int]:
    """글자 없는 빈 창의 BAT 단어 {(행, 열): 단어} — 틀 + 바탕만. 쪽이 바뀌는 사이 글자 타일을 올리는 동안 이걸 보인다."""
    bat: dict[tuple[int, int], int] = {}
    for r in range(H):
        for c in range(W):
            if r == 0:
                t = FRAME["tl"] if c == 0 else FRAME["tr"] if c == W - 1 else FRAME["t"]
            elif r == H - 1:
                t = FRAME["bl"] if c == 0 else FRAME["br"] if c == W - 1 else FRAME["b"]
            else:
                t = FRAME["l"] if c == 0 else FRAME["r"] if c == W - 1 else FRAME["fill"]
            bat[(ROW0 + r, COL0 + c)] = PAL | t
    return bat


def make_window(speaker: str | None, text: str) -> tuple[bytes, dict[tuple[int, int], int]]:
    """→ (글자 타일 압축본 — 타일마다 8B, 번호 0x660 부터 차례로 · BAT 단어 {(행, 열): 단어}). 4bpp 로는 `expand`."""
    pgs = typeset.pages(font.expand_packed(text), speaker=speaker is not None)
    assert len(pgs) == 1, "한 쪽만"
    lines = ([speaker] if speaker else []) + pgs[0]
    strips = bytearray()
    bat = blank_bat()
    n = TILE0
    for li, line in enumerate(lines):
        rows, ncol = strip(line)
        top = LINE_ROWS[li] if speaker else LINE_ROWS[li + 1]
        for cidx in range(ncol):
            for half in (0, 1):
                for y in range(8):
                    strips.append((rows[half * 8 + y] >> (ncol * 8 - (cidx + 1) * 8)) & 0xFF)
                bat[(top + half, TEXT_COL0 + cidx)] = PAL | n
                n += 1
    assert n <= 0x6B0, "엔진 글자 타일 칸(0x660~0x6AF)을 넘는다"
    return bytes(strips), bat


if __name__ == "__main__":
    t, b = make_window("라이아스", "안녕히 주무셨사옵니까, 세리오스님.")
    print(len(t), "B 압축 ·", len(expand(t)), "B 타일 ·", len(b), "BAT")
