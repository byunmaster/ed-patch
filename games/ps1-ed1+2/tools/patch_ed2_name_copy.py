#!/usr/bin/env python3
"""ED2 조우 코드의 몬스터 이름 복사를 **널까지 복사하는 루프**로 바꾼다(09-28, 마스터 QA 129).

조우(포메이션)마다 ED2MON 오버레이 코드가 이름표의 이름을 전투 워크스페이스
(`0x80137F59` 부터 104B 간격)로 복사한다. 이 복사는 루프가 아니라 **컴파일러가 펼친
고정 길이 복사**이고, 길이는 **원판 일본어 이름+널**로 굳어 있다(`木人Ａ` 6B+1 = 7).
한글 이름이 그보다 길면 끝이 잘려 모든 `%s` 전투 로그에 「나무인ː」처럼 깨져 나오고,
조사 훅도 마지막 글자를 못 읽어 「을(를)」이 안 접힌다.

⇒ 복사 명령어 구간(`lw?/lb` from `a1`, `sw?/sb` to `a0`)을 5명령 strcpy 루프 + nop 으로
바꾼다. 워크스페이스 이름 칸은 +0x14(능력치)까지 20B 라 가장 긴 이름(14B)도 들어간다.

⚠ **이름이 복사 길이를 넘는 블록만** 바꾼다(최소 변경).
⚠ 루프는 a0·a1·v0 를 바꾸고 v1 을 안 쓴다 — 복사 구간 **뒤 코드가 a0·a1·v0·v1 을 다시
  쓰기 전에 읽으면** 거부한다(그 블록은 실패로 보고, 조용히 넘어가지 않는다).
⚠ 이름표 재배치(`patch_ed2_monsters`)가 끝난 **뒤**에 돈다 — 복사 원본 주소는 빌드
  코드의 `lui/addiu a1` 에서 읽는다(재배치가 이미 새 자리로 고쳐 둔 값).
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import capstone
from common import extract, write_user_data
from ed2_monster_review import MON
from patch_ed2_monster_lines import BASE, IMG, _live_group_lba

WS_LO, WS_HI = 0x80137000, 0x80139000  # 전투 워크스페이스 이름 칸들
WS_CAP = 0x14  # 이름 칸 → 다음 필드(+0x14)까지
COPY_OPS = {"lwl", "lwr", "lb", "lbu", "lh", "lhu", "lw", "swl", "swr", "sb", "sh", "sw", "nop"}
REGS = ("$a0", "$a1", "$v0", "$v1")

_md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN)
_md.detail = True


def _dis(buf, off):
    r = list(_md.disasm(buf[off : off + 4], BASE + off, 1))
    return r[0] if r else None


def _imm(op_str, idx):
    return int(op_str.split(",")[idx].strip(), 0)


def _is_copy(ins):
    if ins is None or ins.mnemonic not in COPY_OPS:
        return False
    if ins.mnemonic == "nop":
        return True
    reg, mem = ins.op_str.split(",", 1)
    base = mem.split("(")[-1].rstrip(")")
    if ins.mnemonic.startswith("s"):
        return base == "$a0"
    return base == "$a1" and reg.strip() in ("$v0", "$v1")


def _rw(ins):
    """(읽는 레지스터, 쓰는 레지스터) — capstone 의 regs_access 는 MIPS 를 지원 안 해 규칙으로 판정."""
    import re

    m = ins.mnemonic
    regs = re.findall(r"\$\w+", ins.op_str)
    if m == "nop" or m in ("j", "b"):
        return set(), set()
    if m == "jal":
        return set(), {"$ra"}
    if m.startswith("s") and m not in ("sll", "srl", "sra", "sllv", "srlv", "srav", "slt",
                                        "sltu", "slti", "sltiu", "sub", "subu", "syscall"):
        return set(regs), set()  # 저장: rt·base 둘 다 읽는다
    if m.startswith("b") or m in ("jr",):
        return set(regs), set()
    if m == "jalr":
        return set(regs[1:] or regs), {regs[0]} if len(regs) > 1 else {"$ra"}
    if not regs:
        return set(), set()
    # lwl/lwr 은 형식상 rt 를 병합 읽기하지만 컴파일러는 늘 짝으로 써서 통째로 덮는다 — 쓰기로만 센다
    return set(regs[1:]), {regs[0]}


def _reads_before_write(buf, off, written=frozenset(), depth=0, limit=256):
    """복사 구간 뒤에서 a0·a1·v0·v1 중 **쓰기 전에 읽힐 수 있는** 레지스터.

    `j` 는 따라가고, 조건 분기는 두 갈래를 다 본다. 호출(`jal`)·간접 점프(`jr`)·
    한도 초과는 **아직 안 쓴 레지스터를 전부 위험**으로 본다(보수적).
    """
    written = set(written)
    for k in range(limit):
        ins = _dis(buf, off + 4 * k)
        if ins is None:
            return set(REGS) - written
        rd, wr = _rw(ins)
        bad = rd & (set(REGS) - written)
        if bad:
            return bad
        written |= wr
        m = ins.mnemonic
        if m in ("j", "jal", "jr", "jalr") or m.startswith("b"):
            ds = _dis(buf, off + 4 * (k + 1))
            if ds is None:
                return set(REGS) - written
            rd2, wr2 = _rw(ds)
            bad = rd2 & (set(REGS) - written)
            if bad:
                return bad
            written |= wr2
            if m == "jr" and ins.op_str.strip() == "$ra":
                # 함수 복귀 — 호출 규약상 a0·a1·v1 은 호출자가 기대하지 않는다. 반환값 v0 만 본다.
                return {"$v0"} - written
            if m in ("jal", "jalr", "jr") or depth > 3:
                return set(REGS) - written
            tgt = int(ins.op_str.split(",")[-1].strip(), 0) - BASE
            res = _reads_before_write(buf, tgt, written, depth + 1)
            if m != "j" and m != "b":  # 조건 분기 — 안 탄 갈래도 본다
                res |= _reads_before_write(buf, off + 4 * (k + 2), written, depth + 1)
            return res
    return set(REGS) - written


def find_blocks(buf):
    """[(복사구간 시작, 복사 명령 수, 원본 RAM, 목적지 RAM, 복사 바이트)]"""
    out = []
    for off in range(0, len(buf) - 16, 4):
        a, b, c, d = (_dis(buf, off + 4 * i) for i in range(4))
        if None in (a, b, c, d):
            continue
        if not (a.mnemonic == "lui" and a.op_str.startswith("$a1") and b.mnemonic == "addiu"
                and b.op_str.startswith("$a1, $a1") and c.mnemonic == "lui"
                and c.op_str.startswith("$a0") and d.mnemonic == "addiu"
                and d.op_str.startswith("$a0, $a0")):
            continue
        src = ((_imm(a.op_str, 1) << 16) + _imm(b.op_str, 2)) & 0xFFFFFFFF
        dst = ((_imm(c.op_str, 1) << 16) + _imm(d.op_str, 2)) & 0xFFFFFFFF
        if not WS_LO <= dst < WS_HI:
            continue
        start = off + 16
        n, mx = 0, 0
        while _is_copy(_dis(buf, start + 4 * n)):
            ins = _dis(buf, start + 4 * n)
            if ins.mnemonic.startswith("s") and ins.mnemonic != "nop":
                o = ins.op_str.split(",", 1)[1].split("(")[0].strip()
                o = int(o, 0) if o else 0
                w = {"sb": 1, "sh": 2, "sw": 4, "swl": 1, "swr": 4}[ins.mnemonic]
                mx = max(mx, o + 1 if ins.mnemonic == "swl" else o + w)
            n += 1
        out.append((start, n, src, dst, mx))
    return out


def _loop(pc):
    """lbu v0,0(a1) · addiu a1,a1,1 · sb v0,0(a0) · bne v0,zero,pc · addiu a0,a0,1"""
    return [0x90A20000, 0x24A50001, 0xA0820000, 0x1440FFFC, 0x24840001]


def plan(img=IMG):
    todo, refused = [], []
    live = _live_group_lba(img)
    for g in sorted(MON):
        lba, size = live[g]
        buf = bytes(extract(lba, (size + 2047) // 2048 * 2048, path=img))
        for start, n, src, _dst, copied in find_blocks(buf):
            so = src - BASE
            if not 0 <= so < len(buf):
                continue
            need = buf.find(b"\x00", so) - so + 1
            if need <= copied:
                continue
            if need > WS_CAP:
                refused.append((g, start, need, "이름 칸(20B) 초과"))
                continue
            if n < 5:
                refused.append((g, start, need, f"복사 명령 {n}개 < 루프 5"))
                continue
            bad = _reads_before_write(buf, start + 4 * n)
            if bad:
                refused.append((g, start, need, f"뒤 코드가 {sorted(bad)} 를 읽는다"))
                continue
            todo.append((g, lba, start, n, copied, need))
    return todo, refused


def main():
    todo, refused = plan()
    for g, _s, need, why in refused:
        print(f"  ✗ g{g} {BASE + _s:#x} 이름 {need}B — {why}")
    if refused:
        raise SystemExit("이름 복사 패치: 거부된 블록이 있다 — 이름이 잘린 채 나간다")
    by_group = {}
    for g, lba, start, n, copied, need in todo:
        by_group.setdefault((g, lba), []).append((start, n, copied, need))
    live = _live_group_lba(IMG)
    with open(IMG, "r+b") as f:
        for (g, lba), items in sorted(by_group.items()):
            size = live[g][1]
            buf = bytearray(extract(lba, (size + 2047) // 2048 * 2048, path=IMG))
            for start, n, _copied, _need in items:
                words = _loop(BASE + start) + [0] * (n - 5)
                for k, w in enumerate(words):
                    struct.pack_into("<I", buf, start + 4 * k, w)
            write_user_data(f, lba, bytes(buf[:size]), label=f"ED2MON{g} 이름 복사 루프")
    print(f"ED2MON 이름 복사: {len(todo)}곳을 널까지 복사하는 루프로 바꿨다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
