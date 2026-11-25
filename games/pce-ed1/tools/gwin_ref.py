"""비모달 자막 **런타임 글리프 조립의 파이썬 참조 구현**(제품 공사 안 B, 마스터 10-30 「B로 진행해보자」).

틱이 6502 로 할 일을 그대로 파이썬으로 적은 것이다 — 입력은 **게임이 읽는 바이트**(씬 블록 안 번역 줄의 글리프 코드)와 **글리프 뱅크 바이트**(상주 + 그 블록의 동적 칸)뿐이고,
출력은 `gwin.make_window`(문자열 → 글리프 → 타일)와 **바이트까지 같은** 글자 타일 압축본이다(`tools/tests/test_gwin_ref.py` 가 음성 쪽 전량으로 대조).

코드 형식(`font.py`):
  · 글리프 = 리드 F0~F3 + 트레일 0x24+k → 순번 idx = (리드−F0)×220 + k, 뱅크 안 자리 = `font.glyph_at(idx)`, 18B 패킹(`font.unpack` → 24B = 12행 × 2B, 위 12비트).
  · `F8 24` = 반각 공백(4px, 안 그림). `F4~F7` = 같은 글자 + 4px(조립기는 모름 — 문안이 안 쓴다). `F9 xx` = 동적 조사(받침 판정이 런타임이라 자막에서 안 쓴다 — 거부).
  · 전진 px: 공백·반각 부호 4 · 「」·합자 8 · ASCII 숫자 8 · 나머지 12 — 예외 코드 표(`adv_exceptions`)만 있으면 된다.
  · 줄 안 글자는 12행 글리프를 16행 줄의 **2행부터** 놓는다(위 2행 · 아래 2행 비움). 8px 기둥으로 자르면 줄 하나 = 기둥마다 타일 둘(위 8행 · 아래 8행).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font
import gwin


def adv_exceptions(table: dict[str, bytes]) -> dict[bytes, int]:
    """코드 → 전진 px 중 12 가 아닌 것(글자표에서). 6502 쪽 표가 이것이다."""
    out = {}
    for ch, code in table.items():
        a = gwin.adv(ch)
        if a != 12:
            out[bytes(code)] = a
    out[font.HALF_SPACE] = 4
    return out


def glyph_rows(bank: bytes, code: bytes) -> list[int]:
    """코드 → 12행 정수(위 12비트 — 왼쪽이 최상위). 글리프 뱅크(상주 + 동적 칸을 덮은 것)에서 18B 를 꺼내 푼다."""
    lead, trail = code[0], code[1]
    assert font.LEAD0 <= lead < font.LEAD0 + font.GLYPH_NBANKS * font.LEADS_PER_BANK, code.hex()
    idx = (lead - font.LEAD0) * font.PER_LEAD + (trail - font.TRAIL0)
    at = font.glyph_at(idx)
    g = font.unpack(bank[at : at + font.PACKED_BYTES])
    return [int.from_bytes(g[2 * r : 2 * r + 2], "big") >> 4 for r in range(12)]


def render_line(line: bytes, bank: bytes, adv_exc: dict[bytes, int]) -> tuple[list[bytearray], int]:
    """줄 바이트 → (16행 × 기둥 바이트, 기둥 수). 바이트 단위로만 쓴다(6502 가 하는 방식: 글자마다 행 12개를 비트 위치에 맞춰 두 바이트에 얹는다)."""
    codes, i = [], 0
    while i < len(line):
        c = bytes(line[i : i + 2])
        assert len(c) == 2 and c[0] >= 0x24, f"글리프 코드가 아니다: {line[i:i+2].hex()}"
        assert c[0] != font.JOSA_LEAD, "동적 조사 토큰은 자막이 못 그린다"
        codes.append(c)
        i += 2
    w = sum(adv_exc.get(c, 12) for c in codes)
    ncol = (w + 7) // 8
    buf = [bytearray(ncol + 2) for _ in range(16)]  # 끝 글자가 12px 로 그려져도 모자라지 않게 두 바이트 여유
    x = 0
    for c in codes:
        if c != font.HALF_SPACE:
            rows = glyph_rows(bank, c)
            sh = x % 8
            col = x // 8
            for r in range(12):
                v = rows[r] << 4  # 16비트 왼쪽 정렬(위 12비트 잉크)
                v = (v << 8) >> sh  # 24비트 — 첫 바이트가 기둥 col
                buf[2 + r][col] |= (v >> 16) & 0xFF
                buf[2 + r][col + 1] |= (v >> 8) & 0xFF
                buf[2 + r][col + 2] |= v & 0xFF
        x += adv_exc.get(c, 12)
    return buf, ncol


def tiles_of(lines: list[tuple[bytes, int]], bank: bytes, adv_exc: dict[bytes, int]) -> bytes:
    """(줄 바이트, 첫 행) 목록 → 글자 타일 압축본(타일마다 8B — 줄 → 기둥 → 위·아래 반). `gwin.make_window` 가 만드는 것과 같은 순서."""
    out = bytearray()
    for line, _top in lines:
        buf, ncol = render_line(line, bank, adv_exc)
        for c in range(ncol):
            for half in (0, 1):
                out += bytes(buf[half * 8 + y][c] for y in range(8))
    return bytes(out)


FULL_PX = 13 * 12  # 줄이 이 폭에 닿으면 인터프리터가 스스로 넘긴다(`typeset.FULL`)


def message_pages(msg: bytes, adv_exc: dict[bytes, int]) -> tuple[bytes | None, list[list[bytes]]]:
    """게임이 읽는 메시지 바이트(`compose` 결과, 점프가 있으면 `narration_gates.flat_msg` 로 편 것) → (화자 이름 코드열 | None, 쪽마다 줄 바이트 목록).
    쪽 = `05`/종료까지 · 줄 = `01` 또는 **폭이 13칸(156px)에 닿는 자동 넘김**. 글리프가 아닌 옵코드(색 `1D` 등)는 건너뛴다(자막은 색을 안 낸다)."""
    import messages as M

    ops = {**M.TEXT_OPS, **M.OTHER_OPS}
    i, name = 0, None
    if msg[:1] == b"\x1f":  # 화자 머리 1F 이름 04
        j = 1
        while j < len(msg) and msg[j] >= 0x24:
            j += 2
        if j < len(msg) and msg[j] == 4:
            name = bytes(msg[1:j])
            i = j + 1
    pages: list[list[bytes]] = []
    lines: list[bytes] = []
    cur = bytearray()
    px = 0

    def end_line():
        nonlocal cur, px
        lines.append(bytes(cur))
        cur, px = bytearray(), 0

    while i < len(msg):
        c = msg[i]
        if c >= 0x24:
            code = bytes(msg[i : i + 2])
            a = adv_exc.get(code, 12)
            if px + a > FULL_PX and cur:
                end_line()
            cur += code
            px += a
            i += 2
            if px >= FULL_PX:
                end_line()
            continue
        if c in (0, 6, 7):
            break
        if c == 1:
            if cur:
                end_line()
            i += 1
            continue
        if c == 5:
            if cur:
                end_line()
            pages.append(lines)
            lines = []
            i += 1
            continue
        i += ops.get(c, 1)
    if cur:
        end_line()
    if lines:
        pages.append(lines)
    return name, pages
