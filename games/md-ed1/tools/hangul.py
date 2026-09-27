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
    path: Path | None = None, cell: int = CELL, top: int = 1, left: int = 0
) -> dict[str, list[list[int]]]:
    """BDF 전체를 한 번 읽어 {글자: cell×cell 비트 행렬}. 폭·높이가 cell 을 넘는 건 자른다."""
    path = path or BDF
    key = (str(path), cell, top, left)
    if key in _bdf_cache:
        return _bdf_cache[key]
    raw = {}
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
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
            raw[ch] = (bw, bh, bx, by, rows)
            i += bh + 1
        i += 1
    # 🔴 BBX 의 **y 오프셋(by)** 을 쓴다 — 버리면 키 작은 글자(마침표·「…」)가 셀 꼭대기에 붙는다
    # (pce-ed1 이 화면에서 물렸다: 「나타났다`」). 기준선은 **글꼴에서 잰다** — 한글은 by=0·bh=11 이라
    # ref = max(by+bh) = 11 이 되고, 그 글자들은 지금 자리 그대로다(재빌드 요동 없음).
    # ⚠ FONT_ASCENT(14)를 쓰면 한글이 3행 내려가 **HUD 장 제목 바에서 받침이 잘린다** — 그래서
    # 「위쪽 정렬」이라는 우리 사정은 top 으로 유지하고, 글자마다의 높이 차이만 by 로 맞춘다.
    # 기준은 **한글 한 글자**(가)다 — 글꼴 전체의 최대치를 쓰면 라틴 큰 글자 때문에 한글이 밀린다.
    _bw, _bh, _bx, _by, _rows = raw.get("가", (0, 0, 0, 0, []))
    ref = (_by + _bh) or max((by + bh) for _w, bh, _x, by, _r in raw.values())
    out = {}
    for ch, (bw, bh, bx, by, rows) in raw.items():
        grid = [[0] * cell for _ in range(cell)]
        y0 = top + (ref - (by + bh))
        for y in range(bh):
            ry = y0 + y
            if not 0 <= ry < cell:
                continue
            for x in range(bw):
                rx = x + bx + left
                if 0 <= rx < cell and rows[y][x]:
                    grid[ry][rx] = 1
        out[ch] = grid
    _bdf_cache[key] = out
    return out


NEODGM = common.ROOT / "shared" / "fonts" / "neodgm.ttf"
_neo_cache: dict[str, list[list[int]]] = {}


def neodgm_fill(ch: str, cell: int = 16, size: int = 16) -> list[list[int]]:
    """네오둥근모 글리프 → cell×cell 비트 행렬. **16px 에서만 계단이 없다**(14·15px 는 회색 픽셀이 섞인다,
    2026-09-05 실측) — 그래서 16×16 칸(타이틀 셀·리소스 5)에만 쓴다. 임계값 이진화라 렌더러 판이 달라도
    같은 결과가 나온다(제1원칙: 빌드는 결정적).

    ⚠ 잘라 낼 창은 **글자마다가 아니라 고정**이다(그리는 자리 +1,+1). 글자별 잉크 상자에 맞추면
    「」·… 같은 기호가 칸 왼쪽 위로 끌려와 자리가 틀어진다.
    """
    key = f"{ch}:{cell}:{size}"
    if key in _neo_cache:
        return _neo_cache[key]
    from PIL import Image, ImageDraw, ImageFont

    f = ImageFont.truetype(str(NEODGM), size)
    pad = 8
    im = Image.new("L", (cell + 2 * pad, cell + 2 * pad), 0)
    ImageDraw.Draw(im).text((pad, pad), ch, font=f, fill=255)
    # 잉크는 그리는 자리 +1,+1 에서 시작한다 ⇒ 창을 **그리는 자리 그대로** 잡아 잉크를 1,1 로 민다.
    # 그래야 팽창 테두리(8방향)가 0행·0열에 들어간다 — +1,+1 로 잡으면 위·왼쪽 테두리가 잘린다
    # (2026-09-05 유저 지적: 「처음부터/이어하기가 위쪽 1px 잘린 느낌」).
    ox = oy = pad
    g = [
        [1 if im.getpixel((ox + x, oy + y)) >= 128 else 0 for x in range(cell)] for y in range(cell)
    ]
    _neo_cache[key] = g
    return g


