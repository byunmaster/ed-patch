"""한글 인코딩 + 글꼴 리소스 0 재구성 — 방침 (b): 한자 슬롯(1,459칸) 안에 **번역문이 쓰는 한글만**.

    python3 tools/hangul.py --preview out.png "가나다…"   # 글리프 미리보기(채움 + 테두리)

- 코드: 2바이트 `0x8A40 + i`(둘째 바이트 0x40~0xFC, SJIS 꼴 유지 — 렌더러는 상위 0x80~0x9F 를 2B 로 읽는다).
  번역문에 나오는 음절을 **유니코드 순으로** 매긴다 → 같은 정본이면 같은 코드(결정적). 조회표는 오름차순이어야
  한다(`$9C36` 이 0x40B 보폭 조탐색 뒤 역방향 정탐색).
- 표 0 = 원본의 기호·숫자·영문 89자(코드 < 0x829B, 그대로) + 한글. 가나·한자는 버린다(번역문에 없다).
  ⇒ 한글 최대 **1,370자**. 넘치면 빌드가 죽는다 — 그때 (a) 리소스 분할로 간다.
- 글리프: Galmuri11(11×11, 셀 아래 정렬) 채움 + 테두리(8방향 팽창 − 채움, 원본 규칙 196/196 일치).
"""

import json
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

_bdf_cache: dict[tuple, dict[str, list[list[int]]]] = {}


def _load_bdf(
    path: Path | None = None, cell: int = CELL, top: int = 1
) -> dict[str, list[list[int]]]:
    """BDF 전체를 한 번 읽어 {글자: cell×cell 비트 행렬}. 폭·높이가 cell 을 넘는 건 자른다."""
    path = path or BDF
    key = (str(path), cell, top)
    if key in _bdf_cache:
        return _bdf_cache[key]
    out = {}
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    i = 0
    while i < len(lines):
        if lines[i].startswith("ENCODING "):
            ch = chr(int(lines[i].split()[1]))
            while not lines[i].startswith("BBX"):
                i += 1
            bw, bh, bx, _by = map(int, lines[i].split()[1:5])
            while lines[i].strip() != "BITMAP":
                i += 1
            rows = []
            for r in lines[i + 1 : i + 1 + bh]:
                r = r.strip()
                v = int(r, 16)
                nb = len(r) * 4
                rows.append([(v >> (nb - 1 - x)) & 1 for x in range(bw)])
            grid = [[0] * cell for _ in range(cell)]
            # 셀 **위쪽**에 붙인다(기본 1~11행). HUD 장 제목 바는 셀 높이가 14 보다 낮아 아래를 자르므로
            # 아래 정렬이면 받침이 잘린다(실측: 「제1장」이 「조1적」으로 보였다). 대사창은 줄 간격 16 이라 무방.
            for y in range(min(bh, cell - top)):
                for x in range(bw):
                    if 0 <= x + bx < cell and rows[y][x]:
                        grid[top + y][x + bx] = 1
            out[ch] = grid
            i += bh + 1
        i += 1
    _bdf_cache[key] = out
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


def needs_glyph(ch: str, keep_codes: list[int]) -> bool:
    """새 글리프가 필요한 글자 — 한글, 그리고 원본 표에도 ASCII 에도 없는 기호(…‘’“” 등)."""
    if is_hangul(ch):
        return True
    if 0x20 <= ord(ch) < 0x7F or ch in "\n\f":
        return False
    try:
        return int.from_bytes(ch.encode("cp932"), "big") not in keep_codes
    except UnicodeEncodeError:
        return True


CODES_JSON = common.GAME_DIR / "textmap" / "hangul_codes.json"


def _code_at(i: int) -> int:
    seconds = [b for b in range(0x40, 0xFD) if b != 0x7F]
    hi, lo = divmod(i, len(seconds))
    if 0x8A + hi > 0x9F:
        raise SystemExit("한글 코드가 0x9F 를 넘는다 — 상위 바이트 범위 밖")
    return ((0x8A + hi) << 8) | seconds[lo]


