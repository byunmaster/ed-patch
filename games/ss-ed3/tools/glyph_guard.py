"""글리프 읽기 감시 — 「이 번호대 슬롯을 글자 그리기가 읽는가」를 실행 중 0회로 증명한다(헤드리스, 롬 불변).

    from glyph_guard import install, hits
    install(h, [(lo_idx, hi_idx), ...])   # 하네스 `h` 의 RAM 에 감시를 얹는다(디스크·롬은 안 건드린다)
    n, last = hits(h)                     # 읽힌 횟수와 마지막 주소
    unchanged(h)                          # 감시 구간 바이트가 설치 때와 같은가(쓰기 감시)

원리(10-24): 한자 글리프는 **함수 하나**가 읽는다 — `0x0604119A`(SJIS → 색인 → `KANJI12.FON` RAM 사본 `0x2B6004 + 색인×18`).
폰트 기준 주소 리터럴(`0x06041254`)이 코드 전체에서 이 함수 하나뿐이다(리터럴 전수 스캔). 그래서 그 함수의 주소 계산 직후에
`jsr @r1`(리터럴을 감시 코드 주소로 바꿔 둔 r1)로 감시 코드를 끼운다 — 감시 코드는 원래 `add r1,r8 · mov r8,r5` 를 대신하고, 주소가
감시 구간 `[lo, hi)` 안이면 카운터를 올리고 마지막 주소를 적는다. 감시 코드·카운터는 엔진이 안 쓰는 HWRAM(0.BIN 끝 뒤)에 둔다.
쓰기 쪽은 감시 구간 바이트를 점검마다 처음과 견준다.
⚠ 코드 예약 칸에 코드가 앉은 **빌드**에서는 `unchanged` 가 의미 없다(변수가 쓰인다) — 그땐 `hits` 만 본다(글자 그리기가 코드 칸을 글리프로 읽는가).
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subtitle_stub as SS

FONT_BASE = (
    0x002B6004  # KANJI12.FON 이 RAM 에 올라오는 자리(실측: 글리프 283·377·7000·7807 의 위치로 확인)
)
STRIDE = 18
SITE = 0x060411D8  # `add r1,r8` — 주소 계산 직후
LIT = 0x06041254  # 폰트 기준 주소 리터럴(이 함수만 쓴다)
SITE_ORIG = bytes.fromhex("381c")  # add r1,r8
JSR_R1 = bytes.fromhex("410b")
COUNTER = 0x06085000  # 엔진이 안 쓰는 HWRAM(0.BIN 끝 뒤 · 리터럴 전수 스캔에서 참조 0)
STUB = 0x06085040  # 감시 코드 자리 — 카운터 바로 뒤 HWRAM(엔진이 안 쓴다)


def _code(ranges):
    a = SS.Asm(STUB)
    a.movl_pc(1, "BASE")
    a.addr(8, 1)  # add r1,r8
    a.mov(5, 8)  # mov r8,r5
    pool = {"BASE": FONT_BASE, "CNT": COUNTER}
    for k, (lo, hi) in enumerate(ranges):
        pool[f"LO{k}"] = FONT_BASE + lo * STRIDE
        pool[f"HI{k}"] = FONT_BASE + hi * STRIDE
        a.movl_pc(2, f"LO{k}")
        a.cmp_hs(8, 2)  # r8 >= lo ?
        a.bf(f"n{k}")
        a.movl_pc(2, f"HI{k}")
        a.cmp_hs(8, 2)  # r8 >= hi ?
        a.bt(f"n{k}")
        a.movl_pc(1, "CNT")
        a.movl_at(2, 1)
        a.add(2, 1)
        a.movl_to(1, 2)
        a.movl_to_d(1, 8, 4)  # mov.l r8,@(4,r1)
        a.bra("done")
        a.nop()
        a.label(f"n{k}")
    a.label("done")
    a.rts()
    a.nop()
    code, _ = a.resolve(pool)
    assert STUB % 4 == 0
    return code


def install(h, ranges):
    """감시를 얹는다. `ranges` = [(lo, hi)] 글리프 색인(hi 미포함)."""
    assert h.peek(SITE, 2) in (SITE_ORIG, JSR_R1), h.peek(SITE, 2).hex()
    assert h.peek(COUNTER, 8) == bytes(8), "카운터 자리가 0 이 아니다"
    h.poke(STUB, _code(ranges))
    h.poke(LIT, struct.pack(">I", STUB))
    h.poke(SITE, JSR_R1)
    h.guard_ref = [
        (lo, hi, bytes(h.peek(FONT_BASE + lo * STRIDE, (hi - lo) * STRIDE))) for lo, hi in ranges
    ]


def hits(h):
    n, last = struct.unpack(">II", h.peek(COUNTER, 8))
    return n, last


def unchanged(h):
    """감시 구간이 설치 때와 같은가(쓰기 감시)."""
    return all(
        bytes(h.peek(FONT_BASE + lo * STRIDE, (hi - lo) * STRIDE)) == ref
        for lo, hi, ref in h.guard_ref
    )


def parse(spec):
    """`7231-7804,6636-7115` → [(7231, 7804), (6636, 7115)]"""
    return [tuple(int(x) for x in p.split("-")) for p in spec.split(",")]