# 실험 손잡이 — HUD 장 제목 밴드에서 받침이 잘리는 자리(status.md 2026-09-15)를 재려고 둔다.
# 정본은 top=1(기존, MD_GLYPH_TOP=0 은 마스터 반려 2026-09-15 — 원본도 아래를 넘긴다는 게 값으로
# 확인돼 세로는 그대로 둔다). `_load_bdf` 의 그 값 그대로다 — **바꾸면 리소스 0 전체(대사창 포함)가
# 움직인다.**
#
# MD_GLYPH_LEFT — 가로 손잡이(같은 날, 이어서). bx=0 인 한글(제·장·왕 등, 대부분)은 잉크가 칸
# 0열에 바로 붙어 **왼쪽으로 테두리가 팽창할 자리가 없다**(-1열은 없다) — 그 행만 테두리 없이
# 잉크가 배경에 바로 닿는다. 문자열 첫 글자에서 특히 드러난다(뒷글자는 피치 12 < 셀 14 라 앞
# 글자 테두리가 그 자리를 메운다).
# 🔴 **기본값 1 = 정본**(마스터 승인 2026-09-15, "글자가 온전하네"). `resource0()`의 kept 코드
# (숫자·기호·영문, 원본 그대로 복사하던 자리)도 같이 밀어야 한다 — 한글만 밀면 kept 코드가
# 제자리라 「제１장」처럼 한글과 kept 코드가 섞인 자리에서 간격이 어긋난다(마스터가 화면에서
# 직접 잡았다). 리소스 1(반각)은 **안 민다** — 한글 최대 오른쪽 열이 이동해도 10→11 인데
# 리소스0→1 겹침은 열12 부터 시작해 **항상 열12 앞에서 멈춘다**(BDF 11,172자 전수 확인) —
# 깨짐이 구조적으로 불가능해 밀 필요가 없다.
import os as _os

GLYPH_TOP = int(_os.environ.get("MD_GLYPH_TOP", "1"))
GLYPH_LEFT = int(_os.environ.get("MD_GLYPH_LEFT", "1"))


def extend_jamo_arms(grid: list[list[int]]) -> list[list[int]]:
    """갈무리11 의 `ㅏㅓ…` 계열 가로획(팔)이 1px 뿐이라 안 읽힌다(마스터 지적 2026-09-17,
    재 보니 정확했다 — 세로획이 있으면 8방향 팽창 테두리가 옆 칸에 늘 "+"를 찍어서, 팔이
    있는 행이나 없는 행이나 그 칸이 똑같이 밝아 팔이 도드라지지 않는다).

    **무엇을 보고 늘리나**: 어떤 칸(x)에 세로로 3행 이상 이어지는 채움(스트로크)이 있고,
    바로 옆 칸(x+1)에 **딱 1~2행짜리 고립된 돌출**(그 칸 전체를 봐도 다른 데는 안 채워짐)이
    붙어 있으면, 그 돌출을 한 칸 더(x+2) 늘린다. 세로획 옆의 짧은 돌출만 골라내므로
    ㄱ·ㅋ 의 윗획처럼 원래 긴 가로획은 (돌출이 아니라서) 안 걸리고, ㅏㅓ 류의 팔만 걸린다.

    ⚠ 캡션 235자 전수 확인(2026-09-17): 60자가 걸림(대부분 ㅏㅓ 류 + 「왕」처럼 ㅘ 안에 ㅏ가
    낀 자리) · 부작용 **1건**(「국」— 이미 11칸짜리 가로획 끝에 1px 이 더 붙을 뿐이라 티가
    안 난다) · 우측 경계(칸15) 넘침 0.
    """
    h, w = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for y in range(h):
        for x in range(w - 1):
            if not (grid[y][x] and grid[y][x + 1] and (x + 2 >= w or not grid[y][x + 2])):
                continue
            run = 1
            yy = y - 1
            while yy >= 0 and grid[yy][x]:
                run += 1
                yy -= 1
            yy = y + 1
            while yy < h and grid[yy][x]:
                run += 1
                yy += 1
            if run < 3:
                continue
            col_x1_run = sum(1 for yy2 in range(h) if grid[yy2][x + 1])
            if col_x1_run <= 2 and x + 2 < w:
                out[y][x + 2] = 1
    return out


