"""손 어셈블러(MIPS I · 리틀엔디언)와 검산 — 훅을 손으로 인코딩할 때 쓴다(ps1-ed3 `engine_patch` 의 어셈블러 몫을 옮겼다 — 같은 CPU·같은 도구).

`asm(text, base)` 가 라벨 2-pass 로 워드를 만들고 `verify(words, base)` 가 capstone 으로 ① 끊김 없이 디코드 ② 지연 슬롯에 분기 없음 ③ **로드 지연**(R3000 은 `lw/lhu/lbu` 바로 다음 명령이
그 레지스터를 못 읽는다)을 본다. 의미는 사람이 보고, 실제 동작은 `uploader_sim` 이 unicorn 으로 돌려 모델과 대조한다.
둘째 소비자(ps1-ed3)가 실재한다 — 공용 후보(`shared/ps1/mipsasm.py`).
"""

import re
import struct

import capstone

_R = {
    n: i
    for i, n in enumerate(
        [
            "zero",
            "at",
            "v0",
            "v1",
            "a0",
            "a1",
            "a2",
            "a3",
            "t0",
            "t1",
            "t2",
            "t3",
            "t4",
            "t5",
            "t6",
            "t7",
            "s0",
            "s1",
            "s2",
            "s3",
            "s4",
            "s5",
            "s6",
            "s7",
            "t8",
            "t9",
            "k0",
            "k1",
            "gp",
            "sp",
            "fp",
            "ra",
        ]
    )
}
_LOADS = {"lb": 0x20, "lh": 0x21, "lw": 0x23, "lbu": 0x24, "lhu": 0x25}
_STORES = {"sb": 0x28, "sh": 0x29, "sw": 0x2B}
_RTYPE = {
    "addu": 0x21,
    "subu": 0x23,
    "and": 0x24,
    "or": 0x25,
    "xor": 0x26,
    "nor": 0x27,
    "slt": 0x2A,
    "sltu": 0x2B,
}


def _reg(s):
    return _R[s.strip().lstrip("$")]


def _i(op, rs, rt, imm):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _r(fn, rs, rt, rd, sa=0):
    return (rs << 21) | (rt << 16) | (rd << 11) | (sa << 6) | fn