def codes_for(syllables: set[str], freeze: bool = False) -> dict[str, int]:
    """글자 → 코드. **정본 `textmap/hangul_codes.json` 에 고정**한다 — 쓰는 글자 순으로 매번 다시 매기면 문안이 늘 때마다
    코드가 밀려 세이브(장 제목·파티 이름이 든다)와 스테이트의 글자가 다른 글자로 뜬다(2026-09-05 실측). 새 글자는
    뒤에 붙인다(`--freeze`). 빌드는 정본에 없는 글자를 실패로 친다."""
    cur = json.loads(CODES_JSON.read_text(encoding="utf-8")) if CODES_JSON.exists() else {}
    missing = sorted(c for c in syllables if c not in cur)
    if missing and not freeze:
        raise SystemExit(
            f"코드가 고정되지 않은 글자 {len(missing)}: {''.join(missing[:40])}… — `python3 tools/hangul.py --freeze` 로 붙인다"
        )
    if missing:
        n = len(cur)
        for k, ch in enumerate(missing):
            cur[ch] = _code_at(n + k)
        CODES_JSON.parent.mkdir(exist_ok=True)
        CODES_JSON.write_text(json.dumps(cur, ensure_ascii=False, indent=0), encoding="utf-8")
    return {c: cur[c] for c in syllables}


class Charset:
    """빌드 한 번의 문자 집합 — 표 0 항목(코드 오름차순)과 글자→코드."""

    def __init__(self, rom: bytes, chars: set[str]):
        r0 = font.resources(rom)[0]
        keep = [c for c in font.codes(rom, r0) if c <= KEEP_MAX]
        self.keep_codes = keep
        self.hangul = codes_for({c for c in chars if needs_glyph(c, keep)})
        self.entries = sorted(keep + list(self.hangul.values()))
        if len(self.entries) > r0["entries"]:
            raise SystemExit(
                f"표 0 이 넘친다: 원본 기호 {len(keep)} + 한글 {len(self.hangul)} > {r0['entries']} — 방침 (a) 로 간다"
            )
        self.r0 = r0
        self.rom = rom

    def encode_char(self, ch: str) -> bytes:
        if ch in self.hangul:
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


# 반각 리소스 1 에 없는 쉼표(0x2C) — 온점(행 8~11 의 점)과 같은 자리에 꼬리를 단다. 8×14, 1B/행.
COMMA_FILL = [
    "........",
    "........",
    "........",
    "........",
    "........",
    "........",
    "........",
    "........",
    "..#.....",
    ".###....",
    ".###....",
    "..##....",
    "...#....",
    "..#.....",
]
FONT1_HDR = (0x1A54DE, 0x1A54EA)


def _pack8(rows: list[list[int]]) -> bytes:
    return bytes(sum(v << (7 - x) for x, v in enumerate(r)) for r in rows)


def resource1(cs: "Charset") -> list[tuple[str, int, bytes]]:
    """리소스 1(반각 8×14)에 쉼표를 더한 새 표·글리프를 표 0 이 비운 자리에 두고 헤더를 돌린다.
    → [(라벨, 자리, 바이트)] — 라벨은 build.Rom 의 허용 구간 이름."""
    rom = cs.rom
    r0, r1 = font.resources(rom)[:2]
    codes = font.codes(rom, r1)
    if 0x2C in codes:
        return []
    i = next(k for k, c in enumerate(codes) if c > 0x2C)
    codes.insert(i, 0x2C)
    fill = [[1 if ch == "#" else 0 for ch in row] for row in COMMA_FILL]
    g = rom[r1["glyphs"] : r1["glyphs"] + (len(codes) - 1) * r1["stride"]]
    glyphs = g[: i * r1["stride"]] + _pack8(fill) + _pack8(ring(fill)) + g[i * r1["stride"] :]
    table = b"".join(struct.pack(">H", c) for c in codes)
    tbl_at = r0["table"] + 2 * len(cs.entries)  # 표 0 바로 뒤 (짝수)
    desc_at = r0["desc"] + 4 + len(cs.entries) * r0["stride"]  # 표 0 글리프 바로 뒤
    if tbl_at + len(table) > r0["table_end"]:
        raise SystemExit("표 0 이 커서 리소스 1 표를 둘 자리가 없다")
    h = r1["hdr"]
    header = struct.pack(">III", tbl_at - h, tbl_at + len(table) - 4 - h, desc_at - h - 8)
    desc = rom[r1["desc"] : r1["desc"] + 4]
    return [
        ("font1-header", h, header),
        ("font0-table", tbl_at, table),
        ("font0-glyphs", desc_at, desc + glyphs),
    ]