_period_dot_cache: tuple[list[list[int]], int] | None = None


def _period_dot() -> tuple[list[list[int]], int]:
    """원작 마침표(반각 리소스1, **켑트 바이트 — 우리가 안 그렸다**)의 잉크 모양과 그
    절대 행(칸 맨 위에서부터 몇 번째 행에 잉크가 시작하나).

    🔴 **정정(2026-09-17)** — 말줄임표를 처음 맞출 때 "마침표"를 갈무리11.bdf 에서
    잘못 읽었다(`glyph_fill(".")` 는 실제로 안 쓰인다 — `.` 은 ASCII 라 `needs_glyph()` 가
    False 를 내 애초에 리소스0/5 를 안 타고 **리소스1(반각, 원작 그대로)** 로 나간다).
    실제 화면의 마침표는 이 함수가 읽는 8×14 켑트 글리프고, **3×4 다이아몬드**(테두리 포함
    5×6)다 — Galmuri11 의 자체 `.` 글리프(1×1)보다 훨씬 크다. 말줄임표 점은 이 모양을
    기준으로 잡아야 "마침표와 같은 크기"가 된다.
    """
    global _period_dot_cache
    if _period_dot_cache is not None:
        return _period_dot_cache
    rom = common.rom()
    r1 = font.resources(rom)[1]
    codes = font.codes(rom, r1)
    i = codes.index(ord("."))
    raw = rom[r1["glyphs"] + i * r1["stride"] : r1["glyphs"] + (i + 1) * r1["stride"]]
    fill = [[(b >> (7 - x)) & 1 for x in range(8)] for b in raw[:14]]
    ys = [y for y, row in enumerate(fill) if any(row)]
    xs = [x for row in fill for x, v in enumerate(row) if v]
    y0, y1, x0, x1 = min(ys), max(ys), min(xs), max(xs)
    dot = [row[x0 : x1 + 1] for row in fill[y0 : y1 + 1]]
    _period_dot_cache = (dot, y0)
    return _period_dot_cache


def ellipsis_dots(cell: int) -> list[list[int]]:
    """말줄임표 — **점 크기·가로 간격은 갈무리11 원본 그대로, 세로 위치만** 마침표의
    바닥(원작 켑트 글리프의 잉크 맨 아래 행)으로 내린다(마스터 확정 2026-09-17 —
    "크기는 그대로 위치만 아래로". 점 모양을 마침표 크기로 다시 그리는 안은 접었다).

    갈무리11 자체 `…` 글리프는 칸 가운데(일본식)에 있다 — 그 잉크를 통째로 세로로만
    밀어 **잉크의 맨 아래 행 = 마침표(리소스1, 원작) 잉크의 맨 아래 행**이 되게 한다.
    """
    native = _load_bdf(BDF, cell, top=GLYPH_TOP, left=GLYPH_LEFT)["…"]
    native_bottom = max((y for y, row in enumerate(native) if any(row)), default=None)
    _dot, y0 = _period_dot()
    period_bottom = y0 + len(_dot) - 1
    if native_bottom is None:
        return native
    shift = period_bottom - native_bottom
    out = [[0] * cell for _ in range(cell)]
    for y, row in enumerate(native):
        ny = y + shift
        if 0 <= ny < cell:
            out[ny] = row[:]
    return out


