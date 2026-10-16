"""장 제목 띠 — 패키지마다 들어 있는 6줄 덩이(메시지 표 항목 1~13)를 정본의 장 제목으로 바꾼다.

원문: `{a0}…{a0} 序章 {a0} 平和な日々 {a0}…` 꼴의 6줄(서장 · 제1~4장 · 종장). `a0` = 한 칸 공백, **줄 폭은 14칸** — 모든 줄이
왼쪽 공백 + 글 + 오른쪽 공백으로 14칸을 채워 가운데에 앉는다(실측: 서장 3+8+3 · 제1장 2+10+2 · 종장 2+11+1).
글리프 = 한 칸(한글·한자 같은 12px, 단일 바이트 가나도 한 칸). **공백은 두 가지다** — `a0`(한 칸 12px · 여백용)과 `60`(4px · 낱말 사이 반각).
문안은 **정본**(`shared/canon` `chapter` 범주 — 장 제목 · `@번호`)에서 읽는다. 이 모듈엔 표가 없다(마스터 10-08).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon
import jptext

BAND_CELLS = 14
CELL_PX = 12  # 글리프·`a0` 한 칸
SPACE_PX = 4  # 게임의 공백 `60` 은 4px 만 간다(반각 — translation-rules 1-6 · pce-ed1 의 반각 공백과 같은 폭)
BAND_PX = BAND_CELLS * CELL_PX
PAD = 0xA0  # 가운데 맞춤 여백(한 칸)
SPACE = 0x60  # 낱말 사이(반각)
KEY_LINES = 6


def is_chapter_chunk(d: bytes) -> bool:
    lines = d.split(b"\x00")
    return len(lines) == KEY_LINES + 1 and all(l[:2] == b"\xa0\xa0" for l in lines[:KEY_LINES])


def _entry(jp_line: str) -> tuple[str, str]:
    """원문 줄 → (번호 문안, 제목 문안) — 정본 `chapter` 범주에서."""
    text = jp_line.replace("　", "")
    ch = canon.table("chapter", "ed2")
    for key in ch:
        if "@" in key or key not in text:
            continue
        return ch[key + "@번호"], ch[key]
    raise KeyError(f"정본 장 제목에 없는 줄: {jp_line!r}")


def _pad(px: int) -> bytes:
    """여백 px(4의 배수) → `a0`(12px) 최대한 + `60`(4px) 나머지."""
    n12, rest = divmod(px, CELL_PX)
    return bytes([PAD]) * n12 + bytes([SPACE]) * (rest // SPACE_PX)


def lines(orig: bytes, tab) -> list[bytes]:
    """원문 덩이 → 새 줄 바이트 목록(끝 `00` 제외). `tab` = `font.GlyphTable`. 줄 폭은 px 로 14칸(168px)에 맞춘다."""
    out = []
    for raw in orig.split(b"\x00")[:KEY_LINES]:
        num, title = _entry(jptext.decode(raw))
        disp = f"{num} {title}"
        w_px = sum(SPACE_PX if c == " " else CELL_PX for c in disp)
        if w_px > BAND_PX:
            raise ValueError(f"장 제목이 띠({BAND_PX}px)를 넘는다: {disp!r} {w_px}px")
        extra = BAND_PX - w_px
        left = (extra // 2) // SPACE_PX * SPACE_PX
        out.append(_pad(left) + tab.enc(disp, space=SPACE) + _pad(extra - left))
    return out


def edit(orig: bytes, tab) -> bytes:
    """덩이 전체(줄마다 `00` 으로 끝)를 새로 만든다."""
    return b"".join(l + b"\x00" for l in lines(orig, tab))