def asm(text, base):
    """[워드] — 라벨 2-pass. 한 줄 한 명령, 지연 슬롯은 손으로 채운다."""
    lines = [ln.split("#")[0].strip() for ln in text.strip().splitlines()]
    lines = [ln for ln in lines if ln]
    labels, body, pc = {}, [], base
    for ln in lines:
        if ln.endswith(":"):
            labels[ln[:-1]] = pc
            continue
        body.append((pc, ln))
        pc += 4
    words = []
    for pc, ln in body:
        op, _, rest = ln.partition(" ")
        a = [x.strip() for x in rest.split(",")] if rest else []

        def target(s):
            return labels[s] if s in labels else int(s, 0)

        if op == "nop":
            w = 0
        elif op in _LOADS or op in _STORES:
            m = re.match(r"(-?\w+)\((\$?\w+)\)", a[1])
            w = _i((_LOADS | _STORES)[op], _reg(m.group(2)), _reg(a[0]), int(m.group(1), 0))
        elif op == "addiu":
            w = _i(9, _reg(a[1]), _reg(a[0]), int(a[2], 0))
        elif op == "li":
            v = int(a[1], 0)
            assert -0x8000 <= v <= 0xFFFF, ln
            w = _i(9 if v < 0 else 0xD, 0, _reg(a[0]), v)
        elif op == "lui":
            w = _i(0xF, 0, _reg(a[0]), int(a[1], 0))
        elif op in ("ori", "andi", "slti", "sltiu"):
            w = _i(
                {"ori": 0xD, "andi": 0xC, "slti": 0xA, "sltiu": 0xB}[op],
                _reg(a[1]),
                _reg(a[0]),
                int(a[2], 0),
            )
        elif op in _RTYPE:
            w = _r(_RTYPE[op], _reg(a[1]), _reg(a[2]), _reg(a[0]))
        elif op == "move":
            w = _r(0x21, _reg(a[1]), 0, _reg(a[0]))
        elif op in ("sll", "sra", "srl"):
            w = _r({"sll": 0, "srl": 2, "sra": 3}[op], 0, _reg(a[1]), _reg(a[0]), int(a[2], 0))
        elif op in ("sllv", "srlv", "srav"):  # sllv rd, rt, rs
            w = _r({"sllv": 4, "srlv": 6, "srav": 7}[op], _reg(a[2]), _reg(a[1]), _reg(a[0]))
        elif op == "div":
            w = _r(0x1A, _reg(a[1]), _reg(a[2]), 0)
        elif op == "mult":
            w = _r(0x18, _reg(a[0]), _reg(a[1]), 0)
        elif op in ("mflo", "mfhi"):
            w = _r(0x12 if op == "mflo" else 0x10, 0, 0, _reg(a[0]))
        elif op == "jr":
            w = _r(8, _reg(a[0]), 0, 0)
        elif op in ("j", "jal"):
            w = ((2 if op == "j" else 3) << 26) | ((target(a[0]) >> 2) & 0x3FFFFFF)
        elif op in ("beq", "bne"):
            w = _i(4 if op == "beq" else 5, _reg(a[0]), _reg(a[1]), (target(a[2]) - pc - 4) >> 2)
        elif op in ("blez", "bgtz", "bgez", "bltz"):
            code, rt = {"blez": (6, 0), "bgtz": (7, 0), "bgez": (1, 1), "bltz": (1, 0)}[op]
            w = _i(code, _reg(a[0]), rt, (target(a[1]) - pc - 4) >> 2)
        else:
            raise ValueError(f"모르는 명령: {ln}")
        words.append(w & 0xFFFFFFFF)
    return words, labels


_BRANCH = {"j", "jal", "jr", "jalr", "beq", "bne", "blez", "bgtz", "bgez", "bltz", "beqz", "bnez"}
_ALL_SRC = _BRANCH | {"sb", "sh", "sw", "div", "divu", "mult", "multu"}


def verify(words, base):
    """손 인코딩 검산 — ① 끊김 없이 디코드 ② 지연 슬롯에 분기 없음 ③ 로드 지연 위반 없음.

    ⚠ 재조립 대조까지는 못 한다(capstone 은 디스어셈블러다). 의미는 사람이 본다.
    """
    md = capstone.Cs(
        capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN
    )
    blob = b"".join(struct.pack("<I", w) for w in words)
    ins = list(md.disasm(blob, base))
    if len(ins) != len(words):
        raise AssertionError(f"디코드가 끊겼다 — {len(ins)}/{len(words)} (base {base:#x})")

    def regs(s):
        return set(re.findall(r"\$\w+", s))

    for k, i in enumerate(ins):
        nxt = ins[k + 1] if k + 1 < len(ins) else None
        if nxt is None:
            continue
        if i.mnemonic in _BRANCH and nxt.mnemonic in _BRANCH:
            raise AssertionError(f"{i.address:#x}: 지연 슬롯에 분기가 또 있다 ({nxt.mnemonic})")
        if i.mnemonic in _LOADS or i.mnemonic in ("mflo", "mfhi"):
            dest = i.op_str.split(",")[0].strip()
            ops = [x.strip() for x in nxt.op_str.split(",")]
            src = ops if nxt.mnemonic in _ALL_SRC else ops[1:]
            if dest in regs(", ".join(src)):
                raise AssertionError(
                    f"{i.address:#x}: 로드 지연 — {nxt.mnemonic} 이 {dest} 를 바로 읽는다"
                )
    return "\n".join(f"{i.address:08x}  {i.mnemonic:6s} {i.op_str}" for i in ins)