def glyph_fill(ch: str) -> list[list[int]]:
    if ch == "…":
        return ellipsis_dots(CELL)
    g = _load_bdf(top=GLYPH_TOP, left=GLYPH_LEFT).get(ch)
    if g is None:
        raise KeyError(f"Galmuri14 에 없는 글자: {ch!r}")
    return extend_jamo_arms(g)


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


def unpack(data: bytes, w: int, h: int) -> list[list[int]]:
    return [[(v >> (15 - x)) & 1 for x in range(w)] for v in struct.unpack(f">{h}H", data)]


def shift_cols(rows: list[list[int]], left: int, cell: int) -> list[list[int]]:
    """열을 `left` 만큼 오른쪽으로 미는 자리 이동 — 칸을 넘는 열은 버린다(`_load_bdf` 와 같은 규칙)."""
    if left == 0:
        return rows
    h = len(rows)
    out = [[0] * cell for _ in range(h)]
    for y in range(h):
        for x in range(cell):
            rx = x + left
            if 0 <= rx < cell and rows[y][x]:
                out[y][rx] = 1
    return out


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


def check_frozen() -> None:
    """🔴 배정이 **흔들리지 않았나** — 커밋된 정본과 대조한다(세이브 호환의 근본 조건).

    빌드는 「없는 글자」만 실패로 친다. 그런데 진짜 사고는 **재생성**이다 — 누가 코드표를 유니코드
    순으로 다시 매기면 빌드는 그대로 통과하고, **옛 세이브의 이름·장 제목이 딴 글자로 뜬다**
    (파티 이름은 레코드에 우리 코드로 박혀 세이브로 따라간다). pce-ed1 이 같은 사고를 실제로 겪었다.
    ⇒ `git show HEAD:<정본>` 과 대조해 **이미 있던 글자의 코드가 바뀌거나 사라졌으면** 실패시킨다.
    """
    import subprocess

    rel = CODES_JSON.relative_to(common.ROOT)
    cur = json.loads(CODES_JSON.read_text(encoding="utf-8"))
    try:
        old_raw = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=common.ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"  한글 코드 {len(cur)}자 — 커밋본이 없어 대조는 건너뛴다")
        return
    old = json.loads(old_raw)
    moved = [c for c, v in old.items() if cur.get(c) != v]
    if moved:
        raise SystemExit(
            f"한글 코드가 밀렸다({len(moved)}자: {''.join(moved[:20])}…) — 세이브 호환이 깨진다. "
            "정본은 **뒤에만** 붙인다(`--freeze`)"
        )
    print(f"  한글 코드 {len(cur)}자 · 커밋본 {len(old)}자 대조 OK (밀린 글자 0)")


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
        r1 = font.resources(rom)[1]
        # 반각으로 나갈 수 있는 코드 — 원본 표 + resource1() 이 끼워 넣는 글자.
        # 🔴 표에 없는 반각을 쓰면 **화면에서 조용히 빈칸**이 된다(괄호로 물렸다, 2026-09-06).
        self.half = set(font.codes(rom, r1)) | set(EXTRA_R1)

    def encode_char(self, ch: str) -> bytes:
        if ch in self.hangul:
            return struct.pack(">H", self.hangul[ch])
        if 0x20 <= ord(ch) < 0x7F:
            if ord(ch) not in self.half:
                raise SystemExit(
                    f"반각 글리프가 없다: {ch!r}({ord(ch):#04x}) — 글꼴 리소스 1 에 없는 글자다. "
                    "hangul.EXTRA_R1 에 글리프를 넣거나 문안에서 뺀다"
                )
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
                raw = rom[g : g + r0["stride"]]
                if GLYPH_LEFT:
                    # 🔴 kept 코드(기호·숫자·영문, 원본 그대로)도 한글과 **같은 이동**을 받아야
                    # 리소스 0 전체가 균일하게 밀린다 — 안 그러면 「올(」처럼 한글 뒤에 반각이
                    # 바로 붙는 자리에서 둘의 상대 간격이 어긋난다(status.md 2026-09-15, 마스터
                    # 지시 "x값을 오른쪽으로 1px" 를 한글에만 반만 적용했던 자리를 마저 채운다).
                    # ⚠ 열13 에 이미 닿은 글리프가 **`％`(0x8193) 하나** 있다 — 지금은 문안에
                    # 사용례가 0건이라 안전하지만, **나중에 누가 `％`를 쓰면 그 오른쪽 1열이
                    # 잘린다.** 쓰게 되면 그때 이 글리프만 예외 처리한다.
                    fill = unpack(raw[: r0["nbytes"]], r0["w"], r0["h"])
                    fill = shift_cols(fill, GLYPH_LEFT, r0["w"])
                    raw = pack(fill) + pack(ring(fill))
                glyphs += raw
        h = r0["hdr"]
        tbl_off = r0["table"] - h
        end_off = tbl_off + len(table) - 4
        desc = r0["desc"] - h - 8
        header = struct.pack(">III", tbl_off, end_off, desc)
        return header, table, bytes(glyphs)


