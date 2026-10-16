"""한글 글리프 — 12×12 비트맵 · 코드표 · 16B 묶음 (pce-ed1 `font.py` 와 같은 규약).

    글리프 = 12×12 → 화면용 24B(행 0~11, 2B/행, 비트 15~4). **디스크엔 11×11 비트로 묶어 16B** 로 싣는다(`pack`) —
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
PACKED_BYTES = 16
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
    if out[11] and not out[0]:  # 11×11 묶음 — 베이스라인 아래로 내려온 글자(쉼표 등)는 한 행 올린다(맨 윗행이 빈 경우만)
        out = out[1:] + [0]
    return b"".join(v.to_bytes(2, "big") for v in out)


NARROW = set(".,!?0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")  # 엔진이 ASCII 단일 바이트를 8px 반각으로 그린다(`$6448` +2) — 규칙 1-1·1-5·1-6
SPACE_PX, NARROW_PX, CELL_PX = 4, 8, 12


def adv(ch: str) -> int:
    """글자가 차지하는 가로 px — 공백 4 · 반각(ASCII) 8 · 나머지 12."""
    return SPACE_PX if ch == " " else NARROW_PX if ch in NARROW else CELL_PX


JOSA_LEAD = LEAD0 + MAX_LEADS  # F9 — 동적 조사 토큰(트레일 = TRAIL0 + 종류). 앞 글자의 받침으로 훅이 고른다
JOSA = [("은", "는"), ("이", "가"), ("을", "를"), ("과", "와")]  # (받침 있음, 없음)
JOSA_PAIRS = ["은(는)", "이(가)", "을(를)", "과(와)"]
JOSA_CHARS = "".join(a + b for a, b in JOSA)
FLAG_BATCHIM = 0x02  # 묶음 마지막 바이트의 남는 비트 — 이 글자는 받침이 있다(훅이 LASTB 로 기억한다)


JOSA_MARK = "\ue000\ue001\ue002\ue003"  # 동적 조사 표지(사설 영역) — `mark_josa` 가 병기를 바꾸고 `enc` 가 F9 토큰으로 낸다
_DIGIT_BATCHIM = {"0": 1, "1": 1, "3": 1, "6": 1, "7": 1, "8": 1}  # 읽는 소리 영·일·삼·육·칠·팔 = 받침 있음(마스터 09-26)


def _batchim_before(prev: str) -> bool | None:
    """앞 글자의 받침 — 한글은 종성, 영문 끝 = 없음, 숫자는 읽는 소리. 판정 불가(처음·공백·기호)면 None(런타임 판정)."""
    if "가" <= prev <= "힣":
        return (ord(prev) - 0xAC00) % 28 != 0
    if "A" <= prev <= "Z" or "a" <= prev <= "z":
        return False
    if prev in "0123456789":
        return prev in _DIGIT_BATCHIM
    return None


def mark_josa(text: str) -> str:
    """병기 조사(`은(는)` · `이(가)` · `을(를)` · `과(와)`)를 푼다 — 바로 앞 글자로 받침을 알면 **빌드 때** 고르고, 모르면(문장·조각 첫머리 =
    런타임 이름 뒤) 표지 한 글자로 바꿔 둔다(`enc` 가 훅용 토큰으로 낸다)."""
    out = []
    i = 0
    while i < len(text):
        for k, pair in enumerate(JOSA_PAIRS):
            if text.startswith(pair, i):
                has = _batchim_before(out[-1]) if out else None
                out.append(JOSA_MARK[k] if has is None else JOSA[k][0 if has else 1])
                i += len(pair)
                break
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def flags(ch: str) -> int:
    """글자의 훅용 플래그 — 받침 있는 한글이면 FLAG_BATCHIM."""
    return FLAG_BATCHIM if "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 else 0


def pack(g24: bytes, flag: int = 0) -> bytes:
    """24B(행당 2B, 아래 4비트 0) → 16B. 글리프는 11×11(행 11·열 11 은 늘 빈다 — 11px 원천 글꼴) —
    앞 11B = 행 0~10 의 위 8비트(열 0~7), 뒤 5B = 행 0~10 의 아래 3비트(열 8~10)를 행 순서대로 이은 33비트 + 0 채움."""
    rows = [int.from_bytes(g24[2 * r : 2 * r + 2], "big") >> 4 for r in range(12)]  # 행당 12비트(열 0 = 최상위)
    assert rows[11] == 0, "행 11 은 비어야 한다(11×11 묶음)"
    assert all(v & 1 == 0 for v in rows), "열 11 은 비어야 한다(11×11 묶음)"
    hi = bytes(v >> 4 for v in rows[:11])
    bits = 0
    for v in rows[:11]:
        bits = bits << 3 | (v >> 1) & 7
    assert flag & ~0x7F == 0
    lo = ((bits << 7) | flag).to_bytes(5, "big")  # 33비트 → 40비트(아래 7비트 = 플래그)
    return hi + lo


def unpack(p16: bytes) -> bytes:
    """`pack` 의 거꾸로 — 후킹 루틴이 하는 일과 같아야 한다(테스트가 맞댄다)."""
    bits = int.from_bytes(p16[11:16], "big") >> 7
    out = bytearray()
    for r in range(11):
        low3 = bits >> (3 * (10 - r)) & 7
        out += bytes([p16[r], low3 << 5])
    out += b"\0\0"
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
        text = mark_josa(text).replace("!!", "\x00")  # 「!!」 는 원판의 겹느낌표 글자(`81 62`, 12px 한 칸)로 — ASCII `!` 둘은 8px 칸이라 사이가 벌어진다(10-13)
        out = bytearray()
        for ch in text:
            if ch == "\x00":
                out += b"\x81\x62"
            elif ch in JOSA_MARK:  # 동적 조사 — 훅이 앞 글자의 받침으로 고른다
                k = JOSA_MARK.index(ch)
                if self.map is None:
                    self.chars.update(JOSA_CHARS)  # 두 꼴 다 정적 풀에 있어야 한다
                out += bytes([JOSA_LEAD, TRAIL0 + k])
            elif ch == " ":
                out.append(space)
            elif ch in NARROW:  # 반각 — 글리프 코드가 아니라 ASCII 한 바이트(엔진이 8px 로 그린다)
                out.append(ord(ch))
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
