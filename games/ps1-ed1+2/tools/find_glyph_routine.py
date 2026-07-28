"""
SJIS→글리프 주소 변환 루틴 탐색 (MIPS 정적 분석).

ED.EXE 코드에서 폰트 베이스 대역을 조립하는 lui+addiu 쌍과 스트라이드 곱셈을
찾아 변환 루틴을 특정한다. dump()로 주변을 디스어셈블해 손으로 읽는다.

결과(0x800AE6C8~ 변환 함수): 범위 판정으로 블록 베이스 선택 후
글리프 주소 = 베이스 + 로컬인덱스 × 22. 상세는 font_map.py / 리버싱 노트 참조.

ED.EXE: text_addr=0x80010000, 파일 0x800부터. RAM→파일 = addr-0x80010000+0x800.
"""

import struct

from common import extract

ED_LBA, ED_SIZE = 257, 1021952
TEXT_ADDR = 0x80010000
FILE_BASE = 0x800  # 파일 내 text 시작

data = extract(ED_LBA, ED_SIZE)


def ram_to_file(addr):
    return addr - TEXT_ADDR + FILE_BASE


def file_to_ram(off):
    return off - FILE_BASE + TEXT_ADDR


def words(off, n):
    return struct.unpack(f"<{n}I", data[off : off + n * 4])


def disasm(w):
    """아주 축약된 MIPS 디스어셈블 — 관심 명령만 식별."""
    op = w >> 26
    rs, rt, rd = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
    sa, funct = (w >> 6) & 31, w & 63
    imm = w & 0xFFFF
    simm = imm - 0x10000 if imm >= 0x8000 else imm

    def R(n):
        return f"r{n}"

    if w == 0:
        return "nop"
    if op == 0:
        if funct == 0x00:
            return f"sll {R(rd)},{R(rt)},{sa}"
        if funct == 0x02:
            return f"srl {R(rd)},{R(rt)},{sa}"
        if funct == 0x18:
            return f"mult {R(rs)},{R(rt)}"
        if funct == 0x19:
            return f"multu {R(rs)},{R(rt)}"
        if funct == 0x12:
            return f"mflo {R(rd)}"
        if funct == 0x20:
            return f"add {R(rd)},{R(rs)},{R(rt)}"
        if funct == 0x21:
            return f"addu {R(rd)},{R(rs)},{R(rt)}"
        if funct == 0x23:
            return f"subu {R(rd)},{R(rs)},{R(rt)}"
        if funct == 0x08:
            return f"jr {R(rs)}"
        return f".r funct=0x{funct:02X}"
    if op == 0x02:
        return f"j 0x{((w & 0x3FFFFFF) << 2) | 0x80000000:08X}"
    if op == 0x03:
        return f"jal 0x{((w & 0x3FFFFFF) << 2) | 0x80000000:08X}"
    if op == 0x04:
        return f"beq {R(rs)},{R(rt)},{simm}"
    if op == 0x05:
        return f"bne {R(rs)},{R(rt)},{simm}"
    if op == 0x0A:
        return f"slti {R(rt)},{R(rs)},{simm}"
    if op == 0x0B:
        return f"sltiu {R(rt)},{R(rs)},{simm}"
    if op == 0x0C:
        return f"andi {R(rt)},{R(rs)},0x{imm:04X}"
    if op == 0x0F:
        return f"lui {R(rt)},0x{imm:04X}"
    if op == 0x09:
        return f"addiu {R(rt)},{R(rs)},{simm}"
    if op == 0x0D:
        return f"ori {R(rt)},{R(rs)},0x{imm:04X}"
    if op == 0x08:
        return f"addi {R(rt)},{R(rs)},{simm}"
    if op in (0x20, 0x21, 0x23, 0x24, 0x25):
        nm = {0x20: "lb", 0x21: "lh", 0x23: "lw", 0x24: "lbu", 0x25: "lhu"}[op]
        return f"{nm} {R(rt)},{simm}({R(rs)})"
    if op in (0x28, 0x29, 0x2B):
        nm = {0x28: "sb", 0x29: "sh", 0x2B: "sw"}[op]
        return f"{nm} {R(rt)},{simm}({R(rs)})"
    if op == 0x23:
        return f"lw {R(rt)},{simm}({R(rs)})"
    return f"op=0x{op:02X}"