# 반각 리소스 1 에 **없는 글자**들 — 원본 표엔 ` !"-.0-9?A-Za-z` 뿐이다. 8×14, 1B/행.
# 🔴 괄호가 없으면 병기 「을(를)」이 화면에서 「을 를」로 뜬다(2026-09-06 인게임 실측 — 39자리).
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
PAREN_L_FILL = [
    "........",
    "....##..",
    "...##...",
    "..##....",
    "..##....",
    ".##.....",
    ".##.....",
    ".##.....",
    "..##....",
    "..##....",
    "...##...",
    "....##..",
    "........",
    "........",
]
PAREN_R_FILL = ["".join(reversed(r)) for r in PAREN_L_FILL]

# 갈무리11 자체 마침표·쉼표 — **마스터 확정(2026-09-17)**: 원작 마침표(켑트 바이트,
# 3×4 다이아몬드)·우리 손그림 쉼표가 큰 건 실수가 아니라 **일본식 조판 관례**였다(부호를
# 덩어리로 크게 그린다). 한글 획 하나(테두리 포함 3px)와 비슷한 크기인 갈무리11 자체 부호로
# 바꾸는 쪽으로 정했다 — 8×14 칸(리소스1 규격, top=1·left=1, 대사창과 같은 오프셋)에 얹은 그대로.
PERIOD_FILL_GALMURI = ["........"] * 11 + ["..#....."] + ["........"] * 2
COMMA_FILL_GALMURI = ["........"] * 11 + ["..#....."] + [".#......"] + ["........"]
# MD_PUNCT_SRC=original 로 되돌릴 수 있는 손잡이는 남긴다(비교·회귀용) — 정본은 galmuri.
PUNCT_SRC = _os.environ.get("MD_PUNCT_SRC", "galmuri")
EXTRA_R1 = {
    0x28: PAREN_L_FILL,
    0x29: PAREN_R_FILL,
    0x2C: (lambda: COMMA_FILL_GALMURI if PUNCT_SRC == "galmuri" else COMMA_FILL),
}
# 🔴 마침표는 EXTRA_R1(없는 글자 추가) 이 아니라 OVERRIDE_R1(있는 글자를 갈아 끼움) 이다 —
# 원작이 이미 갖고 있던 켑트 코드라 "추가"가 아니라 "교체"다. `resource1()` 이 갈라 처리한다.
OVERRIDE_R1 = {0x2E: PERIOD_FILL_GALMURI} if PUNCT_SRC == "galmuri" else {}
FONT1_HDR = (0x1A54DE, 0x1A54EA)


