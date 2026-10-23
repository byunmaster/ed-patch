"""HUD 판의 「アト」 라벨(경험치 표시 = 남다)을 마스터 도트로 바꾼다.

라벨 두 타일(풀린 타일 38·39 = 16×8)은 HUD 판 타일 묶음(데이터 트랙 rel 186 +1405, 압축 5,083B → 풀린 6,304B, `hudlz`)에 있다.
도트는 **pce-ed1 의 마스터 도트 `games/pce-ed1/assets/graphics/namda.txt`(8줄×16칸 #/.)를 그대로 읽는다**(마스터 10-17 「ed1과 똑같이」 — 복사본을 두지 않고,
도트 모양은 안 바꾸고 색 번호만 ed2 HUD 팔레트에 맞춘다: 0열 = 판 테두리(원본 색 유지) · 바탕 1 · 글자 = 원본 라벨의 글자색).
새 압축본은 원본 압축 길이(5,083B) 안에 들어야 한다(뒤 묶음 자리를 안 넘는다).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import hudlz

REL, OFF = 186, 1405
N_OUT = 6304  # 풀린 바이트(해제 끝 포인터가 원본 5,083B 와 정확히 맞는 값 — 실측)
LEN = 5083  # 원본 압축 길이
TILE_L, TILE_R = 38, 39
NAMDA = Path(__file__).resolve().parents[3] / "games/pce-ed1/assets/graphics/namda.txt"
BG = 1  # 판 바탕 색 번호(원본 라벨 타일의 지배색)


def tile_px(tile: bytes) -> list[list[int]]:
    """VRAM 타일 32B(행마다 p0·p1, 16B 뒤 p2·p3) → 8×8 색 번호."""
    rows = []
    for r in range(8):
        ps = [tile[2 * r], tile[2 * r + 1], tile[16 + 2 * r], tile[17 + 2 * r]]
        rows.append([sum(((ps[p] >> (7 - x)) & 1) << p for p in range(4)) for x in range(8)])
    return rows


def px_tile(rows: list[list[int]]) -> bytes:
    out = bytearray(32)
    for r in range(8):
        for p in range(4):
            b = 0
            for x in range(8):
                b |= ((rows[r][x] >> p) & 1) << (7 - x)
            out[2 * r + (p & 1) + (16 if p >= 2 else 0)] = b
    return bytes(out)


def load_dots(path: Path = NAMDA) -> list[list[int]]:
    """마스터 도트판(`#`/`.`) → 8×16 의 0/1. 0열은 판 테두리 자리라 비어 있어야 한다."""
    rows = [ln.rstrip("\n") for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(rows) == 8 and all(len(r) == 16 and set(r) <= {"#", "."} for r in rows), f"{path}: 8줄×16칸 #/. 가 아니다"
    a = [[1 if c == "#" else 0 for c in r] for r in rows]
    assert not any(r[0] for r in a), f"{path}: 0열(테두리)에 점이 있다"
    return a


def ink_color(left: list[list[int]], right: list[list[int]]) -> int:
    """원본 라벨의 글자색 — 테두리(0열)·바탕을 뺀 가장 많은 색."""
    cnt: dict[int, int] = {}
    for r in range(8):
        for x in range(8):
            for c in (left[r][x] if x else None, right[r][x]):
                if c is not None and c != BG:
                    cnt[c] = cnt.get(c, 0) + 1
    return max(cnt, key=cnt.get)


def label_tiles(orig_tiles: bytes, dots: list[list[int]]) -> tuple[bytes, bytes]:
    """원본 타일 38·39(64B) → 도트를 그린 새 타일 둘."""
    L = tile_px(orig_tiles[:32])
    R = tile_px(orig_tiles[32:64])
    ink = ink_color(L, R)
    a = [L[r] + R[r] for r in range(8)]
    for r in range(8):
        for x in range(1, 16):
            a[r][x] = ink if dots[r][x] else BG
    return px_tile([row[:8] for row in a]), px_tile([row[8:] for row in a])


def original() -> tuple[bytes, bytes]:
    """(풀린 원본 6,304B, 원본 압축 5,083B)."""
    sec = bytes(common.track_data(REL, 8))
    dec, end = hudlz.decode(sec, OFF, N_OUT)
    assert end - OFF == LEN, f"압축 길이 {end - OFF}B — 원본이 아니다?"
    return dec, sec[OFF:end]


def new_stream(dots: list[list[int]] | None = None) -> bytes:
    dec, _comp = original()
    t38, t39 = label_tiles(dec[TILE_L * 32 : (TILE_R + 1) * 32], dots or load_dots())
    new = bytearray(dec)
    new[TILE_L * 32 : TILE_L * 32 + 32] = t38
    new[TILE_R * 32 : TILE_R * 32 + 32] = t39
    enc = hudlz.encode(bytes(new))
    assert len(enc) <= LEN, f"새 압축본 {len(enc)}B > 원본 {LEN}B"
    back, _e = hudlz.decode(enc + bytes(8), 0, N_OUT)
    assert back == bytes(new), "압축 왕복이 다르다"
    return enc


def apply(w) -> None:
    """빌드 쓰기 — `build.Writer.put` (거울 이중 쓰기 · 기대 원본 사전조건 포함)."""
    enc = new_stream()
    _dec, comp = original()
    w.put(REL * common.USER + OFF, enc, comp[: len(enc)], "HUD 판 타일(「남다」 라벨)")
    print(f"  HUD 판: 라벨 「남다」 마스터 도트 · 압축 {len(enc)}B / 원본 {LEN}B")
