"""sfc-ed2 한글 글리프 — 갈무리 11px BDF 를 12×12(`font.py` 형식: 두 줄 = 3바이트 big-endian 12비트×2)로 굽는다.

잉크는 11×11 을 왼쪽 위에 둔다 — 12번째 줄·칸은 비워 둔다(게임이 오른쪽·아래로 그림자(2번 색)를 합성한다, `font.py` 머리말).
지금은 시험 문안(트램펄린 확인)용 최소 구현이다 — 어느 글자가 필요한지는 번역 정본이 정한다(다음 라운드).
"""

import functools
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

BDF = common.ROOT / "shared" / "fonts" / "Galmuri11.bdf"


@functools.lru_cache(maxsize=1)
def _bdf() -> dict[int, tuple[list[int], int, int, int, int]]:
    """코드포인트 → (행 비트 — 폭 w 로 오른쪽 정렬, w, h, xoff, yoff). BBX 의 오프셋이 있어야 마침표·쉼표·말줄임표가 바닥/가운데에 앉는다."""
    out, cur, rows, bb = {}, None, None, None
    for line in BDF.read_text(encoding="latin1").splitlines():
        if line.startswith("ENCODING"):
            cur = int(line.split()[1])
        elif line.startswith("BBX"):
            bb = tuple(map(int, line.split()[1:]))
        elif line.startswith("BITMAP"):
            rows = []
        elif line.startswith("ENDCHAR"):
            if cur is not None and rows is not None and bb and bb[0] <= 11 and bb[1] <= 11:
                w = bb[0]
                out[cur] = ([int(r, 16) >> (len(r) * 4 - w) for r in rows], w, bb[1], bb[2], bb[3])
            cur, rows = None, None
        elif rows is not None and re.fullmatch(r"[0-9A-Fa-f]+", line.strip()):
            rows.append(line.strip())
    return out


# 갈무리의 「…」 는 가운데(yoff 5)에 있지만 번역 규칙 1-3 은 **점이 바닥**이다 — 바닥(yoff 0)에 앉힌다
YOFF_OVERRIDE = {0x2026: 0}

# 글리프 전체를 셀 안에서 오른쪽으로 민 열 수 — 출력기가 만드는 윤곽(그림자)은 잉크 왼쪽 1열이 필요한데 셀 0열 잉크는 그 열이 칸 밖이라 잘린다(마스터 10-13 「맨 왼쪽 1px」).
# 잉크 11열(0~10)이 1~11열로 앉아 자간은 그대로고, 줄 끝 글자의 오른쪽 윤곽 1열이 대신 칸 밖으로 나간다.
SHIFT_X = 1


def _ellipsis12() -> bytes:
    """「…」 — 점 셋을 이 기종 마침표(반각 「.」 = 2×2 네모, patches.HALF_GLYPHS)와 같은 모양·크기로, 바닥(잉크 9~10행)에 앉힌다(번역 규칙 1-3, 마스터 11-15 「… 도 마침표 모양으로」 → 「전 기종」).
    점 간격 4(갈무리와 같음)·칸 안 좌우 여백 1 씩 — 점만 2×2 가 된다."""
    rows = [0] * 12
    for y in (9, 10):
        rows[y] = (0b11 << 9) | (0b11 << 5) | (0b11 << 1)  # 열 1~2 · 5~6 · 9~10 (칸 0~11 에서 좌우 여백 1 씩)
    out = bytearray()
    for k in range(0, 12, 2):
        out += ((rows[k] << 12) | rows[k + 1]).to_bytes(3, "big")
    return bytes(out)


def glyph12(ch: str) -> bytes:
    """글자 하나 → 18바이트 글리프(11×11 잉크, 왼쪽 위 — BBX 오프셋대로 앉힌다: 아랫줄 = 기준선)."""
    if ch == "…":
        return _ellipsis12()
    g = _bdf().get(ord(ch))
    if g is None:
        raise KeyError(f"갈무리에 없는 글자: {ch!r}")
    bits, w, h, xo, yo = g
    yo = YOFF_OVERRIDE.get(ord(ch), yo)
    rows = [0] * 12
    top = 11 - (yo + h)  # 11줄 칸(0~10)에서 첫 잉크줄
    for i, r in enumerate(bits):
        y = top + i
        if 0 <= y < 12:
            sh = 12 - xo - SHIFT_X - w  # 오른쪽으로 SHIFT_X 열 밀어 앉힌다(왼쪽 윤곽 열 확보)
            rows[y] = (r << sh) & 0xFFF if sh >= 0 else (r >> -sh) & 0xFFF
    out = bytearray()
    for k in range(0, 12, 2):
        v = (rows[k] << 12) | rows[k + 1]
        out += v.to_bytes(3, "big")
    return bytes(out)


if __name__ == "__main__":
    import font

    for ch in "안녕":
        g = glyph12(ch)
        print(ch)
        for k in range(0, 18, 3):
            v = int.from_bytes(g[k : k + 3], "big")
            for r in ((v >> 12) & 0xFFF, v & 0xFFF):
                print("".join("#" if (r >> (11 - x)) & 1 else "." for x in range(12)))


# 콘덴스드 반각 글리프 — HUD 「큐베라～프로스」(박스 72px 에 12px 글자 6개+「～」 = 84px 가 안 든다, 마스터 11-10 「여기만 갈무리 콘덴스드」).
COND_BDF = common.ROOT / "shared" / "fonts" / "Galmuri11-Condensed.bdf"


def cond_half(ch: str) -> bytes:
    """콘덴스드 글자 → 반각 8×16 글리프 16B(잉크 오른쪽 1열 밀기 — 윤곽 열, 행 14 가 기준선 아래)."""
    t = COND_BDF.read_text(encoding="latin1")
    m = re.search(r"ENCODING %d\n(.*?)ENDCHAR" % ord(ch), t, re.S).group(1)
    w, h, xo, yo = map(int, re.search(r"BBX (.*)", m).group(1).split())
    rows = [int(x, 16) >> (len(x) * 4 - w) for x in re.search(r"BITMAP\n(.*)", m, re.S).group(1).split()]
    g = [0] * 16
    top = 14 - (yo + h)
    for i, r in enumerate(rows):
        g[top + i] = ((r << (8 - w - xo)) & 0xFF) >> 1
    return bytes(g)