def _pack8(rows: list[list[int]]) -> bytes:
    return bytes(sum(v << (7 - x) for x, v in enumerate(r)) for r in rows)


def layout_after_r1(cs: "Charset") -> tuple[int, int]:
    """리소스 1 을 옮긴 뒤 남는 (표 자리, 글리프 자리) — 리소스 5 가 여기서 시작한다.

    🔴 **더한 글자 수를 세서 쓴다.** 예전엔 `+ 1`(쉼표 한 자)로 박혀 있었는데 `EXTRA_R1` 이
    괄호 둘을 더 받으면서(2026-09-06, 병기 「을(를)」 때문) **셋이 됐다.** 그래서 리소스 5 의
    시작이 2칸 앞으로 밀려 **리소스 1 의 마지막 두 글자를 덮어썼다**(표 4B · 글리프 56B).
    ⚠ 덮인 게 하필 안 쓰는 반각 탁점(0xDE·0xDF)이라 **화면에 안 드러났다** — 게이트 셋도 못 봤다
    (2026-09-07, `build.Rom.verify_no_overlap` 을 세우자마자 나왔다. ss-ed1+2 가 물린 부류다).
    """
    rom = cs.rom
    r0, r1 = font.resources(rom)[:2]
    codes = font.codes(rom, r1)
    n1 = len(codes) + len([c for c in EXTRA_R1 if c not in codes])
    tbl = r0["table"] + 2 * len(cs.entries) + 2 * n1
    gl = r0["desc"] + 4 + len(cs.entries) * r0["stride"] + 4 + n1 * r1["stride"]
    return (tbl + (tbl & 1), gl + (gl & 1))


def resource1(cs: "Charset") -> list[tuple[str, int, bytes]]:
    """리소스 1(반각 8×14)에 쉼표를 더한 새 표·글리프를 표 0 이 비운 자리에 두고 헤더를 돌린다.
    → [(라벨, 자리, 바이트)] — 라벨은 build.Rom 의 허용 구간 이름."""
    rom = cs.rom
    r0, r1 = font.resources(rom)[:2]
    codes = font.codes(rom, r1)
    add = [c for c in sorted(EXTRA_R1) if c not in codes]
    override = {c: v for c, v in OVERRIDE_R1.items() if c in codes}
    if not add and not override:
        return []
    n0 = len(codes)
    g = rom[r1["glyphs"] : r1["glyphs"] + n0 * r1["stride"]]
    parts = [g[i * r1["stride"] : (i + 1) * r1["stride"]] for i in range(n0)]
    for c, rows in override.items():  # 있는 글자를 갈아 끼운다(표는 안 바뀐다)
        i = codes.index(c)
        fill = [[1 if ch == "#" else 0 for ch in row] for row in rows]
        parts[i] = _pack8(fill) + _pack8(ring(fill))
    for c in add:  # 코드 오름차순 자리에 글리프를 끼운다(표와 글리프 순서가 같아야 한다)
        i = next((k for k, x in enumerate(codes) if x > c), len(codes))
        codes.insert(i, c)
        raw = EXTRA_R1[c]
        rows = raw() if callable(raw) else raw
        fill = [[1 if ch == "#" else 0 for ch in row] for row in rows]
        parts.insert(i, _pack8(fill) + _pack8(ring(fill)))
    glyphs = b"".join(parts)
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
# 리소스 2(8×8, 1B/행, 두 면): 「ｱﾄ」(b1·c4 — 다음 레벨까지 남은 경험치 라벨) 글리프만 「남다」로.
# 🔴 도안은 **마스터가 찍은 정본**(`assets/hud_namda_16x8.txt`, 2026-09-26) — 한 픽셀도 고치지 않는다.
# 리소스 4(12×12, 2B/행, 두 면, 86칸): HUD 이름(`fd 84`, 필드·전투)의 2B 글꼴 — 파티 이름 음절로 갈아 끼운다.
FONT2_GLYPHS = (0x1BB056, 0x1BB2D6)
FONT4_HDR = (0x1A5502, 0x1A550E)
FONT4_TABLE = (0x1A6222, 0x1A62CE)
FONT4_GLYPHS = (0x1BB66E, 0x1BC68E)
LABEL_R2 = (0xB1, 0xC4)  # あと → 「남다」(PS1 정본 표기와 통일, 2026-09-06) — 왼쪽·오른쪽 8×8
LABEL_R2_DOTS = common.GAME_DIR / "assets" / "hud_namda_16x8.txt"  # 마스터 도안 16×8(채움만, 테두리는 ring)


