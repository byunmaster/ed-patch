"""HUD 상태 라벨(C4 · 방어 표시) — 가나 도트 타일을 한글 8×8 로 다시 굽는다.

파티 칸 4째 줄(EP 줄)은 상태가 걸리면 「남다 33」 대신 **상태 라벨 프레임**을 낸다. 라벨은 대사 글자가 아니라
HUD 전용 2bpp 8×8 타일이고(BG2, 글자코드 표 `$03:F3EC` 에 없다), 프레임 일곱이 `$00:9AC7` 부터 16B 씩 놓인다
(2026-10-09 실기 — 방어를 고르면 일본어 「まもる」가 떴다. 기존 게이트는 글자 코드만 봐서 못 잡았다).

  프레임        원본 라벨        타일(원본)
  $00:9AC7     きぜつ           3A 3B 3C
  $00:9AD7     どく             2E 1F8
  $00:9AE7     ねる             39 38
  $00:9AF7     こんらん         3D 1F6 3E 1F6
  $00:9B07     ちんもく         1F5 1F6 1F7 1F8
  $00:9B17     かえす           1F9 2C 2D
  $00:9B27     まもる           2F 1F7 38

타일 그림은 롬 `$18:F16C`(타일 2C~2F)·`$18:F1AC`(38~3F)·`$18:F27C`(1F5~)에 16B 씩 연속이다 — 원본 타일을 VRAM 에서 읽어
롬에서 유일하게 찾아 확인했다. 한글 라벨 열둘이 열여섯 타일 안에 들어가므로 **프레임의 타일 워드만 새로 배정**한다
(라벨마다 팔레트 비트는 원본 그대로 — 빨강 계열 다섯 · 노랑 계열 둘).

표기는 PS1 정본(`patch_hud_names.STATUS_ROW1` · 마스터 최종 확인 09-13)을 따른다: 독 · 잠 · 혼란 · 침묵 · 반사 · 방어 ·
기절. PS1 은 한 칸이라 한 글자(묵·혼·반·수)지만 이쪽은 프레임이 두 칸 이상이라 낱말로 쓴다.
도안 정본은 `textmap/hud_status_8x8.txt`(`--dump` 로 Galmuri7 에서 뽑는다, 이름 도안 `hud_names_8x8.txt` 와 같은 방식).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import hud_names

DOTS = common.GAME_DIR / "textmap" / "hud_status_8x8.txt"
FONT = hud_names.FONT
FRAME_BASE = 0x009AC7
FRAME_WORDS = 8
# (한글 라벨, 원본 프레임 16B hex) — 프레임 차례대로. 원본 라벨(가나)은 위 표에만 적는다(게임 폴더에 JP→KR 표를 두지 않는다).
FRAMES = [
    ("기절", "3a083b083c0827002700270027002700"),
    ("독", "2e08f809270027002700270027002700"),
    ("잠", "39083808270027002700270027002700"),
    ("혼란", "3d08f6093e08f6092700270027002700"),
    ("침묵", "f509f609f709f8092700270027002700"),
    ("반사", "f90d2c0c2d0c27002700270027002700"),
    ("방어", "2f0cf70d380c27002700270027002700"),
]
# 한글 글자 → HUD 타일 번호(프레임이 쓰던 열여섯 중 열둘)
TILE_OF = {
    "기": 0x2C,
    "절": 0x2D,
    "독": 0x2E,
    "잠": 0x2F,
    "혼": 0x38,
    "란": 0x39,
    "침": 0x3A,
    "묵": 0x3B,
    "반": 0x3C,
    "사": 0x3D,
    "방": 0x3E,
    "어": 0x1F5,
}


def TILE_SRC(t: int) -> int:
    """HUD 타일 번호 → 그 그림이 있는 롬 자리(VRAM 에서 읽어 롬에서 유일하게 찾은 값, 2026-10-09)."""
    if 0x2C <= t <= 0x2F:
        return 0x18F16C + 16 * (t - 0x2C)
    if 0x38 <= t <= 0x3E:
        return 0x18F1AC + 16 * (t - 0x38)
    if 0x1F5 <= t <= 0x1F9:
        return 0x18F27C + 16 * (t - 0x1F5)
    raise ValueError(f"모르는 HUD 상태 타일 ${t:03X}")


def chars() -> list[str]:
    out: list[str] = []
    for kr, _w in FRAMES:
        for c in kr:
            if c not in out:
                out.append(c)
    return out


def frame_words(kr: str, orig: bytes) -> bytes:
    """원본 프레임의 팔레트 비트를 살려 타일 워드만 한글로 바꾼다. 남는 칸은 빈 칸(`$0027`)."""
    attr = orig[1] & 0xFC  # 윗바이트에서 타일 상위 비트(0~1)만 뺀다 — 팔레트·우선순위는 원본 그대로
    words = []
    for c in kr:
        t = TILE_OF[c]
        words.append(((attr << 8) | t).to_bytes(2, "little"))
    words += [b"\x27\x00"] * (FRAME_WORDS - len(words))
    return b"".join(words)


def dump() -> str:
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
        raise SystemExit(f"{DOTS.name} 의 글자가 상태 라벨 글자와 다르다: {''.join(out)}")
    return out


def bake(out: bytearray, rom: bytes) -> dict:
    dots = load()
    for n, (kr, orig_hex) in enumerate(FRAMES):
        fo = common.snes2off(FRAME_BASE + 2 * FRAME_WORDS * n)
        orig = bytes.fromhex(orig_hex)
        if bytes(rom[fo : fo + 2 * FRAME_WORDS]) != orig:
            raise SystemExit(
                f"HUD 상태 프레임 {kr} 이 예상과 다르다: {bytes(rom[fo : fo + 16]).hex()}"
            )
        out[fo : fo + 2 * FRAME_WORDS] = frame_words(kr, orig)
    for c, t in TILE_OF.items():
        so = common.snes2off(TILE_SRC(t))
        tb = hud_names.tile_bytes(dots[c])
        out[so : so + 16] = tb
        if hud_names.glyph_of(bytes(out[so : so + 16])) != dots[c]:
            raise SystemExit(f"HUD 상태 {c} 되읽기가 도트 파일과 다르다")
    return {"라벨": [kr for kr, _w in FRAMES], "글자": len(dots)}


def patch_ranges() -> list[tuple[int, int]]:
    base = common.snes2off(FRAME_BASE)
    r = [(base, base + 2 * FRAME_WORDS * len(FRAMES))]
    for t in TILE_OF.values():
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
