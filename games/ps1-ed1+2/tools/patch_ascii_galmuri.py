#!/usr/bin/env python3
"""반각 영문·숫자(A–Z a–z 0–9) 글리프를 Galmuri(대사 글꼴 계열)로 굽는다 — 마스터 2026-10-10.

PS1 원판 반각 라틴은 얇은 8×11 도트라 한글·전각 Ａ~Ｚ(Galmuri)와 결이 달랐다(「Ｅ Ｐ 1」 이
벌어져 보인 까닭). 반각 전진폭은 6px 이라 Galmuri11 본체(숫자 7px 잉크)는 못 들어가고,
**GalmuriMono11**(전진 6 · 잉크 5 · 높이 10)이 같은 계열에서 6px 칸에 맞는 판이다.

표는 `patch_hangul_glyph_table` 과 같은 자리다 — 8×11 · 행당 1B · MSB=왼쪽 · 글리프당 11B ·
주소 = base + (코드−0x21)×11. ED.EXE·ED2.EXE 두 벌(사본이 둘). 잉크는 열 0~4(5px)만 쓰고
열 5 는 자간으로 비운다.

⚠ 소문자 내림(g j p q y)은 Mono11 이 2행이라 11행 칸을 넘는다 — 줄기 한 행을 덜어 1행으로 맞춘다.
⚠ 쓰기 전 원본 지문(62자 연결 sha1)을 대조해 이중 적용·주소 어긋남을 막는다.
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import extract, write_user_data
from hangul_font import REPO_ROOT, load_bdf
from patch_hangul_glyph_table import EXES, IMG

BDF = os.path.join(REPO_ROOT, "shared", "fonts", "GalmuriMono11.bdf")
CODES = (*range(0x30, 0x3A), *range(0x41, 0x5B), *range(0x61, 0x7B))
TOP_DY = -3  # ascent 14 → 대문자·숫자 윗줄이 0행(밑줄이 9행)
ROWS = 11

# 원판 연결 지문 — 코드 순서대로 11B×62 의 sha1. 두 실행파일이 같다(실측).
ORIG_SHA1 = "40247baa8f214cf8ca20c6a53a5c81f8be92ee5b"


def _idx(code):
    return code - 0x21


def glyph(font, asc, code):
    w, h, xo, yo, rows = font[code]
    nbits = ((w + 7) // 8) * 8
    top = asc - (yo + h) + TOP_DY
    grid = [0] * ROWS + [0] * 4  # 넘침 여유
    for r, v in enumerate(rows):
        y = top + r
        if 0 <= y < len(grid):
            # BDF 행(왼쪽=MSB) → 8비트 MSB=왼쪽, xo 만큼 오른쪽
            grid[y] = ((v >> (nbits - 8)) if nbits >= 8 else (v << (8 - nbits))) >> xo & 0xFF
    used = [r for r in range(len(grid)) if grid[r]]
    if used and used[-1] >= ROWS:
        # 내림 2행 → 1행: 줄기 행을 하나 덜어 낸다(이웃과 같은 행 우선, 없으면 9행)
        cand = [r for r in (8, 9, 10) if grid[r] == grid[r + 1] or grid[r] == grid[r - 1]]
        cut = cand[0] if cand else 9
        del grid[cut]
        grid.append(0)
    assert not any(grid[ROWS:]), f"0x{code:02X} 11행 초과"
    assert all(b & 0x07 == 0 for b in grid[:ROWS]), f"0x{code:02X} 열 5~7 잉크"
    return bytes(grid[:ROWS])


def bake():
    font, asc = load_bdf(BDF)
    return {c: glyph(font, asc, c) for c in CODES}


def _span(buf, base):
    return b"".join(bytes(buf[base + _idx(c) * 11 : base + _idx(c) * 11 + 11]) for c in CODES)


def apply():
    new = bake()
    want = b"".join(new[c] for c in CODES)
    total = 0
    for exe, (lba, size, base) in EXES.items():
        buf = bytearray(extract(lba, size, path=IMG))
        cur = _span(buf, base)
        if cur == want:
            print(f"  {exe}: 반각 영문·숫자 이미 갈무리")
            continue
        assert hashlib.sha1(cur).hexdigest() == ORIG_SHA1, (
            f"{exe} 반각 영문·숫자 표 원본 불일치 — 다른 패치가 먼저 건드렸거나 주소 어긋남"
        )
        for c in CODES:
            off = base + _idx(c) * 11
            buf[off : off + 11] = new[c]
        with open(IMG, "r+b") as f:
            write_user_data(f, lba, bytes(buf), label=f"반각 영문·숫자 갈무리({exe})")
        print(f"  {exe}: 반각 영문·숫자 {len(CODES)}자 구움")
        total += len(CODES)
    return total


def preview(text):
    g = bake()
    lines = [""] * ROWS
    for ch in text:
        rows = g[ord(ch)]
        for r in range(ROWS):
            lines[r] += "".join("#" if rows[r] >> (7 - c) & 1 else "." for c in range(6))
    return "\n".join(lines)


if __name__ == "__main__":
    if "--preview" in sys.argv:
        print(preview("EP 0123456789 ABCMW".replace(" ", "")))
        print(preview("abcdefghijklm"))
        print(preview("nopqrstuvwxyz"))
        sys.exit(0)
    sys.exit(0 if apply() is not None else 1)