def _pack_w(rows: list[list[int]], width: int) -> bytes:
    if width <= 8:
        return bytes(sum(v << (7 - x) for x, v in enumerate(r)) for r in rows)
    return b"".join(struct.pack(">H", sum(v << (15 - x) for x, v in enumerate(r))) for r in rows)


def label_r2_dots() -> list[list[int]]:
    """마스터 도안 → 16×8 채움 행렬. 머리 줄 뒤 `.`/`#` 16자 여덟 줄만 읽는다(다르면 죽는다)."""
    rows = [
        ln.rstrip("\n")
        for ln in LABEL_R2_DOTS.read_text(encoding="utf-8").splitlines()
        if ln and set(ln) <= {".", "#"}
    ]
    if len(rows) != 8 or any(len(r) != 16 for r in rows):
        raise SystemExit(f"{LABEL_R2_DOTS.name}: 16×8 도안이 아니다 ({len(rows)}줄)")
    return [[1 if ch == "#" else 0 for ch in r] for r in rows]


def resource2_labels() -> list[tuple[str, int, bytes]]:
    """리소스 2 의 「ｱ」「ﾄ」 자리에 마스터 도안 「남다」(16×8 → 8×8 두 칸, 테두리는 ring)."""
    rom = common.rom()
    r2 = font.resources(rom)[2]
    codes = font.codes(rom, r2)
    dots = label_r2_dots()
    out = []
    for i, code in enumerate(LABEL_R2):
        fill = [r[i * 8 : i * 8 + 8] for r in dots]
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


# ── 리소스 5 = 오프닝·엔딩용 16×16 네오둥근모 ─────────────────────────────────
# 렌더러는 스트림 안에서 글꼴을 고른다 — `fd 8N`(와이드 = 2B 코드) / `fd 0N`(반각). 핸들러 $A6C0 이
# 색인을 $FF1843(와이드)에 넣고 $9BA0 이 `lea $1A54D2` + 색인×12 로 헤더를 짚는다. 리소스 5 는 빈 슬롯이라
# **대사(리소스 0, 14×14 Galmuri)와 따로** 16×16 글꼴을 둘 수 있다. 글리프 상자가 16 이라 폭 2B/행 —
# 블리터($9C8E)는 바이트 열을 세어 돌므로 14 든 16 이든 같다.
FONT5_HDR = (0x1A550E, 0x1A551A)


