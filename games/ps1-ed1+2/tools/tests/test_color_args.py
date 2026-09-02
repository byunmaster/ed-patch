#!/usr/bin/env python3
"""`dump_color_args` 인자 추출 회귀 — **원본 없이** 돈다(손으로 짠 기계어로).

원본을 읽는 테스트는 워크트리마다 빨간불이 되므로(레포 규칙), 정답지를 코드로 만든다.
정답은 실측이다 — `reinsert_kr_pilot.SCN_ARG_PATCHES` 의 eid 280 주석이 같은 콜사이트를
`(2,1,8,3,1,0xC)` 로 적어 뒀고, 그 자리를 그대로 재현한다.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("LOCK_BYPASS", "1")

import struct

import dump_color_args as D

A0, A1, A2, A3, V0, SP = 4, 5, 6, 7, 2, 29


def addiu(rt, rs, imm):
    return 0x24000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def lui(rt, imm):
    return 0x3C000000 | (rt << 16) | (imm & 0xFFFF)


def sw(rt, off):
    return 0xAC000000 | (SP << 21) | (rt << 16) | (off & 0xFFFF)


def jal(t):
    return 0x0C000000 | ((t >> 2) & 0x3FFFFFF)


def j(t):
    return 0x08000000 | ((t >> 2) & 0x3FFFFFF)


BASE = 0x80170000
FMT = 0x801703BC


def blob(words):
    return b"".join(struct.pack("<I", w) for w in words)


def test_direct_callsite_recovers_arg_list():
    """한 블록에 인자가 다 있는 꼴 — eid 280 실측과 같은 배열."""
    words = [
        j(BASE),  # 앞 기본블록을 끊는다
        0,
        addiu(A0, SP, 0x20),
        lui(A1, FMT >> 16),
        addiu(A1, A1, FMT & 0xFFFF),
        addiu(A2, 0, 2),
        addiu(A3, 0, 1),
        addiu(V0, 0, 8),
        sw(V0, 0x10),
        addiu(V0, 0, 3),
        sw(V0, 0x14),
        addiu(V0, 0, 1),
        sw(V0, 0x18),
        addiu(V0, 0, 0xC),
        jal(D.SPRINTF),
        sw(V0, 0x1C),  # 지연 슬롯도 인자다
    ]
    got = D.callsites(blob(words), BASE, 0)
    assert len(got) == 1, got
    fmt, args, _site = got[0]
    assert fmt == FMT, hex(fmt)
    assert args == [2, 1, 8, 3, 1, 0xC], args


def test_tail_jump_callsite_merges_both_halves():
    """⚠ **콜사이트가 두 토막인 꼴** — 앞 블록이 서식·스택 인자, 공용 꼬리가 `a2`·`a3`.

    이걸 안 이으면 커버리지가 반토막 난다(실측 ED1SCN1 53% → 99%).
    꼬리로 **블록 중간에 뛰어드는** 것까지 재현한다.
    """
    tail = BASE + 0x40
    words = [
        j(BASE),
        0,
        addiu(V0, 0, 6),
        sw(V0, 0x10),
        lui(A1, FMT >> 16),
        addiu(A1, A1, FMT & 0xFFFF),
        j(tail),
        addiu(A0, SP, 0x48),
    ]
    words += [0] * ((0x40 // 4) - len(words))
    words += [addiu(A2, 0, 2), jal(D.SPRINTF), addiu(A3, 0, 1)]
    got = [g for g in D.callsites(blob(words), BASE, 0) if g[0] == FMT]
    assert len(got) == 1, got
    assert got[0][1] == [2, 1, 6], got[0][1]


def test_register_sourced_arg_is_unknown_not_guessed():
    """레지스터에서 온 인자는 **`None` 으로 남긴다** — 추측하면 색을 지어내게 된다."""
    words = [
        j(BASE),
        0,
        lui(A1, FMT >> 16),
        addiu(A1, A1, FMT & 0xFFFF),
        addiu(A2, 0, 2),
        0x00801021,  # move v0, a0 — v0 이 어디서 왔는지 모른다
        sw(V0, 0x10),
        jal(D.SPRINTF),
        addiu(A3, 0, 1),
    ]
    got = [g for g in D.callsites(blob(words), BASE, 0) if g[0] == FMT]
    assert got and got[0][1] == [2, 1, None], got


def test_conversions_pair_args_in_order():
    """`%c`·`%s`·`%d` 가 섞여도 **나온 순서대로** 인자를 먹는다."""
    raw = b"%c\x88\xa0%c\x0a%s\xa4%d%c"
    cs = D.block_colors(raw, [2, 1, 0x1234, 7, 3])
    assert [v for _p, v in cs] == [2, 1, 3], cs




def test_find_sprintf_picks_the_routine_whose_fmt_points_at_text():
    """⚠ **주소를 손으로 박으면 ED2 가 조용히 0 이 된다** — 트랙마다 라이브러리 자리가 다르다.

    이름도 심볼도 없으니 **성질**로 찾는다: 서식 인자가 대사 블록 영역을 가리키는 호출.
    미끼로 더 자주 불리는 다른 함수를 섞어 둔다(호출 수만 세면 그쪽을 고른다).
    """
    real, decoy = 0x800CC740, 0x800AA000
    text_end = 0x1000  # BASE..BASE+0x1000 이 텍스트
    words = []
    for _ in range(2):  # 진짜 — fmt 가 텍스트를 가리킨다
        words += [
            j(BASE),
            0,
            lui(A1, BASE >> 16),
            addiu(A1, A1, 0x200),
            addiu(A2, 0, 2),
            jal(real),
            addiu(A3, 0, 1),
        ]
    for _ in range(5):  # 미끼 — 더 자주 불리지만 fmt 가 텍스트 밖이다
        words += [
            j(BASE),
            0,
            lui(A1, 0x8019),
            addiu(A1, A1, 0x100),
            jal(decoy),
            0,
        ]
    ins = D.disasm(blob(words), BASE, 0)
    assert D.find_sprintf(ins, BASE, text_end) == real


if __name__ == "__main__":
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            v()
            print(f"  ok  {k}")
