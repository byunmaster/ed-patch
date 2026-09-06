"""한글 글리프 뱅크 + 코드표 — 문안이 쓰는 음절만 싣는다(결정 B, status.md 8절).

    글리프 = 12×12 → 24B(행 0~11, 2B/행, 비트 15~4). 뱅크 0x85~0x87 에 순서대로(24B × ≤1,024).
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
MAX_GLYPHS = 3 * 0x2000 // GLYPH_BYTES  # 1,024
# 🔴 리드 F9 는 **동적 조사** 전용으로 예약한다(글리프 배정에서 뺀다) — `F9 (0x24+종류)`.
#    후킹 루틴이 **직전에 그린 글자**의 받침을 보고 두 글리프 중 하나를 낸다(status.md 12절).
JOSA_LEAD = 0xF9
MAX_LEADS = JOSA_LEAD - LEAD0  # 9 → 1,980 자리, 뱅크 셋(1,024)이 먼저 찬다
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


def glyph(ch: str) -> bytes:
    """한 글자 → 24B. 세로는 **베이스라인에 맞추고**(BDF `yo`) 가로는 왼쪽 정렬."""
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


def code_of(idx: int) -> bytes:
    if idx >= MAX_GLYPHS:
        raise ValueError(f"글리프 {idx} — 뱅크 셋(1,024자)을 넘는다")
    lead = LEAD0 + idx // PER_LEAD
    if lead >= JOSA_LEAD:
        raise ValueError("리드가 조사 예약(F9)에 닿았다")
    return bytes([lead, TRAIL0 + idx % PER_LEAD])


def josa_code(pair: str) -> bytes:
    return bytes([JOSA_LEAD, TRAIL0 + JOSA_PAIRS.index(pair)])


def batchim_tables(order: list[str]) -> tuple[bytes, bytes]:
    """글리프 순서 → (받침 비트맵, ㄹ받침 비트맵) 각 128B. 비트 1 = 받침 있음."""
    has = bytearray(MAX_GLYPHS // 8)
    rieul = bytearray(MAX_GLYPHS // 8)
    for i, ch in enumerate(order):
        if "가" <= ch <= "힣":
            f = (ord(ch) - 0xAC00) % 28
            if f:
                has[i >> 3] |= 1 << (i & 7)
                if f == 8:
                    rieul[i >> 3] |= 1 << (i & 7)
    return bytes(has), bytes(rieul)


def josa_offsets(table: dict[str, bytes]) -> bytes:
    """조사 종류별 (받침용, 무받침용) 글리프 오프셋 2B × 2 × 7 = 28B.

    ⚠ 두 글자짜리 조사(으로·이랑)는 **첫 글자만** 표에 넣고 둘째 글자는 문안이 그대로 들고 있는다 —
    루틴이 글리프 하나만 낼 수 있어서다(`으로/로` → 문안에 `{으로/로}로` 로 쓰지 않는다,
    encode 가 첫 글자를 조사 코드로 두 번째를 보통 글자로 낸다).
    """
    out = bytearray()
    for pair in JOSA_PAIRS:
        a, b = pair.split("/")
        for part in (a, b):
            idx = _index_of(part[0], table)
            out += (idx * GLYPH_BYTES).to_bytes(2, "little")
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
    need = set(chars) | set(JOSA_CHARS)
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
    bank = b"".join(glyph(ch) for ch in order)
    bank += b"\0" * (3 * 0x2000 - len(bank))
    build_table.order = order  # 받침 표를 만들 때 쓴다
    return table, bank


def needs_glyph(ch: str) -> bool:
    """우리 글리프가 필요한 글자 — SJIS 전각 2바이트로 못 적는 것 전부(한글 · ASCII 부호·숫자·라틴)."""
    if ch in (" ", "\n", "\f"):
        return False
    try:
        b = ch.encode("cp932")
    except UnicodeEncodeError:
        return True
    return len(b) != 2 or b[0] < 0x24


JOSA_TOKEN = re.compile("|".join(re.escape(p) for p in JOSA_PAIRS))


def encode(text: str, table: dict[str, bytes]) -> bytes:
    """우리 문안 → 게임 바이트.

    `은/는`·`이/가`·`을/를`·`과/와`·`으로/로`·`아/야`·`이랑/랑` 은 **동적 조사 토큰**이다 —
    앞말이 런타임에 정해지는 자리(이름·아이템)에 그대로 쓴다. 두 글자 조사는 첫 글자만 토큰이 되고
    둘째 글자는 보통 글자로 나간다(`으로/로` → `F9 28` + `로`).
    """
    out = bytearray()
    pos = 0
    for m in JOSA_TOKEN.finditer(text):
        out += encode(text[pos : m.start()], table) if m.start() > pos else b""
        pair = m.group()
        out += josa_code(pair)
        rest = pair.split("/")[0][1:]  # 받침용의 둘째 글자(으로→로, 이랑→랑)
        if rest:
            out += table[rest[0]]
        pos = m.end()
    if pos:
        return bytes(out) + encode(text[pos:], table)
    for ch in text:
        if ch in table:
            out += table[ch]
        elif ch == "\n":
            out.append(0x01)
        elif ch == " ":
            out += b"\x81\x40"  # 공백은 전각 한 칸 — 반각은 이 창에 없다(3절)
        elif needs_glyph(ch):
            raise ValueError(f"글리프 표에 없는 글자: {ch!r} — 정본에서 모은 집합이 아니다")
        else:
            out += ch.encode("cp932")
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