def resource5(
    cs: "Charset",
    chars: set[str],
    after: tuple[int, int],
    *,
    cell: int = 14,
    source: str = "galmuri14",
) -> list[tuple[str, int, bytes]]:
    """빈 리소스 5 에 **자막 전용 글꼴**을 만든다 — (라벨, 자리, 바이트). `after` = 리소스 1 이 쓴 자리 뒤.

    자막은 피치 14(원문 그대로 한 줄 16칸)라 **Galmuri14 14×14** 가 제자리다 — 대사창이 피치 12 라
    Galmuri11 을 쓰는 것이지 자막까지 그럴 이유가 없다(유저 2026-09-06).
    ⚠ Galmuri14 는 잉크가 14행·14열을 꽉 채운다(원본 JP 글리프는 1px 여백이 있었다) ⇒ 팽창 테두리는
    칸 안에 드는 만큼만 남는다. 검은 바탕 자막이라 그림자가 조금 얇아질 뿐이다.
    """
    rom = cs.rom
    r0 = font.resources(rom)[0]
    by_code: dict[int, str] = {}
    for ch in chars:
        enc = cs.encode_char(ch)
        if len(enc) == 2:  # 반각(ASCII)은 리소스 1 이 그린다
            by_code[int.from_bytes(enc, "big")] = ch
    codes = sorted(by_code)
    # (BDF, 칸 안 위 여백, 칸 안 왼 여백) — 채움이 칸 0행·0열에 바로 닿으면 그쪽으로 팽창할
    # 테두리 자리가 없다(대사창 리소스0 의 GLYPH_TOP/GLYPH_LEFT 와 같은 함정, 2026-09-17
    # 마스터 지적 — 갈무리11 후보를 왼쪽 잘린 채로 보여드렸었다). 갈무리11 계열은 잉크가
    # 11×11 이라 상하좌우 다 1칸씩 띄워야 사방 테두리가 온전하다. 갈무리14 는 14×14 라 위만
    # 안 띄우면 위쪽이 잘린다(왼쪽은 bx 오프셋이 있어 이미 여유가 있다).
    _BDF = {
        "galmuri11": ("Galmuri11.bdf", 1, 1),
        "galmuri11bold": ("Galmuri11-Bold.bdf", 1, 1),
        "galmuri14": ("Galmuri14.bdf", 1, 0),
    }
    if source == "neodgm":

        def src(ch):
            return neodgm_fill(ch, cell, cell)

    else:
        _name, _top, _left = _BDF[source]
        _path = common.ROOT / "shared" / "fonts" / _name

        # 갈무리 계열의 ㅏㅓ 팔 1px·「…」가 가운데(일본식)인 문제는 대사창(리소스0)과 같은
        # 글꼴 파일이라 **같은 함수**로 고친다(마스터 확정 2026-09-17) — 여기서 안 태우면
        # 자막만 안 고쳐진 채로 남아 「같은 지식이 두 곳, 한쪽만 고침」이 재현된다.
        def src(ch):
            if ch == "…":
                return ellipsis_dots(cell)
            return extend_jamo_arms(_load_bdf(_path, cell, _top, _left)[ch])

    tbl_at, gl_at = after
    table = b"".join(struct.pack(">H", c) for c in codes)
    nbytes = ((cell + 7) // 8) * cell
    glyphs = bytearray()
    for c in codes:
        fill = src(by_code[c])
        glyphs += _pack_w(fill, cell) + _pack_w(ring(fill), cell)
    if tbl_at + len(table) > r0["table_end"]:
        raise SystemExit("리소스 5 표를 둘 자리가 없다(표 0 구역 초과)")
    end = r0["glyphs"] + r0["entries"] * r0["stride"]
    if gl_at + 4 + len(glyphs) > end:
        raise SystemExit(f"리소스 5 글리프가 글꼴 구역을 넘는다 ({len(codes)}자)")
    h = FONT5_HDR[0]
    desc = bytes([0x01, cell, cell, nbytes])  # 두 면 · cell×cell
    header = struct.pack(">III", tbl_at - h, tbl_at + len(table) - 4 - h, gl_at - h - 8)
    return [
        ("font5-header", h, header),
        ("font0-table", tbl_at, table),
        ("font0-glyphs", gl_at, desc + bytes(glyphs)),
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
    elif "--check" in sys.argv:
        check_frozen()
    elif "--preview" in sys.argv:
        i = sys.argv.index("--preview")
        preview(sys.argv[i + 2], Path(sys.argv[i + 1]))
