"""장 제목 띠 — 패키지마다 들어 있는 6줄 덩이(메시지 표 항목 1~13)를 정본의 장 제목으로 바꾼다.

원문: `{a0}…{a0} 序章 {a0} 平和な日々 {a0}…` 꼴의 6줄(서장 · 제1~4장 · 종장). `a0` = 한 칸 공백, **줄 폭은 14칸** — 모든 줄이
왼쪽 공백 + 글 + 오른쪽 공백으로 14칸을 채워 가운데에 앉는다(실측: 서장 3+8+3 · 제1장 2+10+2 · 종장 2+11+1).
글리프 = 한 칸(한글·한자 같은 12px, 단일 바이트 가나도 한 칸). **공백은 두 가지다** — `a0`(한 칸 12px · 여백용)과 `60`(4px · 낱말 사이 반각).
문안은 **정본**(`shared/canon` `chapter` 범주 — 장 제목 · `@번호`)에서 읽는다. 이 모듈엔 표가 없다(마스터 10-08).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon
import font
import jptext

BAND_CELLS = 14
CELL_PX = 12  # 글리프·`a0` 한 칸
TITLE_INK_END = 132  # 디버그 마을(`cells`) — 같은 띠 위에 그려지는 「ETC. TEST」 줄의 글이 끝나는 곳(11칸). 그 뒤 칸은 안 덮어 그려 앞 줄의 글 조각이 남는다(11-09 실화면 「!」 조각)
SPACE_PX = 4  # 게임의 공백 `60` 은 4px 만 간다(반각 — translation-rules 1-6 · pce-ed1 의 반각 공백과 같은 폭)
BAND_PX = BAND_CELLS * CELL_PX
PAD = 0xA0  # 가운데 맞춤 여백(한 칸)
SPACE = 0x60  # 안 그려지는 4px 공백(양 끝 짜투리용)
ASCII_SP = 0x20  # 반각 ASCII 공백 — 8px 칸을 **그려서** 지운다(엔진의 반각 글자 폭, `font.NARROW_PX`). 낱말 사이(마스터 11-10 「공백 반각」)
KEY_LINES = 6
BAND_SLACK_PX = 8  # 화면 띠 안쪽 176px 에서 14칸(168px)이 왼쪽에 붙고 남는 폭(실측 11-08 — 띠 안쪽 x 34~209, 14칸 시작 x 34)


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


def _pad_left(px: int) -> bytes:
    """왼쪽 여백 — 4px 짜투리 `60`(안 그려진다)은 띠 맨 왼쪽 끝 8px 안에만 둔다(어느 제목도 그 칸엔 잉크가 없어 앞 제목 잔상이 안 남는다), 나머지는 그려서 지우는 `a0`."""
    n12, rest = divmod(px, CELL_PX)
    return bytes([SPACE]) * (rest // SPACE_PX) + bytes([PAD]) * n12


def _pad_right(px: int) -> bytes:
    """오른쪽 여백 — `a0` 먼저, 4px 짜투리는 맨 오른쪽 끝에(`_pad_left` 와 같은 까닭)."""
    return _pad(px)


def _bearing(ch: str) -> tuple[int, int]:
    """글리프 칸(12px) 안 잉크의 (왼쪽 빈틈, 오른쪽 빈틈) px — 칸 밖 글자(원판 전각 숫자 따위 글꼴에 없는 글자)는 (0, 0)."""
    try:
        g = font.glyph(ch)
    except (KeyError, ValueError):
        return 0, 0
    cols = [any(int.from_bytes(g[2 * r : 2 * r + 2], "big") >> (15 - c) & 1 for r in range(12)) for c in range(12)]
    ink = [i for i, v in enumerate(cols) if v]
    return ink[0], 11 - ink[-1]


def chapter_gap(kr: str) -> str:
    """장 번호–제목 사이는 12px(원판 전각 한 칸 = 공백 `60`(4px) 셋) — 정본 값은 공백 둘(8px)이라 여기서 맞춘다(번역 규칙 2-8, 마스터 11-03)."""
    return re.sub(r"(?m)^((?:제[０-９]+|서|종)장)  (?=\S)", r"\1   ", kr)


def lines(orig: bytes, tab, cells: bool = False) -> list[bytes]:
    """원문 덩이 → 새 줄 바이트 목록(끝 `00` 제외). `tab` = `font.GlyphTable`. 줄 폭은 px 로 14칸(168px)에 맞춘다."""
    out = []
    for raw in orig.split(b"\x00")[:KEY_LINES]:
        num, title = _entry(jptext.decode(raw))
        # 번호–제목 간격 = 원판대로 `a0` 12px 한 칸(규칙 1-4, 마스터 10-13 「장띠 번호와 제목간격은 원판 따르자」)
        # 낱말 사이는 `60`(4px 반각 — 마스터 11-10 「공백이 전각인데 반각으로」). 그리지 않고 건너뛰는 칸이라 **다른 장 제목이 앞에 떠 있던 띠에 갈아 끼울 때만** 그 칸에 앞 제목 획이 비친다(장 변수를 직접 바꿔 갈아 끼우는 디버그 경로 — 6줄 모두 비치지 않는 자리는 가운데에서 18px 이상 벗어나야 나온다, 11-10 계산).
        # 4px 짜투리는 띠 맨 양 끝에만 둔다(양 끝 여백은 어느 제목에서도 비어 있다).
        gap = lambda s: sum(font.adv(c) if c != " " else font.NARROW_PX for c in s)  # noqa: E731
        w_px = gap(num) + CELL_PX + gap(title)
        if w_px > BAND_PX:
            raise ValueError(f"장 제목이 띠({BAND_PX}px)를 넘는다: {num!r} {title!r} {w_px}px")
        extra = BAND_PX - w_px
        # 가운데 맞춤 — 화면 띠 안쪽(176px)의 잉크 가운데에 맞춘다. 잉크 쏠림 = 2·left − extra − 8 + (첫 글자 왼쪽 빈틈) − (끝 글자 오른쪽 빈틈), left 는 4px 격자에서 |쏠림| 이 가장 작은 값(마스터 11-08 「장 제목도 가운데정렬」 — 실측 제1·2·4장 잉크 왼 20 · 오른 25 → 24 · 21)
        bl, br = _bearing(num[0])[0], _bearing(title[-1])[1]
        left = min(range(0, (min(extra, max(0, TITLE_INK_END - w_px)) if cells else extra) + 1, CELL_PX if cells else SPACE_PX), key=lambda x: (abs(2 * x - extra - BAND_SLACK_PX + bl - br), x))  # 가장 가까운 칸, 같을 때만 왼쪽(마스터 11-09 2-8 개정)
        words = title.split(" ")
        out.append(
            _pad_left(left)
            + tab.enc(num, space=PAD)
            + bytes([PAD])
            + b"".join(tab.enc(w, space=SPACE) + (bytes([ASCII_SP]) if k < len(words) - 1 else b"") for k, w in enumerate(words))
            + _pad_right(extra - left)
        )
    return out


BLANK_RELS = (258, 2050, 2178, 2306, 2434)  # 디버그 마을·배틀 테스트 마을 — 띠에는 장 제목 대신 마을 제목 줄(msg 14)이 뜬다. 장 제목 줄은 안 쓰이니 **칸마다 `a0` 빈 칸**으로 비워 앞 줄 글이 아래에 깔리지 않게 한다(그래야 제목 줄이 4px 공백 `60`(안 그림)을 써도 글 조각이 안 남는다 — 11-10)


def blank(orig: bytes) -> bytes:
    """장 제목 덩이를 14칸 모두 `a0`(그려서 지우는 빈 칸)인 줄로 바꾼다 — 줄 수는 원문 그대로."""
    return b"".join(bytes([PAD]) * (BAND_PX // CELL_PX) + b"\x00" for _ in orig.split(b"\x00")[:KEY_LINES])


def edit(orig: bytes, tab, cells: bool = False) -> bytes:
    """덩이 전체(줄마다 `00` 으로 끝)를 새로 만든다. `cells` = 시작을 12px 칸 단위로만(디버그 마을 — 같은 띠 위에 「ETC. TEST」 줄이 칸 단위로 덮어 그려 4px 짜투리 글이 남지 않게)."""
    return b"".join(l + b"\x00" for l in lines(orig, tab, cells))
