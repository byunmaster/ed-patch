#!/usr/bin/env python3
"""시험 전용 — 인용부 「」 『』 를 반각 코드 0xA2/0xA3 · 0xA4/0xA5 로 내는 마스터 도안 A판(10-26, 『』 는 10-27 v2 — 가로 5칸).

제품 빌드는 이 경로를 쓰지 않는다(`ED_KAGI_HALF=1` 일 때만 켜지고 `ED_BUILD_TAG=test-…` 로 굽는다).
도안 정본은 쌍마다 12×11 한 장 — 여는 괄호는 0~5열, 」 는 6~11열, 진행 6px. 반각 칸(8×11, 1행 1바이트, MSB=왼쪽)에
앉히려고 6열씩 잘라 쓴다. 반각 표 주소 = base + 색인×11 인데 **색인이 구간마다 다르다** —
0x21~0x7E 는 코드−0x21(`patch_ascii_galmuri`), 0xA1~0xA5 는 **코드−0x40**(엔진 0x800AE4B8, 원본 ｡｢｣､･ 자리).
처음에 0xA2~0xA5 도 코드−0x21 로 써서 엉뚱한 칸(색인 129~132)을 덮고 원본 ｢｣ 가 그대로 나왔다(10-27 화면에서 발견).
"""

import os

from common import extract, write_user_data
from patch_hangul_glyph_table import EXES, IMG

ENABLED = os.environ.get("ED_KAGI_HALF") == "1"
CODES = {"「": 0xA2, "」": 0xA3, "『": 0xA4, "』": 0xA5}

GRIDS = {
    0xA2: (
        "####........",
        "#...........",
        "#...........",
        "#...........",
        "#........#..",
        "#........#..",
        "#........#..",
        ".........#..",
        ".........#..",
        ".........#..",
        "......####..",
    ),
    0xA4: (
        "#####.......",
        "#...#.......",
        "#.###.......",
        "#.#.........",
        "#.#.....###.",
        "#.#.....#.#.",
        "###.....#.#.",
        "........#.#.",
        "......###.#.",
        "......#...#.",
        "......#####.",
    ),
}


# ED2.EXE 의 「」의 주문은 봉인되어 있다」 앞쪽 — 엔진 원문의 **단독 「 한 글자 문자열**(전각 81 75)이라 우리 문안 인코더를
# 안 탄다. 안 맞추면 「는 전각·」는 반각으로 섞인다(ED.EXE 쪽 둘은 items_battle 「 로 인코더를 타서 이미 반각).
# 파일 오프셋, 코드가 lui/addiu 로 가리키는 것을 확인했다(10-27).
ED2_OPEN_QUOTE = (0xD49F4, 0xD4A34)


def sjis(ch):
    """전투·시스템 문자열 인코더용 — 시험 경로가 켜져 있으면 「」 만 반각 코드 1바이트로, 아니면 SJIS 그대로."""
    if ENABLED and ch in ("「", "」"):
        return bytes([CODES[ch]])
    return ch.encode("shift_jis")


def rows(code):
    """코드 → 11바이트. 쌍의 앞 코드(0xA2·0xA4)는 0~5열, 뒤 코드는 6~11열."""
    base, side = (code, 0) if code in GRIDS else (code - 1, 1)
    out = bytearray()
    for r in GRIDS[base]:
        cell = r[side * 6 : side * 6 + 6]
        out.append(int(cell.ljust(8, ".").replace("#", "1").replace(".", "0"), 2))
    return bytes(out)


# ── 따옴표 S 안(마스터 10-28 — 새턴 I·II 와 같은 꼴, 「ps1 12 수정은 핫픽스 대상」) ─────────────────────────
# `ED_QUOTE_S=1` 일 때만. 방향 없는 반각 " ' 한 글자로 열고 닫는다 — 반각 표 0x22·0x27 칸을 가는 두 획·한 획으로
# 바꾸고(" = 50 50 50 · ' = 20 20 20, 열 1·3 / 열 2, 3행, 행 0 시작), 대사의 여닫는 따옴표 “ ” ‘ ’ 를 그 코드로 낸다.
# 폭은 지금 전용 글리프와 같은 반각(0.5)이라 조판이 안 바뀐다. 분열 몬스터 접미(Ａ′·Ａ″)도 같은 코드라 같이 바뀐다.
QUOTE_S = os.environ.get("ED_QUOTE_S") == "1"
QUOTE_S_MAP = {"“": 0x22, "”": 0x22, "‘": 0x27, "’": 0x27}
QUOTE_S_GLYPHS = {0x22: bytes.fromhex("5050500000000000000000"), 0x27: bytes.fromhex("2020200000000000000000")}


def apply_quote():
    if not QUOTE_S:
        return 0
    for exe, (lba, size, base) in EXES.items():
        buf = bytearray(extract(lba, size, path=IMG))
        for code, g in QUOTE_S_GLYPHS.items():
            off = base + (code - 0x21) * 11
            buf[off : off + 11] = g
        with open(IMG, "r+b") as f:
            write_user_data(f, lba, bytes(buf), label=f"시험 따옴표 S 안({exe})")
        print(f"  {exe}: 시험 따옴표 S 안(\" ' 반각 두 획·한 획) 구움")
    return 2


def apply():
    if not ENABLED:
        return 0
    want = {c: rows(c) for c in CODES.values()}
    for exe, (lba, size, base) in EXES.items():
        buf = bytearray(extract(lba, size, path=IMG))
        for code, g in want.items():
            off = base + (code - 0x40) * 11
            buf[off : off + 11] = g
        if exe == "ED2.EXE":
            for off in ED2_OPEN_QUOTE:
                assert bytes(buf[off - 1 : off + 3]) == b"\x00\x81\x75\x00", f"ED2.EXE 0x{off:X} 단독 「 아님"
                buf[off : off + 2] = bytes([CODES["「"], 0x00])
        with open(IMG, "r+b") as f:
            write_user_data(f, lba, bytes(buf), label=f"시험 반각 「」({exe})")
        print(f"  {exe}: 시험 반각 「」 구움")
    return 2


if __name__ == "__main__":
    for ch, c in CODES.items():
        print(ch, " ".join(f"{b:02X}" for b in rows(c)))