def find_font_base_refs():
    """lui+addiu/ori로 0x800F0000~0x800F8000 대역 주소를 조립하는 지점."""
    n = len(data) // 4
    ws = list(words(0, n))
    hits = []
    lui_reg = {}
    for i, w in enumerate(ws):
        op = w >> 26
        if op == 0x0F:  # lui
            lui_reg[(w >> 16) & 31] = (i, w & 0xFFFF)
        elif op in (0x09, 0x0D):  # addiu/ori
            rs = (w >> 21) & 31
            if rs in lui_reg:
                li, hi = lui_reg[rs]
                if i - li <= 4:
                    lo = w & 0xFFFF
                    if op == 0x09 and lo >= 0x8000:
                        addr = (hi << 16) + lo - 0x10000
                    else:
                        addr = (hi << 16) + lo
                    if 0x800F0000 <= addr <= 0x800F8000:
                        hits.append((li, addr))
    return hits


def find_mul24():
    """*24 계산: (a<<4)+(a<<3), 또는 mult/multu with 0x18 인접 li."""
    n = len(data) // 4
    ws = list(words(0, n))
    hits = []
    for i in range(n - 2):
        # li rX, 0x18 다음 mult
        w = ws[i]
        if (w >> 26) in (0x09, 0x0D) and (w & 0xFFFF) == 0x18:
            for j in range(i + 1, min(i + 4, n)):
                if (ws[j] & 0xFC00003F) == 0x00000018 or (ws[j] & 0xFC00003F) == 0x00000019:
                    hits.append((i, "li 0x18 + mult"))
                    break
        # sll rX,rY,3 ... addu (=*8) 조합은 너무 흔해서 제외; *24는 sll3+sll4+add
    return hits


def dump(off, before=6, after=14):
    start = off - before
    for k in range(before + after):
        o = (start + k) * 4
        w = struct.unpack("<I", data[o : o + 4])[0]
        mark = ">>" if (start + k) == off else "  "
        print(f"  {mark} 0x{file_to_ram(o):08X}: {w:08X}  {disasm(w)}")


def find_callers(target_ram):
    """target_ram을 jal하는 지점."""
    tw = 0x0C000000 | ((target_ram & 0x0FFFFFFF) >> 2)
    n = len(data) // 4
    ws = words(0, n)
    return [i for i, w in enumerate(ws) if w == tw]


def find_mul_stride():
    """글리프 스트라이드 곱셈: *24, *12, *32, *18 등.
    li rX,stride + mult, 또는 sll+add 조합((x<<4)+(x<<3)=x*24)."""
    n = len(data) // 4
    ws = list(words(0, n))
    hits = []
    for i in range(n - 3):
        w0, w1 = ws[i], ws[i + 1]
        # sll a,x,3 ; sll b,x,4 ; add → x*24  (또는 순서 바뀜)
        if (w0 >> 26) == 0 and (w0 & 63) == 0 and (w1 >> 26) == 0 and (w1 & 63) == 0:
            sa0, sa1 = (w0 >> 6) & 31, (w1 >> 6) & 31
            if {sa0, sa1} == {3, 4}:
                hits.append((i, "sll3+sll4 (=*24)"))
            elif {sa0, sa1} == {2, 3}:
                hits.append((i, "sll2+sll3 (=*12)"))
        # li rX, stride ; ... ; mult
        if (w0 >> 26) in (0x09, 0x0D):
            v = w0 & 0xFFFF
            if v in (12, 24, 18, 32, 16):
                for j in range(i + 1, min(i + 5, n)):
                    if (ws[j] & 0xFC00003F) in (0x00000018, 0x00000019):
                        hits.append((i, f"li {v} + mult"))
                        break
    return hits


def main():
    refs = find_font_base_refs()
    print(f"폰트 베이스 대역 참조: {len(refs)}건")
    for i, addr in refs:
        print(f"  파일 0x{i * 4:X} (RAM 0x{file_to_ram(i * 4):08X}) → 조립주소 0x{addr:08X}")

    # 접근자 함수 주소(각 ref가 속한 함수 시작 = lui 위치)
    accessors = [file_to_ram(i * 4) for i, _ in refs]
    # -15112 짜리도 포함 (0x800EC4F8) — refs 필터 밖이라 수동 추가
    accessors.append(0x800ACC1C)
    print("\n접근자 함수 호출처(jal):")
    for acc in sorted(set(accessors)):
        callers = find_callers(acc)
        if callers:
            cs = ", ".join(f"0x{file_to_ram(c * 4):08X}" for c in callers[:8])
            print(f"  {acc:#010x} ← {len(callers)}곳: {cs}")

    print("\n글리프 스트라이드 곱셈 후보:")
    strides = find_mul_stride()
    for i, kind in strides[:25]:
        print(f"  RAM 0x{file_to_ram(i * 4):08X}  [{kind}]")


if __name__ == "__main__":
    main()
