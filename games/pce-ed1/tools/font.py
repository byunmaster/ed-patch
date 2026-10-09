"""한글 글리프 뱅크 + 코드표 — 문안이 쓰는 음절만 싣는다(결정 B, status.md 8절).

    글리프 = 12×12 → 화면용 24B(행 0~11, 2B/행, 비트 15~4). **뱅크엔 12비트 행으로 묶어 18B** 로 싣는다
    (`pack`, 10-07) — 리드 하나(220자)가 3,960B, 뱅크 하나에 리드 둘(0x86=F0·F1, 0x87=F2·F3) · 880자.
    후킹이 그 뱅크 꼬리의 풀기 루틴(`hook.unpack_asm`)으로 24B 로 되돌린다.
    코드  = 리드 F0+idx//220 · 트레일 0x24+idx%220 (idx 는 **정본 순서**의 번호 — `script/glyph_order.json`).
    ⚠ 트레일은 0x24 이상 — 인터프리터가 <0x24 를 옵코드로 보고, 이름칸 스캐너가 0x06 을 끝으로 본다.

원천 글꼴은 `shared/fonts/Galmuri11.bdf`(11px, 12×12 셀에 맞다). 없는 글자는 **빌드 실패**다.
"""

import json
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
# 🔴 **2뱅크**(0x86~0x87)다 — 2026-09-25 3뱅크에서 줄였다. 리소스 캐시(0x78~0x87, 16칸)에서 글리프가
#    가져간 만큼 게임의 칸이 준다. 13칸으로는 종장 맵이 넘쳐(원본이 이 자리에서 14칸을 쓴다) 장 제목 띠의
#    적재가 **조용히 실패**했다(devlog 09-25). 상한은 아래 `MAX_GLYPHS`(18B 묶음, 880자) — 넘으면 빌드가 멈춘다.
GLYPH_NBANKS = 2
GLYPH_BANK0 = 0x88 - GLYPH_NBANKS  # 캐시 맨 끝 칸들
# 🔴 **18B 묶음 저장**(10-07) — 24B 는 행마다 아래 4비트가 늘 0 이라 6B 가 빈다. 전투 문안만으로 41자가 더
#    필요한데 2뱅크 24B 로는 676자가 끝이었다(682 − 어절 루틴 자리). 묶으면 리드 하나 = 220×18 = 3,960B 라
#    **뱅크에 리드 둘이 딱 들고**(7,920B) 걸치는 글자가 없다(24B 땐 순번 341 이 뱅크 경계에 걸려 「십」이 깨졌다).
PACKED_BYTES = 18
LEADS_PER_BANK = 2
GROUP_BYTES = PER_LEAD * PACKED_BYTES  # 3960
BANK_GLYPH_END = (
    LEADS_PER_BANK * GROUP_BYTES
)  # 0x1EF0 — 뒤 272B 는 풀기 루틴(`hook.unpack_asm`, 뱅크마다) 자리
# 🔴 **마지막 글리프 뱅크 끝 `CODE_SLOTS` 칸은 코드 자리다**(10-07 반각) — 어절 줄바꿈 `hook.wordck` 과 반 칸 전진 `hook._entry_asm` 가
#   여기 산다(게임이 안 쓰는 우리 뱅크라서다. 10-07: 뱅크 0x69·0x6A·워크 RAM `$22BC~` 의 「빈 자리」는 실행 중에 다 쓰이고 있었다).
#   글리프 정본이 733자라 끝 칸들은 어차피 빈다 — 상한만 그만큼 준다(`MAX_GLYPHS`). 풀기 루틴 뒤 꼬리 168B 는 비어 있다.
CODE_SLOTS = 40
CODE_BYTES = CODE_SLOTS * PACKED_BYTES  # 504
MAX_GLYPHS = GLYPH_NBANKS * LEADS_PER_BANK * PER_LEAD - CODE_SLOTS  # 852
# 🔴 **반 칸(4px) 전진 변형 코드**(마스터 10-07) — 리드 F4~F7 = 「리드 F0~F3 의 같은 트레일 글자를 평소대로 그리고 +4px」.
#    글리프 칸을 안 먹는다(글자는 그대로, 코드만 다르다). 글리프가 이 리드를 쓰기 시작하면(상한 넘김) 빌드가 멈춘다.
#    렌더러 훅은 `hook._narrow_asm`(렌더러 입구 `$7047`).
VARIANT_LEAD0 = LEAD0 + GLYPH_NBANKS * LEADS_PER_BANK  # F4
VARIANT_LEADS = GLYPH_NBANKS * LEADS_PER_BANK  # 4
assert VARIANT_LEAD0 + VARIANT_LEADS <= 0xF8  # F8 은 반각 공백, F9 는 동적 조사 전용
# 🔴 **반각 공백**(마스터 10-07 「대사창 전체에 반각 해야지」) — 대사창(씬 대사 · 전투 문구 · 시스템 메시지)의 공백은 4px 만 간다.
#    `F8 24` = 「안 그리고 4px 전진」(렌더러 훅 `hook._narrow_asm`). 전각 공백 `81 40`(12px)은 입장 배너 가운데맞춤·고정표·라벨 패딩이
#    그대로 쓴다 — 그래서 **다른 코드**다.
HALF_SPACE = bytes([0xF8, 0x24])
# 반각 부호 — 잉크가 왼쪽 4px 안인 글리프(마스터 도트 `?` 4px 포함). 대사창에서 12px 칸에 그린 뒤 8px 되감아 4px 만 간다.
NARROW_PUNCT = ".,!?·"  # 마스터 10-07: … ～ 「」 는 전각 유지, 나머지 부호는 반각
# 🔴 리드 F9 는 **동적 조사** 전용으로 예약한다(글리프 배정에서 뺀다) — `F9 (0x24+종류)`.
#    후킹 루틴이 **직전에 그린 글자**의 받침을 보고 두 글리프 중 하나를 낸다(status.md 12절).
JOSA_LEAD = 0xF9
MAX_LEADS = JOSA_LEAD - LEAD0  # 9 → 1,980 자리, 뱅크(`MAX_GLYPHS` 880)가 먼저 찬다
JOSA_PAIRS = ["은/는", "이/가", "을/를", "과/와", "으로/로", "아/야", "이랑/랑"]
JOSA_CHARS = sorted({c for p in JOSA_PAIRS for part in p.split("/") for c in part})

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


