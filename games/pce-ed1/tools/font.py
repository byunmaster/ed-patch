"""한글 글리프 뱅크 + 코드표 — 문안이 쓰는 음절만 싣는다(결정 B, status.md 8절).

    글리프 = 12×12 → 24B(행 0~11, 2B/행, 비트 15~4). 뱅크 0x85~0x87 에 순서대로(24B × ≤1,024).
    코드  = 리드 F0+idx//220 · 트레일 0x24+idx%220 (idx 는 음절을 유니코드 순으로 정렬한 번호).
    ⚠ 트레일은 0x24 이상 — 인터프리터가 <0x24 를 옵코드로 보고, 이름칸 스캐너가 0x06 을 끝으로 본다.

원천 글꼴은 `shared/fonts/Galmuri11.bdf`(11px, 12×12 셀에 맞다). 없는 글자는 **빌드 실패**다.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

FONT_BDF = common.ROOT / "shared" / "fonts" / "Galmuri11.bdf"
GLYPH_BYTES = 24
PER_LEAD = 220
LEAD0 = 0xF0
TRAIL0 = 0x24
MAX_GLYPHS = 3 * 0x2000 // GLYPH_BYTES  # 1,024

_cache: dict[int, tuple[int, int, int, int, list[int]]] | None = None


def _load_bdf() -> dict[int, tuple[int, int, int, int, list[int]]]:
    global _cache
    if _cache is None:
        s = FONT_BDF.read_text(encoding="utf-8", errors="replace")
        _cache = {}
        for m in re.finditer(r"STARTCHAR [^\n]*\nENCODING (\d+)\n(.*?)ENDCHAR", s, re.DOTALL):
            cp = int(m.group(1))
            body = m.group(2)
            bbx = re.search(r"BBX (-?\d+) (-?\d+) (-?\d+) (-?\d+)", body)
            rows = re.search(r"BITMAP\n(.*)", body, re.DOTALL).group(1).split()
            w, h, xo, yo = map(int, bbx.groups())
            _cache[cp] = (w, h, xo, yo, [int(r, 16) for r in rows])
    return _cache


def glyph(ch: str) -> bytes:
    """한 글자 → 24B. 세로는 셀 위에 붙이고(11px 글꼴이라 아래 1행 여백) 가로는 왼쪽 정렬."""
    g = _load_bdf().get(ord(ch))
    if g is None:
        raise KeyError(f"글꼴에 없는 글자: {ch!r} (U+{ord(ch):04X})")
    w, _h, xo, _yo, rows = g
    nbytes = (w + 7) // 8
    out = []
    for r in rows[:12]:
        v = (r << (16 - nbytes * 8)) & 0xFFFF  # BDF 행은 바이트 단위로 왼쪽 정렬돼 있다
        v = (v >> max(xo, 0)) & 0xFFF0 if xo > 0 else v & 0xFFF0
        out.append(v)
    while len(out) < 12:
        out.append(0)
    if all(v == 0 for v in out):
        raise ValueError(f"글리프가 비었다: {ch!r}")
    return b"".join(v.to_bytes(2, "big") for v in out)


def code_of(idx: int) -> bytes:
    if idx >= MAX_GLYPHS:
        raise ValueError(f"글리프 {idx} — 뱅크 셋(1,024자)을 넘는다")
    return bytes([LEAD0 + idx // PER_LEAD, TRAIL0 + idx % PER_LEAD])


def build_table(chars) -> tuple[dict[str, bytes], bytes]:
    """음절 집합 → (글자→2B 코드, 글리프 뱅크 바이트(24KB, 0 패딩))."""
    order = sorted(set(chars))
    if len(order) > MAX_GLYPHS:
        raise ValueError(f"음절 {len(order)}자 — 상한 {MAX_GLYPHS}. 결정 B 재검토(status.md 8절)")
    table = {ch: code_of(i) for i, ch in enumerate(order)}
    bank = b"".join(glyph(ch) for ch in order)
    bank += b"\0" * (3 * 0x2000 - len(bank))
    return table, bank


def encode(text: str, table: dict[str, bytes]) -> bytes:
    """우리 문안 → 게임 바이트. 한글은 표로, 나머지는 SJIS 전각으로. 못 잡는 글자는 실패."""
    out = bytearray()
    for ch in text:
        if ch in table:
            out += table[ch]
        elif ch == "\n":
            out.append(0x01)
        elif ch == " ":
            out += b"\x81\x40"  # 공백은 전각 한 칸 — 반각은 이 창에 없다(3절)
        else:
            b = ch.encode("cp932")
            if len(b) != 2 or b[0] < 0x24:
                raise ValueError(f"대사에 못 넣는 글자: {ch!r} (전각만 된다)")
            out += b
    return bytes(out)


def base_table() -> bytes:
    """후킹 루틴이 쓰는 리드별 글리프 오프셋(lo/hi 각 10B) — 코드 배치와 같은 식."""
    lo = bytes(((i * PER_LEAD * GLYPH_BYTES) & 0xFF) for i in range(10))
    hi = bytes(((i * PER_LEAD * GLYPH_BYTES) >> 8 & 0xFF) for i in range(10))
    return lo + hi


if __name__ == "__main__":
    t, bank = build_table("안녕하세요한글")
    for ch, c in t.items():
        print(ch, c.hex())
    print(len(bank))
