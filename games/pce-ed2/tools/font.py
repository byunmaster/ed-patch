"""한글 글리프 — 12×12 비트맵 · 코드표 · 18B 묶음 (pce-ed1 `font.py` 와 같은 규약).

    글리프 = 12×12 → 화면용 24B(행 0~11, 2B/행, 비트 15~4). **디스크엔 12비트 행으로 묶어 18B** 로 싣는다(`pack`) —
    후킹 루틴(`hook.py`)이 쓸 때 24B 로 되돌린다. 코드 = 리드 `F0 + idx//220` · 트레일 `0x24 + idx%220`.
    ⚠ 트레일은 **0x00 이 아니어야 한다** — 게임의 줄 건너뛰기(`$7DC0`)가 풀린 바이트열에서 00 을 줄 끝으로 센다(트레일도 센다).
    0x24 부터 쓰는 건 ED1 과 같은 규약이다(도구가 둘을 같은 눈으로 본다).

원천 글꼴은 `shared/fonts/Galmuri11.bdf`(11px, 12×12 셀에 맞다). 없는 글자는 **빌드 실패**다.
이 모듈은 P0 몫(기본 글리프)이다 — 부호 특수 글리프(`?` 반각 · `…` 바닥 · 겹느낌표)는 P2 에서 ED1 것을 옮겨 온다.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

FONT_BDF = common.ROOT / "shared" / "fonts" / "Galmuri11.bdf"
GLYPH_BYTES = 24
PACKED_BYTES = 18
PER_LEAD = 220
LEAD0 = 0xF0
TRAIL0 = 0x24
MAX_LEADS = 9  # F0~F8 (F9 는 뒤에 동적 조사용으로 비운다 — ED1 규약)
BASELINE_ROW = 11  # BDF 의 y=0(베이스라인)이 셀 11행

_cache: dict[int, tuple[int, int, int, int, list[str]]] | None = None


def _load_bdf():
    global _cache
    if _cache is None:
        s = FONT_BDF.read_text(encoding="utf-8", errors="replace")
        _cache = {}
        for m in re.finditer(r"STARTCHAR [^\n]*\nENCODING (\d+)\n(.*?)ENDCHAR", s, re.DOTALL):
            body = m.group(2)
            w, h, xo, yo = map(
                int, re.search(r"BBX (-?\d+) (-?\d+) (-?\d+) (-?\d+)", body).groups()
            )
            rows = re.search(r"BITMAP\n(.*)", body, re.DOTALL).group(1).split()
            _cache[int(m.group(1))] = (w, h, xo, yo, rows)
    return _cache


def glyph(ch: str) -> bytes:
    """한 글자 → 24B. 세로는 베이스라인에 맞추고 가로는 왼쪽 정렬."""
    g = _load_bdf().get(ord(ch))
    if g is None:
        raise KeyError(f"글꼴에 없는 글자: {ch!r} (U+{ord(ch):04X})")
    _w, h, xo, yo, rows = g
    out = [0] * 12
    top = BASELINE_ROW - (h + yo)
    for i, r in enumerate(rows):
        y = top + i
        if not 0 <= y < 12:
            continue  # 셀 밖으로 나가는 행은 버린다
        v = int(r, 16) << (16 - 4 * len(r))  # BDF 행은 바이트 단위로 왼쪽 정렬
        out[y] = (v >> max(xo, 0)) & 0xFFF0
    if not any(out):
        raise ValueError(f"글리프가 비었다: {ch!r}")
    return b"".join(v.to_bytes(2, "big") for v in out)


def pack(g24: bytes) -> bytes:
    """24B(행당 2B, 아래 4비트 0) → 18B(행당 12비트). 3B 가 두 행이다."""
    out = bytearray()
    for i in range(0, GLYPH_BYTES, 4):
        a, b, c, d = g24[i], g24[i + 1], g24[i + 2], g24[i + 3]
        assert b & 0x0F == 0 and d & 0x0F == 0, "행 아래 4비트가 0 이어야 한다"
        out += bytes([a, b | (c >> 4), ((c & 0x0F) << 4) | (d >> 4)])
    return bytes(out)


def unpack(p18: bytes) -> bytes:
    """`pack` 의 거꾸로 — 후킹 루틴이 하는 일과 같아야 한다(테스트가 맞댄다)."""
    out = bytearray()
    for i in range(0, PACKED_BYTES, 3):
        a, b, c = p18[i], p18[i + 1], p18[i + 2]
        out += bytes([a, b & 0xF0, ((b << 4) & 0xF0) | (c >> 4), (c << 4) & 0xF0])
    return bytes(out)


def order(chars) -> list[str]:
    """글리프 순서 — 코드는 이 순서의 번호다. 입력 문자열 모음에서 **결정적으로**(코드포인트순) 뽑는다."""
    return sorted(set(chars))


def code(idx: int) -> bytes:
    lead, trail = divmod(idx, PER_LEAD)
    assert lead < MAX_LEADS, f"글리프 {idx} 가 코드 공간(리드 {MAX_LEADS}개)을 넘는다"
    return bytes([LEAD0 + lead, TRAIL0 + trail])


def encode(text: str, table: dict[str, int]) -> bytes:
    """우리 문안 → 게임 바이트. 공백 = 단일 바이트 0x60(게임의 공백), 나머지는 글리프 코드 2바이트."""
    out = bytearray()
    for ch in text:
        if ch == " ":
            out.append(0x60)
        elif ch == "\n":
            out.append(0x0D)  # 줄바꿈 — 게임 제어 코드
        else:
            out += code(table[ch])
    return bytes(out)


class GlyphTable:
    """글리프 번호 배정 — 두 단계로 쓴다. ① 수집(`map is None`): `enc` 가 글자를 모으고 길이만 맞는 자리 코드를 낸다
    ② 확정(`freeze`): 모은 글자를 코드포인트순으로 번호 매기고, 같은 호출이 진짜 코드를 낸다.
    한글 2바이트·공백 1바이트라 **길이는 번호와 무관**하다 — 그래서 수집 단계와 확정 단계의 바이트 길이가 같다."""

    def __init__(self):
        self.chars: set[str] = set()
        self.map: dict[str, int] | None = None
        self.local: dict[str, int] = {}  # 패키지 지역 글리프(글자 → 코드 번호 S+k) — 패키지마다 갈아 끼운다

    def freeze(self) -> list[str]:
        order_ = order(self.chars)
        self.map = {ch: i for i, ch in enumerate(order_)}
        return order_

    def enc(self, text: str, space: int = 0x60) -> bytes:
        out = bytearray()
        for ch in text:
            if ch == " ":
                out.append(space)
            elif ch == "\n":
                out.append(0x0D)
            elif ch == "\f":
                out += b"\x13\x0d"  # 쪽 넘김(`13` 뒤 줄바꿈)
            elif self.map is None:
                self.chars.add(ch)
                out += code(0)
            elif ch in self.map:
                out += code(self.map[ch])
            else:
                out += code(self.local[ch])
        return bytes(out)