# 11px 글꼴을 12행 셀에 앉히는 기준선 — BDF 의 y=0(베이스라인)이 셀 **11행**이다.
# 그래서 글리프 윗줄 = BASELINE_ROW − (h + yo). 🔴 이걸 안 쓰고 전부 0 행에 붙이면
# **h 가 작은 글리프가 셀 꼭대기로 뜬다** — 마침표(h=1)·쉼표(h=2,yo=−1)가 실제로 그랬다
# (2026-09-06 인게임: 「나타났다'」처럼 점이 글자 어깨에 붙어 나왔다).
BASELINE_ROW = 11

# 🔴 **`?` 는 마스터 도트로 바꾼다**(2026-09-27, 반각 C안) — 반각(4px, 0~3열) 폭에 맞춘 전용 글리프.
# `.local/work/inbox/pce-ed1/master-dots-question-4x12.txt` 그대로(4×12, 행 11 기준선·빈 줄) — 픽셀 그대로 굽는다.
# `shared/fonts/Galmuri11.bdf`(공용)의 원래 `?`(0~4열, 5px 폭)를 대체한다 — 공용 파일은 안 건드리고
# 이 게임의 `glyph()` 에서만 가로챈다.
QUESTION_4PX_ROWS = [
    ".##.",
    "#..#",
    "#..#",
    "...#",
    "..#.",
    ".#..",
    ".#..",
    ".#..",
    "....",
    ".#..",
    ".#..",
    "....",
]


# 🔴 **「…」는 한국식 바닥(글자 아랫줄)에 점 셋**(마스터 10-08, 전 기종 공통 — 일본식 가운데 점 금지). 갈무리의 「…」 는 12행 칸의
#   5행(한가운데)에 찍혀 있어 마침표(10행)와 높이가 달랐다 — 마침표와 같은 행에 점 셋(열 1·5·9). 오프닝·엔딩 자막(`opening_sub.render_line`)은 이미 이 꼴이다.
ELLIPSIS_FLOOR_ROW = 10
ELLIPSIS_FLOOR_COLS = (1, 5, 9)


