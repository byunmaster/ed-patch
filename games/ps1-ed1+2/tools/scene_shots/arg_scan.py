"""씬 오버레이 코드를 미니 시뮬레이터로 따라가 sprintf 호출의 (포맷, 인자) 를 뽑는다.

`lui a1, hi; addiu a1, a1, lo` 로 포맷 주소를 만드는 자리마다 앞쪽 명령을 따라가며 레지스터·스택 상수를 추적하고,
그 포맷을 인자로 sprintf 를 부르는 `jal` 에서 a2·a3 와 스택 인자 네 개를 읽는다(분기는 통과 가정).
"""

import struct

CLOBBERED = (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25)  # 호출이 망가뜨리는 레지스터
UNKNOWN_RD = (
    0x20, 0x22, 0x24, 0x26, 0x27, 0x2A, 0x2B, 0x02, 0x03, 0x04, 0x06, 0x07, 0x10, 0x12, 0x18, 0x19,
)  # fmt: skip
UNKNOWN_RT = (0x23, 0x24, 0x25, 0x21, 0x20, 0x2C, 0x0C, 0x0A, 0x0B, 0x08)


def _exec1(x, regs, stack):
    """명령 하나를 상수 전파로 실행한다(모르면 None)."""
    op, rs, rt, rd = x >> 26, (x >> 21) & 31, (x >> 16) & 31, (x >> 11) & 31
    imm = x & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm

    def put(r, v):
        if r:
            regs[r] = v

    def get(r):
        return regs.get(r) if r else 0

    if op == 0x0F:  # lui
        put(rt, (imm << 16) & 0xFFFFFFFF)
    elif op == 0x09:  # addiu
        v = get(rs)
        put(rt, None if v is None else (v + simm) & 0xFFFFFFFF)
    elif op == 0x0D:  # ori
        v = get(rs)
        put(rt, None if v is None else v | imm)
    elif op == 0 and (x & 0x3F) in (0x21, 0x25):  # addu / or
        a, b = get(rs), get(rt)
        ok = a is not None and b is not None
        put(rd, (a + b if (x & 0x3F) == 0x21 else a | b) & 0xFFFFFFFF if ok else None)
    elif op == 0 and (x & 0x3F) == 0:  # sll
        put(rd, None)
    elif op == 0x2B and rs == 29:  # sw x, off($sp)
        stack[simm] = get(rt)
    elif op in UNKNOWN_RT:
        put(rt, None)
    elif op == 0 and (x & 0x3F) in UNKNOWN_RD:
        put(rd, None)


def scan(d: bytes, base: int, sprintf: int) -> dict[int, list]:
    """{포맷 오프셋(d 안): [[a2, a3, sp+0x10, +0x14, +0x18, +0x1c], …]}"""
    n = len(d) // 4
    words = struct.unpack(f"<{n}I", d[: n * 4])
    jal = 0x0C000000 | ((sprintf >> 2) & 0x3FFFFFF)
    out: dict[int, list] = {}

    def sim(start, target):
        regs, stack = {0: 0}, {}
        pc, steps = start, 0
        while 0 <= pc < n and steps < 80:
            steps += 1
            x = words[pc]
            op = x >> 26
            if x == jal:
                r2 = dict(regs)
                _exec1(words[pc + 1], r2, stack)  # 지연슬롯
                if r2.get(5) == target:
                    args = [r2.get(6), r2.get(7)] + [stack.get(o) for o in (0x10, 0x14, 0x18, 0x1C)]
                    return r2.get(5), args
                for r in CLOBBERED:
                    regs.pop(r, None)
                pc += 2
                continue
            if op in (2, 3, 4, 5, 6, 7, 1) or (op == 0 and (x & 0x3F) in (8, 9)):
                _exec1(words[pc + 1], regs, stack)  # 지연슬롯 먼저
                if op == 2:  # j
                    t = ((pc * 4 + base) & 0xF0000000) | ((x & 0x3FFFFFF) << 2)
                    pc = (t - base) // 4
                    continue
                if op == 3:  # jal(다른 함수) — 호출이 레지스터를 망가뜨린다
                    for r in CLOBBERED:
                        regs.pop(r, None)
                    pc += 2
                    continue
                if op == 0:  # jr/jalr
                    return None
                pc += 2  # 분기는 통과 가정
                continue
            _exec1(x, regs, stack)
            pc += 1
        return None

    for pc in range(n):
        x = words[pc]
        if (x >> 26) != 0x0F or ((x >> 16) & 31) != 5:  # lui a1
            continue
        st = pc
        for k in range(1, 11):  # 뒤로 최대 10 명령, 직전 점프의 지연슬롯 뒤에서 시작
            if pc - k < 0:
                break
            px = words[pc - k]
            if (px >> 26) == 2 or ((px >> 26) == 0 and (px & 0x3F) == 8):
                st = pc - k + 2
                break
            st = pc - k
        st = min(st, pc)
        nx = words[pc + 1]
        if (nx >> 26) != 9:  # 다음이 addiu 가 아니면 포맷 주소 만들기가 아니다
            continue
        lo = (nx & 0xFFFF) - 0x10000 if nx & 0x8000 else nx & 0xFFFF
        target = ((x & 0xFFFF) << 16) + lo
        r = sim(st, target & 0xFFFFFFFF)
        if r:
            a1, args = r
            if base <= a1 < base + len(d):
                out.setdefault(a1 - base, []).append(args)
    return out
