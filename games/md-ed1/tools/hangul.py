"""한글 인코딩 + 글꼴 리소스 0 재구성 — 방침 (b): 한자 슬롯(1,459칸) 안에 **번역문이 쓰는 한글만**.

    python3 tools/hangul.py --preview out.png "가나다…"   # 글리프 미리보기(채움 + 테두리)

- 코드: 2바이트 `0x8A40 + i`(둘째 바이트 0x40~0xFC, SJIS 꼴 유지 — 렌더러는 상위 0x80~0x9F 를 2B 로 읽는다).
  번역문에 나오는 음절을 **유니코드 순으로** 매긴다 → 같은 정본이면 같은 코드(결정적). 조회표는 오름차순이어야
  한다(`$9C36` 이 0x40B 보폭 조탐색 뒤 역방향 정탐색).
- 표 0 = 원본의 기호·숫자·영문 89자(코드 < 0x829B, 그대로) + 한글. 가나·한자는 버린다(번역문에 없다).
  ⇒ 한글 최대 **1,370자**. 넘치면 빌드가 죽는다 — 그때 (a) 리소스 분할로 간다.
- 글리프: Galmuri11(11×11, 셀 아래 정렬) 채움 + 테두리(8방향 팽창 − 채움, 원본 규칙 196/196 일치).
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font

# ⚠ 14px 글꼴은 못 쓴다 — 대사창 피치가 12px 라 옆 글자의 테두리 면이 앞 글자를 갉아먹는다(실측, devlog).
#   Galmuri11(11×11, 1px 획)이 12px 피치에 딱 맞는다. 원본 굵기(2px 획)에 가까운 건 Galmuri11-Bold 인데
#   글자끼리 닿는다 — 유저가 고르면 여기 한 줄만 바꾼다(work/emu 미리보기 `--preview`).
BDF = common.ROOT / "shared" / "fonts" / "Galmuri11.bdf"
CODE_BASE = 0x8A40
KEEP_MAX = 0x829A  # 표 0 에서 그대로 두는 원본 항목(기호·숫자·영문)의 마지막 코드
CELL = 14

_bdf_cache: dict[str, list[list[int]]] | None = None


def _load_bdf() -> dict[str, list[list[int]]]:
    """BDF 전체를 한 번 읽어 {글자: 14×14 비트 행렬}. 폭·높이가 14 를 넘는 건 자른다(없어야 한다)."""
    global _bdf_cache
    if _bdf_cache is not None:
        return _bdf_cache
    out = {}
    lines = BDF.read_text(encoding="utf-8", errors="replace").split("\n")
    i = 0
    while i < len(lines):
        if lines[i].startswith("ENCODING "):
            ch = chr(int(lines[i].split()[1]))
            while not lines[i].startswith("BBX"):
                i += 1
            bw, bh, bx, by = map(int, lines[i].split()[1:5])
            while lines[i].strip() != "BITMAP":
                i += 1
            rows = []
            for r in lines[i + 1 : i + 1 + bh]:
                r = r.strip()
                v = int(r, 16)
                nb = len(r) * 4
                rows.append([(v >> (nb - 1 - x)) & 1 for x in range(bw)])
            grid = [[0] * CELL for _ in range(CELL)]
            # Galmuri14: 베이스라인이 아래에서 by 만큼 위. 셀 안에 위쪽 정렬 + 가로 오프셋 bx
            top = max(0, CELL - bh - by)
            for y in range(min(bh, CELL - top)):
                for x in range(bw):
                    if 0 <= x + bx < CELL and rows[y][x]:
                        grid[top + y][x + bx] = 1
            out[ch] = grid
            i += bh + 1
        i += 1
    _bdf_cache = out
    return out


def glyph_fill(ch: str) -> list[list[int]]:
    g = _load_bdf().get(ch)
    if g is None:
        raise KeyError(f"Galmuri14 에 없는 글자: {ch!r}")
    return g


def ring(fill: list[list[int]]) -> list[list[int]]:
    """테두리 면 = 8방향 팽창 − 채움(원본 둘째 면의 규칙)."""
    h, w = len(fill), len(fill[0])
    out = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if fill[y][x]:
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if 0 <= y + dy < h and 0 <= x + dx < w and fill[y + dy][x + dx]:
                        out[y][x] = 1
    return out


def pack(rows: list[list[int]]) -> bytes:
    return b"".join(struct.pack(">H", sum(v << (15 - x) for x, v in enumerate(r))) for r in rows)


def is_hangul(ch: str) -> bool:
    return "가" <= ch <= "힣"


def codes_for(syllables: set[str]) -> dict[str, int]:
    """번역문에 쓰는 음절 집합 → {음절: 코드}. 둘째 바이트는 0x40~0xFC(0x7F 건너뜀), SJIS 꼴."""
    seconds = [b for b in range(0x40, 0xFD) if b != 0x7F]
    out = {}
    for i, ch in enumerate(sorted(syllables)):
        hi, lo = divmod(i, len(seconds))
        out[ch] = ((0x8A + hi) << 8) | seconds[lo]
        if 0x8A + hi > 0x9F:
            raise ValueError("한글 코드가 0x9F 를 넘는다 — 상위 바이트 범위 밖")
    return out


class Charset:
    """빌드 한 번의 문자 집합 — 표 0 항목(코드 오름차순)과 글자→코드."""

    def __init__(self, rom: bytes, syllables: set[str]):
        r0 = font.resources(rom)[0]
        keep = [c for c in font.codes(rom, r0) if c <= KEEP_MAX]
        self.keep_codes = keep
        self.hangul = codes_for(syllables)
        self.entries = sorted(keep + list(self.hangul.values()))
        if len(self.entries) > r0["entries"]:
            raise SystemExit(
                f"표 0 이 넘친다: 원본 기호 {len(keep)} + 한글 {len(self.hangul)} > {r0['entries']} — 방침 (a) 로 간다"
            )
        self.r0 = r0
        self.rom = rom

    def encode_char(self, ch: str) -> bytes:
        if is_hangul(ch):
            return struct.pack(">H", self.hangul[ch])
        if 0x20 <= ord(ch) < 0x7F:
            return ch.encode("ascii")  # 반각(리소스 1)
        try:
            code = int.from_bytes(ch.encode("cp932"), "big")
        except UnicodeEncodeError as e:
            raise KeyError(f"인코딩 불가: {ch!r}") from e
        if code not in self.keep_codes:
            raise KeyError(f"표 0 에 없는 글자: {ch!r} ({code:04x})")
        return struct.pack(">H", code)

    def encode(self, s: str) -> bytes:
        return b"".join(self.encode_char(c) for c in s)

    def resource0(self) -> tuple[bytes, bytes, bytes]:
        """(헤더 12B, 표, 글리프 데이터) — 서술자 4B 는 글리프 앞에 그대로."""
        r0 = self.r0
        rom = self.rom
        by_code = {v: k for k, v in self.hangul.items()}
        orig_codes = font.codes(rom, r0)
        table = b"".join(struct.pack(">H", c) for c in self.entries)
        glyphs = bytearray()
        for c in self.entries:
            if c in by_code:
                f = glyph_fill(by_code[c])
                glyphs += pack(f) + pack(ring(f))
            else:
                i = orig_codes.index(c)
                g = r0["glyphs"] + i * r0["stride"]
                glyphs += rom[g : g + r0["stride"]]
        h = r0["hdr"]
        tbl_off = r0["table"] - h
        end_off = tbl_off + len(table) - 4
        desc = r0["desc"] - h - 8
        header = struct.pack(">III", tbl_off, end_off, desc)
        return header, table, bytes(glyphs)


def preview(chars: str, out: Path, per_row: int = 24) -> None:
    from PIL import Image

    rows = (len(chars) + per_row - 1) // per_row
    im = Image.new("RGB", (per_row * (CELL + 2), rows * (CELL + 2)), (40, 40, 60))
    px = im.load()
    for i, ch in enumerate(chars):
        f = glyph_fill(ch)
        r = ring(f)
        gx, gy = (i % per_row) * (CELL + 2), (i // per_row) * (CELL + 2)
        for y in range(CELL):
            for x in range(CELL):
                if f[y][x]:
                    px[gx + x, gy + y] = (255, 255, 255)
                elif r[y][x]:
                    px[gx + x, gy + y] = (0, 0, 0)
    im = im.resize((im.width * 3, im.height * 3))
    im.save(out)
    print(f"  {out} ({len(chars)}자)")


if __name__ == "__main__":
    if "--preview" in sys.argv:
        i = sys.argv.index("--preview")
        preview(sys.argv[i + 2], Path(sys.argv[i + 1]))
