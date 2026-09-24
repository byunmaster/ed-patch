"""파일 선택 화면의 「ファイルがありません」 상자 — 압축 그래픽 코덱 (2026-09-16).

이 상자는 문자열이 아니라 **압축된 타일 그림 + 압축된 BAT 표** 둘이다(devlog 09-16 (9)~).
글자를 그리는 건 BIOS 도 우리 훅도 아니라서, 상자를 한글로 바꾸려면 그림을 **다시 압축해
제자리에** 넣어야 한다. 자원 셋이 뱅크 0x7A(rel 106~109) 끝에 붙어 있다:

    +1D06  모드 1B(0x02) + 스트림 512B   타일 68장(2,176B)   ← JSR $48CB  desc `06 1d 32 00 7b 44 00 0f`
    +1F07  모드 1B(0x02) + 스트림        BAT 표 17×3(없음)   ← JSR $4999  desc `07 1f 32 40 07 03 11 03`
    +1F40  모드 1B(0x02) + 스트림        BAT 표 18×3(손상)   ← JSR $4999  desc `40 1f 32 40 06 03 12 03`

디스크립터는 뱅크 0x78 의 코드에 인라인으로 박혀 있다(+0x0025 · +0x0436 · +0x0444).
🔴 **포맷은 디스어셈블(뱅크 0x68 $479F · $45F1 · $4657)에서 옮겼고, 세 자원 모두 게임이 VRAM 에
푼 결과(에뮬 덤프)와 바이트까지 같음을 확인했다** — `tests/test_boxpack.py`.

## 스트림 (`$479F`)

플래그 비트는 **필요할 때** 스트림에서 한 바이트씩 꺼내 MSB 부터 쓴다(리터럴·인덱스 바이트와
섞여 들어간다). 링 버퍼 256B(`$3F00`), 쓰기 포인터는 **0xEF 에서 시작**.

    1 + 바이트           리터럴
    0 + 링인덱스 + 4비트  링[인덱스..] 에서 (n+2) 바이트 복사 (2~17)

⚠ 원본 데이터는 **아직 안 쓴 링 자리(초기 0)를 참조**하기도 한다(초기 0 을 0-런으로 쓴다).
우리 인코더는 그 재주를 쓰지 않는다 — 링 초기화에 기대지 않는 쪽이 안전하다.

## 뒤처리 (`$45F1` 재배치 → `$4657` 델타 필터)

원 스트림 출력은 **플레인별로 8B 씩** 묶여 있다(타일 = 4플레인 32B · BAT = 2플레인 16B).
이를 끼워 넣어(interleave) 16B 줄로 만든 뒤, 줄마다 첫 2B 는 반전(⊕FF), 나머지는 2B 앞과 XOR.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

RING = 256
RING_START = 0xEF
MAX_MATCH = 17
MIN_MATCH = 2
LINE = 16


# ── 스트림 ──────────────────────────────────────────────────────────────────
def decode_stream(src: bytes, n: int) -> tuple[bytes, int]:
    """`$479F` 그대로. (출력, 소비한 바이트 수)."""
    ring = bytearray(RING)
    w = RING_START
    out = bytearray()
    pos = 0
    sh = 0
    bits = 1  # $0A 초기값 1 → 첫 호출에서 리필
    cnt = 0
    ridx = 0

    def nextbit():
        nonlocal sh, bits, pos
        bits -= 1
        if bits == 0:
            bits = 8
            sh = src[pos]
            pos += 1
        sh = (sh << 1) & 0x1FF
        return (sh >> 8) & 1

    while len(out) < n:
        if cnt == 0:
            if nextbit():
                a = src[pos]
                pos += 1
            else:
                ridx = src[pos]
                pos += 1
                a = 0
                for _ in range(4):
                    a = ((a << 1) | nextbit()) & 0xFF
                cnt = a + 2
                a = ring[ridx]
                ridx = (ridx + 1) & 0xFF
                cnt -= 1
        else:
            a = ring[ridx]
            ridx = (ridx + 1) & 0xFF
            cnt -= 1
        ring[w] = a
        w = (w + 1) & 0xFF
        out.append(a)
    return bytes(out), pos


class _Writer:
    """플래그 바이트를 디코더가 읽는 자리에 놓는다 — 비트가 처음 필요할 때 그 자리에 예약."""

    def __init__(self):
        self.buf = bytearray()
        self.flagpos = -1
        self.nbits = 8  # 가득 찬 상태로 시작 → 첫 비트에서 새 플래그 바이트

    def bit(self, b):
        if self.nbits == 8:
            self.buf.append(0)
            self.flagpos = len(self.buf) - 1
            self.nbits = 0
        if b:
            self.buf[self.flagpos] |= 0x80 >> self.nbits
        self.nbits += 1

    def byte(self, x):
        self.buf.append(x & 0xFF)


def encode_stream(data: bytes) -> bytes:
    """최적 파싱(리터럴 9비트 · 매치 13비트, 고정 비용이라 DP 로 정확히 최소).

    매치는 **이미 쓴 출력** 중 거리 1~255 만 참조한다(링 초기값·덮어쓴 자리는 안 믿는다).
    """
    n = len(data)
    INF = 1 << 30
    cost = [INF] * (n + 1)
    step = [None] * (n + 1)  # (길이, 거리) — 거리 0 = 리터럴
    cost[n] = 0
    for i in range(n - 1, -1, -1):
        best = cost[i + 1] + 9
        pick = (1, 0)
        maxlen = min(MAX_MATCH, n - i)
        if maxlen >= MIN_MATCH:
            for d in range(1, min(RING - 1, i) + 1):
                s = i - d
                # 겹치는 매치(d < 길이)도 된다 — 디코더가 한 바이트씩 쓰며 읽는다
                ln = 0
                while ln < maxlen and data[s + ln] == data[i + ln]:
                    ln += 1
                if ln < MIN_MATCH:
                    continue
                for k in range(MIN_MATCH, ln + 1):
                    c = cost[i + k] + 13
                    if c < best:
                        best, pick = c, (k, d)
        cost[i] = best
        step[i] = pick
    wr = _Writer()
    i = 0
    while i < n:
        k, d = step[i]
        if d == 0:
            wr.bit(1)
            wr.byte(data[i])
        else:
            w = (RING_START + i) & 0xFF
            wr.bit(0)
            wr.byte((w - d) & 0xFF)
            v = k - 2
            for b in (8, 4, 2, 1):
                wr.bit(v & b)
        i += k
    return bytes(wr.buf)


# ── 뒤처리 ──────────────────────────────────────────────────────────────────
def _interleave(blk: bytes, planes: int) -> bytes:
    """플레인별 8B 묶음 → 16B 줄(플레인 0/1 끼움, 2/3 끼움)."""
    out = bytearray(planes * 8)
    for p in range(planes):
        base = (p & 1) + LINE * (p >> 1)
        for k in range(8):
            out[base + 2 * k] = blk[p * 8 + k]
    return bytes(out)


def _deinterleave(win: bytes, planes: int) -> bytes:
    out = bytearray(planes * 8)
    for p in range(planes):
        base = (p & 1) + LINE * (p >> 1)
        for k in range(8):
            out[p * 8 + k] = win[base + 2 * k]
    return bytes(out)


def _filter(win: bytes) -> bytes:
    out = bytearray(len(win))
    for i in range(len(win)):
        out[i] = (~win[i]) & 0xFF if (i & 0xF) < 2 else win[i] ^ out[i - 2]
    return bytes(out)


def _unfilter(out: bytes) -> bytes:
    win = bytearray(len(out))
    for i in range(len(out)):
        win[i] = (~out[i]) & 0xFF if (i & 0xF) < 2 else out[i] ^ out[i - 2]
    return bytes(win)


def unpack(src: bytes, nbytes: int, planes: int) -> tuple[bytes, int]:
    """모드 바이트 **뒤** 스트림 → 게임이 VRAM 에 놓는 바이트. (결과, 소비 바이트 수)."""
    blk = planes * 8
    assert nbytes % blk == 0, nbytes
    raw, used = decode_stream(src, nbytes)
    out = b"".join(_filter(_interleave(raw[i : i + blk], planes)) for i in range(0, nbytes, blk))
    return out, used


def pack(vram: bytes, planes: int) -> bytes:
    """VRAM 바이트 → 스트림(모드 바이트 없음)."""
    blk = planes * 8
    assert len(vram) % blk == 0, len(vram)
    raw = b"".join(
        _deinterleave(_unfilter(vram[i : i + blk]), planes) for i in range(0, len(vram), blk)
    )
    return encode_stream(raw)


# ── 이 게임의 자원 셋 ────────────────────────────────────────────────────────
RES_BANK = 0x7A
TILES_OFF = 0x1D06  # 모드 바이트 자리
MAP1_OFF = 0x1F07
MAP2_OFF = 0x1F40
REGION_END = 0x1F88  # 세 자원이 끝나는 자리(원본 map2 스트림 끝 +1). 그 뒤는 남의 것으로 본다
NTILES = 68
TILE_BYTES = 32
MAP1_WH = (17, 3)
MAP2_WH = (18, 3)
MODE = 0x02
DESC = {  # 뱅크 0x78 안 디스크립터(인라인 8B) 오프셋 — JSR 바로 뒤
    "tiles": 0x0028,
    "map1": 0x0439,
    "map2": 0x0447,
}


def map_nbytes(w: int, h: int) -> int:
    """BAT 표는 16B 줄 단위로 푼다 — w×h 워드를 줄 단위로 올림."""
    n = w * h * 2
    return (n + LINE - 1) // LINE * LINE


def words(b: bytes) -> list[int]:
    return [b[i] | (b[i + 1] << 8) for i in range(0, len(b), 2)]


# ── 캔버스 — 상자 픽셀을 다룬다(0=바깥·14=채움·15=흰 테두리/글자) ─────────────
MSG1_W, MSG1_H = 17, 3
MSG1_TOP = 7  # 잉크 세로 자리(원문 실측 행6~17 대), 갈무리11 11행이 그 안에 들어간다


def frame(w: int, h: int = 3) -> np.ndarray:
    """빈 상자(테두리만). 행0·h*8-1·열0·w*8-1 = 바깥(0), 그 안쪽 테두리 1px = 흰(15), 나머지 = 채움(14)."""
    ww = w * 8
    hh = h * 8
    cv = np.full((hh, ww), 14, np.uint8)
    cv[0, :] = 0
    cv[hh - 1, :] = 0
    cv[1, 1 : ww - 1] = 15
    cv[hh - 2, 1 : ww - 1] = 15
    cv[:, 0] = 0
    cv[:, ww - 1] = 0
    cv[1 : hh - 1, 1] = 15
    cv[1 : hh - 1, ww - 2] = 15
    return cv


def px_tile(px: np.ndarray) -> bytes:
    """8×8 색인 픽셀(0/14/15) → 4bpp 32B 타일(플레인 분리, `$45BC` 형식)."""
    t = bytearray(32)
    for r in range(8):
        for x in range(8):
            v = int(px[r, x])
            b = 7 - x
            for i in range(4):
                if (v >> i) & 1:
                    t[(0 if i < 2 else 16) + r * 2 + (i & 1)] |= 1 << b
    return bytes(t)


def tile_px(t: bytes) -> np.ndarray:
    """32B 4bpp 타일 → 8×8 색인 픽셀(px_tile 의 역함수)."""
    px = np.zeros((8, 8), np.uint8)
    for r in range(8):
        p = [t[r * 2], t[r * 2 + 1], t[16 + r * 2], t[16 + r * 2 + 1]]
        for x in range(8):
            b = 7 - x
            px[r, x] = sum(((p[i] >> b) & 1) << i for i in range(4))
    return px


def typeset_ink(text: str, font, dy: int, gap: int = 1, space: int = 5, period_adv: int = 3):
    """한 줄 잉크 비트맵(글꼴 행수 × 폭px). 전각 고정폭이 아니라 **잉크 기준 가변폭**이다
    (이 상자는 원문도 가변폭 손글씨체라 장 제목 띠와 달리 자간을 맞추지 않는다).

    🔴 **자간(`gap`)은 "같은 낱말 안, 두 실글자 사이"에만 준다** — 다음 글자가 공백이거나
    마침표/쉼표면 0 이다. 낱말 사이는 이미 `space` 가 있고 마침표 앞은 바짝 붙는 게
    자연스러워, 그 자리에 자간까지 더하면 **낱말 간격이 조용히 `space+gap`으로 늘어나고
    폭을 공짜로 낭비한다**(09-16 실측 — 이 낭비 때문에 자간1px 전체가 VRAM 타일 천장을
    못 넘던 걸 이 수정 하나로 넘겼다: 80/80타일, devlog 참고)."""
    from shared import fonts as _fonts

    cols = []
    pen = 0
    chars = list(text)
    for i, ch in enumerate(chars):
        if ch == " ":
            pen += space
            continue
        g = font.bits(ch, dy=dy, rows=_fonts.ROWS, width=_fonts.WIDTH)
        _, xs = np.nonzero(g)
        x0, x1 = int(xs.min()), int(xs.max())
        nxt = chars[i + 1] if i + 1 < len(chars) else None
        if ch in ".,":
            cols.append((pen + 1, g[:, x0 : x1 + 1]))
            pen += period_adv + gap
        else:
            this_gap = gap if nxt is not None and nxt not in ".," and nxt != " " else 0
            cols.append((pen, g[:, x0 : x1 + 1]))
            pen += (x1 - x0 + 1) + this_gap
    # ⚠ 폭은 **실제로 놓인 조각들의 오른쪽 끝**으로 잰다 — `pen - gap` 로 트림하면(옛 코드)
    # **마지막 글자가 자간을 안 받는 경우**(마침표 아닌 글자로 끝나는 문안 등, 09-16 실측
    # `typeset_ink('저장된 파일이 없습니다', ...)` 에서 뒤 글자가 잘려 모양이 안 맞았다)
    # 존재하지도 않은 자간을 트림해 **폭이 줄고 마지막 글자가 잘린다.**
    width = max((max(x + g.shape[1] for x, g in cols) if cols else 1), 1)
    ink = np.zeros((_fonts.ROWS, width), np.uint8)
    for x, g in cols:
        ink[:, x : x + g.shape[1]] |= g.astype(np.uint8)
    return ink


def compose(
    w: int, ink: np.ndarray, top: int = MSG1_TOP, h: int = 3, x_offset: int | None = None
) -> np.ndarray:
    """빈 상자 위에 잉크를 얹는다. 기본은 가운데 정렬(`x_offset=None`) — 명시하면 그 x 로.

    ⚠ 안 들어가면 assert 로 죽는다(칸 수 재확인). `x_offset` 을 **8×8 격자 위상 탐색**에
    쓴다 — 가로로 1px 만 밀어도 타일 경계가 통째로 다시 쪼개져 고유 타일 수가 달라진다
    (09-16 실측, 조사 오프셛 32위상 탐색과 같은 수법). 너비 안에서 2~`w*8-2-ink폭` 사이
    아무 값이나 된다."""
    cv = frame(w, h)
    ww = w * 8
    x0 = x_offset if x_offset is not None else (ww - ink.shape[1]) // 2
    assert 2 <= x0 and x0 + ink.shape[1] <= ww - 2, ("잉크가 안 들어간다", ink.shape[1], ww - 4)
    for y in range(ink.shape[0]):
        for x in range(ink.shape[1]):
            if ink[y, x]:
                cv[top + y, x0 + x] = 15
    return cv


def catalog_and_map(cv: np.ndarray, base_tiles: list[bytes], w: int, h: int):
    """캔버스 → (전체 타일 카탈로그, BAT 워드 목록). `base_tiles` 는 재사용 우선순위(원본 68장).

    ⚠ **조밀(dense) 모드** — `base_tiles` 전부를 예약해서 카탈로그 맨 앞에 통째로 둔다.
    msg2 가 실제로 쓰는 타일이 68장 중 49장뿐이라(09-16 실측) 이 모드는 나머지 19장 자리를
    낭비한다 — 그 자리까지 쓰려면 `sparse_catalog_and_map`(예약/자유 분리)을 쓴다.
    """
    catalog = list(base_tiles)
    index = {t: i for i, t in enumerate(base_tiles)}
    m = []
    for r in range(h):
        for c in range(w):
            t = px_tile(cv[r * 8 : (r + 1) * 8, c * 8 : (c + 1) * 8])
            if t not in index:
                index[t] = len(catalog)
                catalog.append(t)
            m.append(0x4000 | (0x7B0 + index[t]))
    return catalog, m


def reserved_indices(orig_tiles: list[bytes], *word_lists: list[int]) -> set[int]:
    """`word_lists`(BAT 워드들, 예: msg2 전체 + msg1 원본 테두리) 가 **실제로 참조하는**
    `orig_tiles` 색인 집합 — 이 자리들은 원본 픽셀을 그대로 지켜야 한다(그 워드를 안
    건드리므로). 나머지(68 미만 안 쓰는 자리 + 68 이상)는 새 내용에 자유롭게 쓸 수 있다."""
    idx = set()
    for words_ in word_lists:
        for w in words_:
            i = (w & 0xFFF) - 0x7B0
            if 0 <= i < len(orig_tiles):
                idx.add(i)
    return idx


def sparse_catalog_and_map(
    cv: np.ndarray,
    orig_tiles: list[bytes],
    reserved: set[int],
    w: int,
    h: int,
    max_total: int = 80,
):
    """희소 카탈로그 — **예약 색인(`reserved`)은 원본 픽셀을 그 자리에 그대로 두고**, 나머지
    자리(68장 중 예약 안 된 것 + 68~`max_total`-1)를 새 내용에 오름차순으로 내준다.

    🔴 예약 안 된 원본 타일도 **번호(색인)는 그대로 유지**한다 — `msg2`·테두리가 자기
    번호로 참조하니 **번호를 밀면 안 된다.** 빈 번호만 새 내용으로 갈아 끼운다.
    """
    slots: list[bytes | None] = [None] * max_total
    for i in reserved:
        slots[i] = orig_tiles[i]
    index = {t: i for i, t in enumerate(slots) if t is not None}
    free = iter(i for i in range(max_total) if i not in reserved)
    m = []
    for r in range(h):
        for c in range(w):
            t = px_tile(cv[r * 8 : (r + 1) * 8, c * 8 : (c + 1) * 8])
            if t not in index:
                try:
                    i = next(free)
                except StopIteration as e:
                    raise AssertionError(
                        f"타일 {len(index) + 1}장(예약 {len(reserved)}장 포함) — "
                        f"예산 {max_total}장을 넘는다"
                    ) from e
                slots[i] = t
                index[t] = i
            m.append(0x4000 | (0x7B0 + index[t]))
    n_used = max(index.values()) + 1 if index else 0
    # 예약 색인 중 「더 큰 색인이 필요해져」 사이에 낀 미사용 자리 — 아무도 안 읽으니 내용은
    # 안 가리지만, 순차 블릿이라 자리는 채워야 한다. 원본이 있던 자리(<68)는 그 바이트로,
    # 그 밖(≥68)은 0 으로 — 둘 다 **의미 없는 채움**이다(어떤 BAT 워드도 이 색인을 안 가리킨다).
    for i in range(n_used):
        if slots[i] is None:
            slots[i] = orig_tiles[i] if i < len(orig_tiles) else b"\x00" * TILE_BYTES
    return slots[:n_used], m, index


# ── 뱅크 0x7B 재배치 — msg1(「ファイルがありません」) 한글화 ────────────────
#
# 압축 예산이 뱅크 0x7A 안에서 완전히 막혔다(devlog 09-16 (10)(11)(12)) — 그 뱅크는
# 8B 이상 0-런이 한 곳도 없이 다른 자원 둘과 꽉 차 있다. 마스터 승인(09-16)으로 **뱅크
# 0x7B 재배치**로 간다 — 라이브 실측(emucap, 디스어셈블)으로 안전한 길을 확인했다:
#
#   · MPR5(=뱅크 0x7A)·MPR6(=뱅크 0x7A+1=0x7B) 는 **항상 짝으로 매핑된다**
#     (뱅크 0x68 `$447B`: `TAM #$20` 로 MPR5, 바로 뒤 `$4494 INC/TAM #$40` 로 MPR6).
#     ⇒ 뱅크 0x7B 는 **이미 살아 있는 창**이고, 새 TAM 코드가 전혀 필요 없다.
#   · 소스 포인터는 `$445C: STX $06/STY $07` 로 세워지는데, 실측값이 **$A000 + 디스크립터
#     오프셛(바이트 0-1, LE)** 를 정확히 재현한다(타일: X=6·Y=$BD = $A000+0x1D06 = $BD06).
#     ⇒ 오프셛을 **0x2000 이상**으로 주면 $C000 이상(=MPR6=뱅크 0x7B)으로 **코드 변경 없이**
#     자연히 넘어간다. **디스크립터의 나머지 필드(포맷 바이트 0x32 등)는 그대로 둔다** —
#     `(포맷바이트&0x1F)` 가 곧 상대 뱅크 오프셛(`$3EF1`+이 값=최종 뱅크)이라 안 건드리면
#     같은 디스패치 경로·같은 최종 뱅크쌍을 그대로 쓴다.
#   · 뱅크 0x7B 자체는 **원본 디스크에서 0x000~0x22B(521B)만 쓰고 그 뒤(0x22C~0x1FFF,
#     7,636B)는 전부 0**(rel 110 의 1섹터, rel 111~113 은 통째로 0) — 우리 실측
#     확인(disc 원본 fresh-read). **그 521B 는 우리가 안 건드린다**(다른 화면/맥락의
#     자원일 수 있다 — devlog 09-16 패치 노트대로 "이 자원만 쓰는지" 를 존중한다).
#
# msg2(원본 그대로)·뱅크 0x7A 의 세 원본 자원은 **전부 손 안 댄다**(오래된 tiles/map1
# 자리는 죽은 바이트로 남지만 아무도 더는 참조하지 않는다 — "그대로 두는 게 안전하다").
RELOC_BANK = 0x7B
RELOC_OFF = 0x300  # 뱅크 0x7B 안 시작 오프셛(0x22C 뒤 여유 있게, 7636B 중 사용은 1KB 안팎)
RELOC_DESC_BASE = 0x2000  # $A000(뱅크 0x7A/MPR5 시작) 대비, 이 값 이상이면 MPR6(뱅크 0x7B)

# 뱅크 0x78 안 인라인 디스크립터의 소스 오프셛 필드(LE 2B) 위치 — 오프셛만 바뀐다
TILES_DESC_SRC_OFF = 0x28  # `JSR $48CB` 바로 뒤 8B 디스크립터의 byte0-1(소스 오프셛)
TILES_DESC_COUNT_OFF = 0x2D  # 같은 디스크립터의 byte5 — 타일 **개수**($48CB 가 $FC 에 실어
# VDC 로 블릿할 타일 수로 쓴다). 🔴 **이걸 안 올리면 BAT 는 새 인덱스를 가리키는데 VRAM
# 타일 패턴은 원본 68장만 써져 새 글자가 빈 칸(검정)으로 보인다** — 09-16 라이브 실측으로
# 잡았다(BAT 는 맞는데 화면이 빈 상자였다).
MAP1_DESC_SRC_OFF = 0x439  # `JSR $4999`(msg1 BAT) 바로 뒤 디스크립터의 byte0-1
MSG1_TEXT = "파일이 없습니다."  # 마스터 최종 확정 문안(09-16) — 11자 원안은 진짜 가운데
# (top=6·7)에서 예산(80장)을 못 지켜 축약안으로 확정됐다(devlog 09-16 (18)~(20)).


def _rel_off(bank: int, off: int) -> tuple[int, int]:
    """뱅크:오프셛 → (rel, 섹터 안 오프셛). `build.py:_main()` 과 같은 식(본 프로그램,
    rel 34 부터 뱅크 0x68 4섹터씩) — 여기 다시 둔 건 이 모듈이 build.py 를 안 끌어오기
    위해서다(순환 임포트 방지, YAGNI 상 둘째 소비자가 없어 shared 로 안 올렸다)."""
    return 34 + (bank - 0x68) * 4 + off // 2048, off % 2048


def original_tiles() -> list[bytes]:
    """원본 디스크(`originals/`, 읽기 전용)에서 상자 타일 68장을 그대로 읽는다.
    "원본이 어땠는가"를 묻는 읽기는 originals 에서 한다(루트 CLAUDE.md 빌드 규율)."""
    import common

    bank_rel = _rel_off(RES_BANK, 0)[0]
    bank = common.track_data(
        bank_rel, 4
    )  # 뱅크 0x7A = 4섹터 = 8,192B, TILES_OFF 는 그 안 바이트 오프셛
    assert bank[TILES_OFF] == MODE
    out, _ = unpack(bank[TILES_OFF + 1 :], NTILES * TILE_BYTES, 4)
    return [out[i * TILE_BYTES : (i + 1) * TILE_BYTES] for i in range(NTILES)]


def original_fixed_words() -> tuple[list[int], list[int]]:
    """원본 디스크에서 (msg2 전체 51워드, msg1 원본 테두리(열0·열`MSG1_W-1`) 6워드)를 읽는다.
    `reserved_indices()` 에 그대로 넘기면 「msg2·테두리가 실제로 참조하는 원본 68장 자리」
    가 나온다 — 09-16 실측(도트판 예산 물음)으로 **49장**이었다."""
    import common

    bank_rel = _rel_off(RES_BANK, 0)[0]
    bank = common.track_data(bank_rel, 4)

    assert bank[MAP2_OFF] == MODE
    m2_bytes, _ = unpack(bank[MAP2_OFF + 1 :], map_nbytes(*MAP2_WH), 2)
    m2_words = words(m2_bytes)[: MAP2_WH[0] * MAP2_WH[1]]

    assert bank[MAP1_OFF] == MODE
    m1_bytes, _ = unpack(bank[MAP1_OFF + 1 :], map_nbytes(*MAP1_WH), 2)
    m1_words = words(m1_bytes)[: MAP1_WH[0] * MAP1_WH[1]]
    w, h = MAP1_WH
    border_words = [m1_words[r * w + c] for r in range(h) for c in (0, w - 1)]

    return m2_words, border_words


def fixed_tiles_export() -> dict:
    """도트판(관리자 웹 도구)이 「이 칸은 기존 타일과 같음(공짜)」를 판정할 수 있게,
    예약 타일 목록을 JSON 으로 낼 준비를 한다 — 8×8 색인 픽셀(0=바깥·14=채움·15=흰).
    `apply(...)`로 파일까지 쓰려면 `export_fixed_tiles_json()`."""
    orig = original_tiles()
    m2_words, border_words = original_fixed_words()
    reserved = sorted(reserved_indices(orig, m2_words, border_words))
    return {
        "max_total_tiles": MAX_TOTAL_TILES,
        "reserved_count": len(reserved),
        "budget_for_new": MAX_TOTAL_TILES - len(reserved),
        "reserved_indices": reserved,
        "tiles": [tile_px(orig[i]).tolist() for i in reserved],
    }


def export_fixed_tiles_json(path: str) -> dict:
    import json

    data = fixed_tiles_export()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


MAX_TOTAL_TILES = 0x800 - 0x7B0  # = 80. 🔴 **압축 예산과 별개인 VRAM 주소 천장**이다 —
# 타일 번호 × 16워드 가 타일 패턴 주소라, 타일 0x800(=원본기준 +80번째)부터 워드주소
# 0x8000 로 VRAM(32K워드) 밖을 나가 **0 으로 감겨 BAT 자신을 덮어쓴다**(09-16 라이브 실측:
# 114장으로 구웠더니 상자 위쪽 테두리만 뜨고 아래 두 줄이 깨졌다 — 감긴 타일이 BAT 를
# 건드린 것). ⇒ 뱅크 0x7B 재배치로 압축 바이트는 넉넉해졌지만 **총 타일 수는 여전히
# 최대 80장(새 타일 ≤ 12장)** 이다 — 이 천장은 자리를 옮겨도 안 없어진다.

# 갈무리7(자간0·낱말간격2·dy-2·top8) — 09-16 실측 79장(새 12장 미만)으로 두 예산(압축
# 바이트·VRAM 타일 천장) 을 **모두** 지키는 후보였지만, 원문 크기(11자)로는 진짜 가운데
# (top=6·7)가 예산을 못 지켜 마스터가 문안을 축약안(8자)으로 최종 확정했다 — 아래는 그
# 확정값(devlog 09-16 (18)~(20)). 갈무리11(원문 11자 크기)은 새 타일 46장이 필요해
# **VRAM 천장을 넘는다** — 그래서 문안 축약 없이는 못 쓴다.
MSG1_FONT_NAME = "Galmuri11"
MSG1_FONT_DY = -3
MSG1_FONT_GAP = 1  # 자간 1px — 마스터 확정(09-16 (15))
MSG1_FONT_SPACE = 6  # 낱말 간격 6px(반각) — 마스터 확정(09-16 (20)), 장 제목 띠와 같은 규칙
MSG1_FONT_TOP = 6  # 진짜 한가운데(위6·아래6행) — 마스터 확정(09-16 (20)), 77/80장


def build_msg1_relocation(
    orig_tiles: list[bytes],
    *,
    font_name: str = MSG1_FONT_NAME,
    dy: int = MSG1_FONT_DY,
    gap: int = MSG1_FONT_GAP,
    space: int = MSG1_FONT_SPACE,
    top: int = MSG1_FONT_TOP,
    x_offset: int | None = None,
) -> dict:
    """마스터 문안을 조판 → 재배치 자원 일습을 만든다. 기본값은 `MSG1_FONT_*`(갈무리7,
    VRAM 타일 천장 80장 안에 드는 안전값). 매개변수로 다른 글꼴/자간도 시험할 수 있다 —
    예: 갈무리11 원문 크기(`font_name="Galmuri11", dy=-3, gap=0, space=6, top=8`)도
    **희소 카탈로그**(`sparse_catalog_and_map`, 예약 49장 재사용)로는 79장/679B 로 든다
    (09-16 실측, devlog 참고) — 다만 정본은 아직 갈무리7 그대로다(마스터 판단 대기).

    🔴 **희소 모드를 쓴다** — msg2·테두리가 실제 참조하는 49장만 예약하고 나머지(19+12=31장)
    자리는 새 내용에 내준다(`sparse_catalog_and_map`). 조밀 모드(`catalog_and_map`, 68장
    전부 예약)보다 자리를 넉넉히 쓸 수 있어 **같은 글꼴도 더 헐렁하게 들어간다.**

    반환: `tiles_block`·`map1_block`(모드바이트 포함 바이트열) · 새 디스크립터 오프셛 둘 ·
    확인용 `catalog`(전체 타일 — 예약 색인 자리는 `orig_tiles`의 그 색인과 바이트까지
    같아야 한다) · `map1_words`(재구성 검산용).
    """
    from shared import fonts as _fonts

    font = _fonts.galmuri(font_name)
    ink = typeset_ink(MSG1_TEXT, font, dy, gap=gap, space=space)
    cv = compose(MSG1_W, ink, top, MSG1_H, x_offset=x_offset)
    m2_words, border_words = original_fixed_words()
    reserved = reserved_indices(orig_tiles, m2_words, border_words)
    catalog, m1, _index = sparse_catalog_and_map(
        cv, orig_tiles, reserved, MSG1_W, MSG1_H, max_total=MAX_TOTAL_TILES
    )
    for i in reserved:
        assert catalog[i] == orig_tiles[i], f"예약 색인 {i} 의 원본 픽셀이 안 지켜졌다"
    assert len(catalog) <= MAX_TOTAL_TILES, (
        f"타일 {len(catalog)}장 — VRAM 천장 {MAX_TOTAL_TILES}장을 넘는다(BAT 를 덮어쓴다)"
    )

    def map_bytes(m, w, h):
        n = map_nbytes(w, h) // 2
        m = m + [m[-1]] * (n - len(m))
        return b"".join(x.to_bytes(2, "little") for x in m)

    tiles_stream = pack(b"".join(catalog), 4)
    map1_stream = pack(map_bytes(m1, MSG1_W, MSG1_H), 2)
    tiles_block = bytes([MODE]) + tiles_stream
    map1_block = bytes([MODE]) + map1_stream

    tiles_src = RELOC_DESC_BASE + RELOC_OFF
    map1_src = RELOC_DESC_BASE + RELOC_OFF + len(tiles_block)
    total = RELOC_OFF + len(tiles_block) + len(map1_block)
    assert total <= 0x2000, f"뱅크 0x7B 여유(8,192B)를 넘는다: {total}B"
    assert RELOC_OFF >= 0x22C, "원본이 쓰는 0x000~0x22B 를 침범한다"

    return {
        "cv": cv,
        "catalog": catalog,
        "map1_words": m1,
        "tiles_block": tiles_block,
        "map1_block": map1_block,
        "tiles_src_offset": tiles_src,
        "map1_src_offset": map1_src,
        "region_len": len(tiles_block) + len(map1_block),
    }


def verify_msg1_relocation(built: dict) -> None:
    """되읽기 — 새 블록을 실제 게임 방식(모드바이트+`unpack`)으로 다시 풀어 캔버스가
    의도와 바이트까지 같은지 확인한다. `build.py` 가 굽기 직전/직후에 부른다."""
    catalog = built["catalog"]
    nt = len(catalog)
    tiles_out, used_t = unpack(built["tiles_block"][1:], nt * 32, 4)
    assert built["tiles_block"][0] == MODE
    assert tiles_out == b"".join(catalog), "타일 왕복 불일치"
    assert used_t == len(built["tiles_block"]) - 1, "타일 스트림 소비량 불일치"

    map1_out, used_m1 = unpack(built["map1_block"][1:], map_nbytes(MSG1_W, MSG1_H), 2)
    assert built["map1_block"][0] == MODE
    exp_words = built["map1_words"]
    n = map_nbytes(MSG1_W, MSG1_H) // 2
    exp_words = exp_words + [exp_words[-1]] * (n - len(exp_words))
    exp = b"".join(x.to_bytes(2, "little") for x in exp_words)
    assert map1_out == exp, "map1 왕복 불일치"
    assert used_m1 == len(built["map1_block"]) - 1, "map1 스트림 소비량 불일치"

    got_words = words(map1_out)
    cv2 = np.zeros((MSG1_H * 8, MSG1_W * 8), np.uint8)
    for r in range(MSG1_H):
        for c in range(MSG1_W):
            idx = (got_words[r * MSG1_W + c] & 0xFFF) - 0x7B0
            cv2[r * 8 : (r + 1) * 8, c * 8 : (c + 1) * 8] = tile_px(
                tiles_out[idx * 32 : (idx + 1) * 32]
            )
    assert np.array_equal(cv2, built["cv"]), "재구성 캔버스가 의도와 다르다"


def apply_msg1_relocation(f, touched: list[tuple[int, int]]) -> str:
    """ISO 에 제자리 되쓰기(뱅크 0x7B 새 자리 + 뱅크 0x78 디스크립터 오프셛 둘).
    뱅크 0x7A · msg2 · 그 밖의 모든 바이트는 손 안 댄다. `build.py` 가 부른다."""
    import common

    from shared.disc import mode1

    built = build_msg1_relocation(original_tiles())
    verify_msg1_relocation(built)

    # 1) 뱅크 0x7B 새 자리(제자리 되쓰기 전 반드시 0 이어야 한다 — 원본이 쓰던 자리가 아님)
    rel, off = _rel_off(RELOC_BANK, RELOC_OFF)
    lba = common.T2_SECTOR + rel
    block = built["tiles_block"] + built["map1_block"]
    mode1.write_at(
        f,
        lba,
        common.USER,
        off,
        block,
        label="msg1 relocation (bank 0x7B)",
        expect=b"\0" * len(block),
    )
    touched.append((lba, 1))

    # 1-b) 타일 개수 필드(byte5) — 68 → 새 카탈로그 크기. 이게 없으면 VRAM 에 68장만 써진다.
    n_new = len(built["catalog"])
    assert n_new <= 255, f"타일 {n_new}장 — 1B 필드를 넘는다"
    rel_cnt, off_cnt = _rel_off(0x78, TILES_DESC_COUNT_OFF)
    lba_cnt = common.T2_SECTOR + rel_cnt
    mode1.write_at(
        f,
        lba_cnt,
        common.USER,
        off_cnt,
        bytes([n_new]),
        label="msg1 tiles descriptor 개수(byte5)",
        expect=bytes([NTILES]),
    )
    touched.append((lba_cnt, 1))

    # 2) 디스크립터 소스 오프셛 둘(뱅크 0x78) — 포맷 바이트(0x32)는 안 건드린다.
    #    `expect` 는 원본이 가리키던 **옛 오프셛**(TILES_OFF·MAP1_OFF, 이 모듈 위쪽 상수) —
    #    이게 없으면 「배치가 밀렸는데 그 자리에 그냥 쓰는」 사고를 못 막는다.
    for label, src_off_field, old_src, new_src in (
        ("msg1 tiles descriptor 오프셛", TILES_DESC_SRC_OFF, TILES_OFF, built["tiles_src_offset"]),
        ("msg1 map1 descriptor 오프셛", MAP1_DESC_SRC_OFF, MAP1_OFF, built["map1_src_offset"]),
    ):
        rel78, off78 = _rel_off(0x78, src_off_field)
        lba78 = common.T2_SECTOR + rel78
        mode1.write_at(
            f,
            lba78,
            common.USER,
            off78,
            new_src.to_bytes(2, "little"),
            label=label,
            expect=old_src.to_bytes(2, "little"),
        )
        touched.append((lba78, 1))

    return (
        f"msg1 재배치: 뱅크 0x7B +0x{RELOC_OFF:03X}, 타일 {len(built['catalog'])}장"
        f" · 블록 {built['region_len']}B · 디스크립터 오프셛 0x{built['tiles_src_offset']:04X}"
        f"/0x{built['map1_src_offset']:04X}"
    )