def _ellipsis_floor() -> bytes:
    rows = [0] * (GLYPH_BYTES // 2)
    for c in ELLIPSIS_FLOOR_COLS:
        rows[ELLIPSIS_FLOOR_ROW] |= 0x8000 >> c
    return b"".join(v.to_bytes(2, "big") for v in rows)


def _question_4px() -> bytes:
    out = []
    for row in QUESTION_4PX_ROWS:
        v = 0
        for col, c in enumerate(row):
            if c == "#":
                v |= 0x8000 >> col
        out.append(v)
    return b"".join(v.to_bytes(2, "big") for v in out)


# 🔴 **겹느낌표는 한 칸에 그린다**(10-07, 마스터 「회심의 일격! !」 — 「!!」 전각 벌어짐). 이 창은 글자마다 12px 칸이라
#   부호 둘이 「! !」로 벌어진다. 반각 렌더러(C안)를 기다리지 않고 **두 부호를 4px 간격으로 한 글리프에** 굽고
#   인코딩 때 바꿔 넣는다(`ligate`). 화면 폭은 오히려 한 칸 준다 — 조판·줄바꿈은 두 칸으로 세니 넘칠 일은 없다.
LIGATURES = {"!!": "‼", "!?": "⁉"}
# 엔진이 수치를 찍는 숫자 표(`$69D3`, 전각 SJIS 열 쌍)를 우리 글리프 코드로 바꾼다 — 그래서 열 글자가 늘 글리프 뱅크에 있어야 한다.
DIGIT_CHARS = "0123456789"
LIGATURE_STEP = 4  # 둘째 부호를 오른쪽으로 민 픽셀


def ligate(text: str) -> str:
    for a, b in LIGATURES.items():
        text = text.replace(a, b)
    return text


def glyph(ch: str) -> bytes:
    """한 글자 → 24B. 세로는 **베이스라인에 맞추고**(BDF `yo`) 가로는 왼쪽 정렬."""
    if ch == "?":
        return _question_4px()
    if ch == "…":
        return _ellipsis_floor()
    lig = next((k for k, v in LIGATURES.items() if v == ch), None)
    if lig is not None:
        a, b = (glyph(c) for c in lig)
        rows = [
            int.from_bytes(a[i : i + 2], "big")
            | (int.from_bytes(b[i : i + 2], "big") >> LIGATURE_STEP)
            for i in range(0, GLYPH_BYTES, 2)
        ]
        return b"".join((v & 0xFFF0).to_bytes(2, "big") for v in rows)
    pk = packed_glyphs().get(ch) if 0xE000 <= ord(ch) <= 0xF8FF else None
    if pk is not None:
        return pk
    g = _load_bdf().get(ord(ch))
    if g is None:
        raise KeyError(f"글꼴에 없는 글자: {ch!r} (U+{ord(ch):04X})")
    w, h, xo, yo, rows = g
    nbytes = (w + 7) // 8
    out = [0] * 12
    top = BASELINE_ROW - (h + yo)
    for i, r in enumerate(rows[:12]):
        y = top + i
        if not 0 <= y < 12:
            continue  # 셀 밖으로 나가는 행(디센더 등)은 버린다
        v = (r << (16 - nbytes * 8)) & 0xFFFF  # BDF 행은 바이트 단위로 왼쪽 정렬돼 있다
        v = (v >> max(xo, 0)) & 0xFFF0 if xo > 0 else v & 0xFFF0
        out[y] = v
    if all(v == 0 for v in out):
        raise ValueError(f"글리프가 비었다: {ch!r}")
    return b"".join(v.to_bytes(2, "big") for v in out)


# ── 촘촘히 짠 줄(전용 글자) ──────────────────────────────────────────────────
# 이 창은 모든 글자를 12px 칸에 하나씩 놓아 공백도 한 칸이다(반각 없음 — 인터프리터가 두 글자를
# 12px 셀 둘 = 타일 셋으로 짠다, status 2절). 13칸을 넘는 한 줄은 **줄 전체를 한 장으로 그려 12px 씩
# 잘라 전용 글자**로 넣는다 — 공백만 6px 로 줄이고 글자는 평소처럼 12px 피치(마스터 2026-09-25,
# 종장 카드 「종장  그리고 영웅들의 전설」 15칸 → 13칸). 정본에선 `⟦…⟧` 로 적고 조판 전에 푼다.
PACK_RE = re.compile("⟦(.*?)⟧")
PACK_SPACE_PX = 6
PACKED = {"종장  그리고 영웅들의 전설": 0xE000}  # 문안 → 전용 글자 첫 코드포인트(사용자 영역)
_packed_cache: dict[str, bytes] | None = None


def _packed_cells(text: str) -> list[bytes]:
    x, strip = 0, [0] * 12
    placed = []
    for ch in text:
        if ch == " ":
            x += PACK_SPACE_PX
            continue
        placed.append((x, glyph(ch)))
        x += 12
    ncell = (x + 11) // 12
    width = ncell * 12
    for gx, g in placed:
        for r in range(12):
            v = int.from_bytes(g[2 * r : 2 * r + 2], "big") >> 4  # 12비트, MSB = 왼쪽 픽셀
            strip[r] |= v << (width - 12 - gx)
    cells = []
    for k in range(ncell):
        rows = [((strip[r] >> (width - 12 - 12 * k)) & 0xFFF) << 4 for r in range(12)]
        cells.append(b"".join(v.to_bytes(2, "big") for v in rows))
    return cells


def packed_glyphs() -> dict[str, bytes]:
    global _packed_cache
    if _packed_cache is None:
        _packed_cache = {}
        for text, base in PACKED.items():
            for k, cell in enumerate(_packed_cells(text)):
                _packed_cache[chr(base + k)] = cell
    return _packed_cache


def expand_packed(text: str) -> str:
    """`⟦문안⟧` → 전용 글자 열. 등록 안 된 문안이면 빌드 실패."""

    def one(m):
        body = m.group(1)
        if body not in PACKED:
            raise KeyError(f"전용 글자로 등록 안 된 줄: {body!r} — font.PACKED 에 넣어라")
        n = len(_packed_cells(body))
        return "".join(chr(PACKED[body] + k) for k in range(n))

    return PACK_RE.sub(one, text)


def code_of(idx: int) -> bytes:
    if idx >= MAX_GLYPHS:
        raise ValueError(f"글리프 {idx} — 글리프 뱅크({MAX_GLYPHS}자)를 넘는다")
    lead = LEAD0 + idx // PER_LEAD
    if lead >= JOSA_LEAD:
        raise ValueError("리드가 조사 예약(F9)에 닿았다")
    return bytes([lead, TRAIL0 + idx % PER_LEAD])


def josa_code(pair: str) -> bytes:
    return bytes([JOSA_LEAD, TRAIL0 + JOSA_PAIRS.index(pair)])


# 숫자를 읽는 소리 — 받침은 이 음절로 가른다(0 = 영). 영문·부호는 무받침(비트 0).
DIGIT_READING = dict(zip("0123456789", "영일이삼사오육칠팔구", strict=True))


def batchim_tables(order: list[str]) -> tuple[bytes, bytes]:
    """글리프 순서 → (받침 비트맵, ㄹ받침 비트맵) 각 128B. 비트 1 = 받침 있음."""
    has = bytearray((MAX_GLYPHS + 7) // 8)
    rieul = bytearray((MAX_GLYPHS + 7) // 8)
    for i, ch in enumerate(order):
        if ch in DIGIT_READING:  # 끝 숫자는 읽는 소리대로(마스터 09-26): 레스1을 · 레스2를
            f = (ord(DIGIT_READING[ch]) - 0xAC00) % 28
            if f:
                has[i >> 3] |= 1 << (i & 7)
                if f == 8:
                    rieul[i >> 3] |= 1 << (i & 7)
        elif "가" <= ch <= "힣":
            f = (ord(ch) - 0xAC00) % 28
            if f:
                has[i >> 3] |= 1 << (i & 7)
                if f == 8:
                    rieul[i >> 3] |= 1 << (i & 7)
    return bytes(has), bytes(rieul)


def josa_offsets(table: dict[str, bytes]) -> bytes:
    """조사 종류별 (받침용, 무받침용) 글리프 **코드**(트레일·리드) 2B × 2 × 7 = 28B — 후킹이 보통 글자 길로 낸다.

    ⚠ 두 글자짜리 조사(으로·이랑)는 **첫 글자만** 표에 넣고 둘째 글자는 문안이 그대로 들고 있는다 —
    루틴이 글리프 하나만 낼 수 있어서다(`으로/로` → 문안에 `{으로/로}로` 로 쓰지 않는다,
    encode 가 첫 글자를 조사 코드로 두 번째를 보통 글자로 낸다).
    """
    out = bytearray()
    for pair in JOSA_PAIRS:
        a, b = pair.split("/")
        for part in (a, b):
            c = table[part[0]]
            out += bytes([c[1], c[0]])
    return bytes(out)


def _index_of(ch: str, table: dict[str, bytes]) -> int:
    c = table[ch]
    return (c[0] - LEAD0) * PER_LEAD + (c[1] - TRAIL0)


GLYPH_ORDER = None  # 지연 로드 — `script/glyph_order.json`


def _order_canon() -> list[str]:
    """글리프 배정 순서 **정본**(커밋된다).

    🔴 **코드가 세이브에 남는다.** 게임은 파티원 이름을 우리 글리프 코드 그대로 BRAM 에 적는다
    (실측 2026-09-06: 유저 세이브 +0x244 에 `f0e0 f1d7 06`). 그래서 배정 순서가 바뀌면
    **이전 세이브의 이름이 다른 글자로 읽힌다** — 「세리오스」가 「서린온을」이 됐다.
    옛 방식(`sorted(쓰는 글자)`)은 문안을 한 글자만 늘려도 뒤 코드가 통째로 밀린다.
    ⇒ 순서를 **커밋되는 정본**으로 못 박고, 새 글자는 **뒤에 덧붙인다**(앞은 안 흔든다).
    """
    global GLYPH_ORDER
    if GLYPH_ORDER is None:
        f = Path(__file__).resolve().parents[1] / "script" / "glyph_order.json"
        GLYPH_ORDER = json.loads(f.read_text())["order"] if f.exists() else []
    return GLYPH_ORDER


def build_table(chars) -> tuple[dict[str, bytes], bytes]:
    """음절 집합 → (글자→2B 코드, 글리프 뱅크 바이트(24KB, 0 패딩)). 조사 글자는 늘 포함한다.

    배정은 **정본 순서**를 따른다(`_order_canon`). 정본에 없는 글자가 있으면 **빌드가 죽는다** —
    `python3 tools/freeze_glyphs.py` 로 뒤에 덧붙이고 커밋한다(코드가 안 밀린다).
    """
    need = set(chars) | set(JOSA_CHARS) | set(LIGATURES.values()) | set(DIGIT_CHARS)
    canon = _order_canon()
    missing = sorted(need - set(canon))
    if missing:
        raise ValueError(
            f"글리프 정본에 없는 글자 {len(missing)}자: {''.join(missing[:20])}…\n"
            "  → python3 games/pce-ed1/tools/freeze_glyphs.py 로 덧붙이고 커밋해라.\n"
            "  (순서를 바꾸면 **이전 세이브의 이름이 깨진다** — 코드가 BRAM 에 남는다)"
        )
    order = list(canon)
    if len(order) > MAX_GLYPHS:
        raise ValueError(f"음절 {len(order)}자 — 상한 {MAX_GLYPHS}. 결정 B 재검토(status.md 8절)")
    table = {ch: code_of(i) for i, ch in enumerate(order)}
    bank = bytearray(GLYPH_NBANKS * 0x2000)
    for i, ch in enumerate(order):
        at = glyph_at(i)
        bank[at : at + PACKED_BYTES] = pack(glyph(ch))
    bank = bytes(bank)
    build_table.order = order  # 받침 표를 만들 때 쓴다
    return table, bank


def needs_glyph(ch: str) -> bool:
    """우리 글리프가 필요한 글자 — SJIS 전각 2바이트로 못 적는 것 전부(한글 · ASCII 부호·숫자·라틴)."""
    if ch in (" ", "\n", "\f"):
        return False
    if ch == "…":
        return True  # 🔴 BIOS 글꼴의 「…」(SJIS 8163)은 가운데 점이다 — 한국식 바닥 꼴은 우리 글리프로(`_ellipsis_floor`, 마스터 10-08)
    if 0xE000 <= ord(ch) <= 0xF8FF:
        return True  # 🔴 사용자 영역 — cp932 가 F040~ 외자로 인코딩해 **우리 글리프 코드(리드 F0~)와 겹친다**
    try:
        b = ch.encode("cp932")
    except UnicodeEncodeError:
        return True
    return len(b) != 2 or b[0] < 0x24


JOSA_TOKEN = re.compile("|".join(re.escape(p) for p in JOSA_PAIRS))


def variant(code: bytes) -> bytes:
    """글리프 코드 → 「그 글자를 그리고 +4px」 변형 코드(리드만 `VARIANT_LEADS` 만큼 올린다)."""
    assert LEAD0 <= code[0] < VARIANT_LEAD0, code.hex()
    return bytes([code[0] + VARIANT_LEAD0 - LEAD0, code[1]])


def encode(
    text: str, table: dict[str, bytes], half_space: bool = False, msg: bool = False
) -> bytes:
    """우리 문안 → 게임 바이트.

    `msg` — 대사창 문안(씬 대사 · 전투 문구 · 시스템 메시지)이다: 공백은 **반각**(`HALF_SPACE`, 4px) 코드로 쓴다.
    아니면 전각 공백(`81 40`, 12px) — 입장 배너·고정표·라벨 패딩.

    `half_space` — 글리프 바로 뒤의 공백을 **반 칸**으로 쓴다: 그 글자를 변형 코드(`variant`, +4px)로 바꿔 공백 바이트를
    따로 안 먹는다(칸이 바이트로 고정된 이름표에서 「성스러운 지팡이」를 7칸 14B 에 넣는다). 글리프 뒤가 아닌 공백(앞 · 연속 ·
    부호 뒤)은 평소처럼 전각 공백이다.

    `은/는`·`이/가`·`을/를`·`과/와`·`으로/로`·`아/야`·`이랑/랑` 은 **동적 조사 토큰**이다 —
    앞말이 런타임에 정해지는 자리(이름·아이템)에 그대로 쓴다. 두 글자 조사는 첫 글자만 토큰이 되고
    둘째 글자는 보통 글자로 나간다(`으로/로` → `F9 28` + `로`).
    """
    text = ligate(text)
    out = bytearray()
    pos = 0
    for m in JOSA_TOKEN.finditer(text):
        out += encode(text[pos : m.start()], table, half_space, msg) if m.start() > pos else b""
        pair = m.group()
        out += josa_code(pair)
        rest = pair.split("/")[0][1:]  # 받침용의 둘째 글자(으로→로, 이랑→랑)
        if rest:
            out += table[rest[0]]
        pos = m.end()
    if pos:
        return bytes(out) + encode(text[pos:], table, half_space, msg)
    glyph_end = -1  # 바로 앞 글자가 우리 글리프였나(그 코드가 out 끝 2B)
    for ch in text:
        if ch in table:
            out += table[ch]
            glyph_end = len(out)
        elif ch == "\n":
            out.append(0x01)
        elif ch == " ":
            if half_space and glyph_end == len(out) and LEAD0 <= out[-2] < VARIANT_LEAD0:
                out[-2:] = variant(bytes(out[-2:]))  # 글자 + 반 칸
            else:
                out += HALF_SPACE if msg else b"\x81\x40"  # 전각 한 칸(12px) · 대사창은 반각(4px)
        elif needs_glyph(ch):
            raise ValueError(f"글리프 표에 없는 글자: {ch!r} — 정본에서 모은 집합이 아니다")
        else:
            out += ch.encode("cp932")
    return bytes(out)


def glyph_at(idx: int) -> int:
    """순번 → 글리프 뱅크들(이어 붙인 것) 안 바이트 자리. 뱅크 = 리드 둘씩, 리드 안은 18B 씩."""
    g, k = divmod(idx, PER_LEAD)
    return (g // LEADS_PER_BANK) * 0x2000 + (g % LEADS_PER_BANK) * GROUP_BYTES + k * PACKED_BYTES


def pack(g: bytes) -> bytes:
    """24B(행마다 hi·lo, lo 아래 4비트 0) → 18B(두 행 = 3B: hiA · loA|hiB>>4 · hiB<<4|loB>>4)."""
    assert len(g) == GLYPH_BYTES
    out = bytearray()
    for r in range(0, 12, 2):
        ha, la, hb, lb = g[2 * r], g[2 * r + 1], g[2 * r + 2], g[2 * r + 3]
        assert not (la & 0x0F or lb & 0x0F), "12 칸 밖 잉크"
        out += bytes([ha, la | hb >> 4, (hb << 4 & 0xF0) | lb >> 4])
    return bytes(out)


def unpack(b: bytes) -> bytes:
    out = bytearray()
    for i in range(0, PACKED_BYTES, 3):
        b0, b1, b2 = b[i : i + 3]
        out += bytes([b0, b1 & 0xF0, (b1 << 4 | b2 >> 4) & 0xFF, b2 << 4 & 0xF0])
    return bytes(out)


if __name__ == "__main__":
    t, bank = build_table("안녕하세요한글")
    for ch, c in t.items():
        print(ch, c.hex())
    print(len(bank))