# ── HUD 소형 폰트 ──────────────────────────────────────────────────────────────
# 리소스 2(8×8, 1B/행, 두 면): 「ｱﾄ」(b1·c4 — 다음 레벨까지 남은 경험치 라벨) 글리프만 「다음」으로.
# 리소스 4(12×12, 2B/행, 두 면, 86칸): HUD 이름(`fd 84`, 필드·전투)의 2B 글꼴 — 파티 이름 음절로 갈아 끼운다.
FONT2_GLYPHS = (0x1BB056, 0x1BB2D6)
FONT4_HDR = (0x1A5502, 0x1A550E)
FONT4_TABLE = (0x1A6222, 0x1A62CE)
FONT4_GLYPHS = (0x1BB66E, 0x1BC68E)
BDF7 = common.ROOT / "shared" / "fonts" / "Galmuri7.bdf"
LABEL_R2 = {0xB1: "다", 0xC4: "음"}


def _pack_w(rows: list[list[int]], width: int) -> bytes:
    if width <= 8:
        return bytes(sum(v << (7 - x) for x, v in enumerate(r)) for r in rows)
    return b"".join(struct.pack(">H", sum(v << (15 - x) for x, v in enumerate(r))) for r in rows)


def resource2_labels() -> list[tuple[str, int, bytes]]:
    """리소스 2 의 「ｱ」「ﾄ」 자리에 Galmuri7 「다」「음」(8×8, 위 1행 띄움)."""
    rom = common.rom()
    r2 = font.resources(rom)[2]
    codes = font.codes(rom, r2)
    g7 = _load_bdf(BDF7, 8, 1)
    out = []
    for code, ch in LABEL_R2.items():
        fill = g7[ch]
        pos = r2["glyphs"] + codes.index(code) * r2["stride"]
        out.append(("font2-glyphs", pos, _pack_w(fill, 8) + _pack_w(ring(fill), 8)))
    return out


def resource4(cs: "Charset", chars: set[str]) -> list[tuple[str, int, bytes]]:
    """리소스 4 를 HUD 이름 음절로 — 표(코드 오름차순, 표 0 과 같은 코드)·글리프(12×12 Galmuri11)·헤더(표 끝)."""
    rom = cs.rom
    r4 = font.resources(rom)[4]
    codes = sorted({cs.hangul[c] for c in chars if c in cs.hangul})
    if len(codes) > r4["entries"]:
        raise SystemExit(f"리소스 4 가 넘친다: HUD 이름 음절 {len(codes)} > {r4['entries']}")
    g11 = _load_bdf(BDF, 12, 0)
    by_code = {v: k for k, v in cs.hangul.items()}
    glyphs = bytearray()
    for c in codes:
        fill = g11[by_code[c]]
        glyphs += _pack_w(fill, 12) + _pack_w(ring(fill), 12)
    table = b"".join(struct.pack(">H", c) for c in codes)
    h = r4["hdr"]
    header = struct.pack(
        ">III", r4["table"] - h, r4["table"] + len(table) - 4 - h, r4["desc"] - h - 8
    )
    return [
        ("font4-header", h, header),
        ("font4-table", r4["table"], table),
        ("font4-glyphs", r4["glyphs"], bytes(glyphs)),
    ]


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
    if "--freeze" in sys.argv:
        import build

        rom = common.rom()
        r0 = font.resources(rom)[0]
        keep = [c for c in font.codes(rom, r0) if c <= KEEP_MAX]
        chars = build.collect_chars(build.load_textmaps())
        codes_for({c for c in chars if needs_glyph(c, keep)}, freeze=True)
        print(f"  {CODES_JSON}: {len(json.loads(CODES_JSON.read_text(encoding='utf-8')))}자 고정")
    elif "--preview" in sys.argv:
        i = sys.argv.index("--preview")
        preview(sys.argv[i + 2], Path(sys.argv[i + 1]))
