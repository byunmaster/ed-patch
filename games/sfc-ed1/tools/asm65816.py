"""아주 작은 65816 어셈블러 — 훅 페이로드를 **손인코딩하지 않기 위한** 도구.

루트 CLAUDE.md 「빌드 규율」: *손인코딩 기계어는 디스어셈블로 검산한다.* 그래서 여기서는
니모닉으로 쓰고, `tools/tests/test_hook.py` 가 capstone 으로 되읽어 대조한다.

가진 것만 있다(우리가 쓰는 명령·주소지정만). 폭(`m8`/`m16`)은 **호출자가 명시**한다 —
65816 에서 즉치 길이는 코드로 안 드러나므로 추측하지 않는다.
"""

# 인자 없는 명령
IMPLIED = {
    "php": 0x08,
    "plp": 0x28,
    "phb": 0x8B,
    "plb": 0xAB,
    "pha": 0x48,
    "pla": 0x68,
    "phx": 0xDA,
    "plx": 0xFA,
    "phy": 0x5A,
    "ply": 0x7A,
    "phd": 0x0B,
    "pld": 0x2B,
    "clc": 0x18,
    "sec": 0x38,
    "asl": 0x0A,
    "lsr": 0x4A,
    "inc": 0x1A,
    "dec": 0x3A,
    "inx": 0xE8,
    "iny": 0xC8,
    "dex": 0xCA,
    "dey": 0x88,
    "tax": 0xAA,
    "tay": 0xA8,
    "txa": 0x8A,
    "tya": 0x98,
    "txy": 0x9B,
    "tyx": 0xBB,
    "xba": 0xEB,
    "rts": 0x60,
    "rtl": 0x6B,
    "nop": 0xEA,
}
BRANCH = {"beq": 0xF0, "bne": 0xD0, "bcc": 0x90, "bcs": 0xB0, "bra": 0x80, "bpl": 0x10, "bmi": 0x30}
# (니모닉, 주소지정) → 오피코드
OPS = {
    ("lda", "imm"): 0xA9,
    ("cmp", "imm"): 0xC9,
    ("and", "imm"): 0x29,
    ("adc", "imm"): 0x69,
    ("ora", "imm"): 0x09,
    ("eor", "imm"): 0x49,
    ("ldx", "imm"): 0xA2,
    ("ldy", "imm"): 0xA0,
    ("cpx", "imm"): 0xE0,
    ("cpy", "imm"): 0xC0,
    ("sep", "imm8"): 0xE2,
    ("rep", "imm8"): 0xC2,
    ("lda", "abs"): 0xAD,
    ("sta", "abs"): 0x8D,
    ("cmp", "abs"): 0xCD,
    ("ldx", "abs"): 0xAE,
    ("ldy", "abs"): 0xAC,
    ("stx", "abs"): 0x8E,
    ("sty", "abs"): 0x8C,
    ("lda", "absx"): 0xBD,
    ("sta", "absx"): 0x9D,
    ("and", "absx"): 0x3D,
    ("lda", "absy"): 0xB9,
    ("and", "absy"): 0x39,
    ("lda", "long"): 0xAF,
    ("sta", "long"): 0x8F,
    ("cmp", "long"): 0xCF,
    ("adc", "long"): 0x6F,
    ("and", "long"): 0x2F,
    ("ora", "long"): 0x0F,
    ("lda", "longx"): 0xBF,
    ("sta", "longx"): 0x9F,
    ("lda", "dp"): 0xA5,
    ("sta", "dp"): 0x85,
    ("lda", "indlong"): 0xA7,
    ("lda", "indlongy"): 0xB7,
    ("sta", "indlongy"): 0x97,
    ("sta", "indlong"): 0x87,
    ("jsr", "abs"): 0x20,
    ("jmp", "abs"): 0x4C,
    ("jsl", "long"): 0x22,
}
SIZE = {
    "imm8": 2,
    "dp": 2,
    "indlong": 2,
    "indlongy": 2,
    "abs": 3,
    "absx": 3,
    "absy": 3,
    "long": 4,
    "longx": 4,
}


class Asm:
    """`org` 는 뱅크 안 주소($8000~). 라벨은 문자열, 값은 뱅크 안 주소."""

    def __init__(self, org: int, bank: int = 0):
        self.org = org
        self.bank = bank  # 라벨을 long 주소로 쓸 때 얹을 뱅크
        self.items: list = []  # (size, emit(labels) -> bytes)
        self.labels: dict[str, int] = {}
        self.pos = org

    # ── 뼈대 ──
    def label(self, name: str):
        if name in self.labels:
            raise ValueError(f"라벨 중복: {name}")
        self.labels[name] = self.pos
        return self

    def _add(self, size: int, fn):
        self.items.append((self.pos, size, fn))
        self.pos += size
        return self

    def raw(self, data: bytes):
        return self._add(len(data), lambda _l, _p, d=bytes(data): d)

    # ── 명령 ──
    def op(self, mnem: str, *, imm=None, m16=False, addr=None, dp=None, mode=None, label=None):
        if mnem in IMPLIED and imm is None and addr is None and dp is None and label is None:
            return self._add(1, lambda _l, _p, o=IMPLIED[mnem]: bytes([o]))
        if mnem in BRANCH:
            o = BRANCH[mnem]

            def emit_branch(lab, pc, o=o, t=label):
                d = lab[t] - (pc + 2)
                if not -128 <= d <= 127:
                    raise ValueError(f"분기가 멀다: {t} ({d})")
                return bytes([o, d & 0xFF])

            return self._add(2, emit_branch)
        if mnem in ("sep", "rep"):
            o = OPS[(mnem, "imm8")]
            return self._add(2, lambda _l, _p, o=o, v=imm: bytes([o, v]))
        if imm is not None:
            o = OPS[(mnem, "imm")]
            n = 2 if m16 else 1
            return self._add(
                1 + n, lambda _l, _p, o=o, v=imm, n=n: bytes([o]) + v.to_bytes(n, "little")
            )
        if dp is not None:
            o = OPS[(mnem, mode or "dp")]
            return self._add(2, lambda _l, _p, o=o, v=dp: bytes([o, v]))
        assert addr is not None and mode is not None
        o = OPS[(mnem, mode)]
        n = SIZE[mode] - 1

        def emit_addr(lab, _pc, o=o, v=addr, n=n, bank=self.bank):
            a = lab[v] if isinstance(v, str) else v
            if isinstance(v, str) and n == 3:  # 라벨을 long 으로 — 이 뱅크 안이다
                a |= bank << 16
            return bytes([o]) + a.to_bytes(n, "little")

        return self._add(1 + n, emit_addr)

    # ── 편의 ──
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def f(**kw):
            return self.op(name, **kw)

        return f

    def assemble(self) -> bytes:
        out = bytearray()
        for pc, size, fn in self.items:
            b = fn(self.labels, pc)
            assert len(b) == size, (pc, size, b)
            out += b
        return bytes(out)
