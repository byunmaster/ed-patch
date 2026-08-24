"""SH-2 미니 어셈블러 — 훅 루틴을 손으로 인코딩하지 않기 위해.

레포 빌드 규율에 「손인코딩 기계어는 디스어셈블로 검산한다」가 있다(PS1 스텁 오타 둘에
반나절). 그래서 **니모닉으로 쓰고 · 여기서 인코딩하고 · 캡스톤으로 되읽어 대조**한다.

지원하는 건 훅에 필요한 것만이다. 없는 걸 쓰면 이름 그대로 실패한다 — 조용히 틀린
바이트를 내는 것보다 낫다.

⚠ **지연 슬롯**: `bra`·`jmp` 다음 한 줄은 분기 **전에** 실행된다. 이 어셈블러는 그걸
  안 챙겨 주므로 쓰는 쪽이 `nop` 을 명시한다(그래야 눈에 보인다).
⚠ `bt`/`bf` 는 지연 슬롯이 **없고** 범위가 ±256B 다 — 넘으면 실패시킨다.
⚠ `mov.l @(d,pc)` 는 앞으로 **1,020B** 까지다. 리터럴 풀은 루틴 바로 뒤에 둔다.
"""

import re


def R(s):
    """`"r12"` → 12."""
    return int(s[1:])


def _n(a):
    return R(a) & 0xF


def _split(s):
    """인자를 콤마로 가른다 — ⚠ 괄호 안의 콤마는 안 가른다(`@(L,pc)`)."""
    out, buf, depth = [], "", 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(buf.strip())
    return out


class Asm:
    def __init__(self):
        self.out = bytearray()
        self.labels = {}
        self.fix = []  # (오프셋, 종류, 라벨)
        self.pool = []  # (라벨, 값)

    # ── 흐름 ────────────────────────────────────────────────────────────────
    def label(self, name):
        assert name not in self.labels, f"라벨 중복: {name}"
        self.labels[name] = len(self.out)

    def long(self, name, value):
        """리터럴 풀 항목 — 루틴 뒤에 4바이트 정렬로 깔린다."""
        self.pool.append((name, value))

    def emit(self, w):
        self.out += w.to_bytes(2, "big")

    # ── 명령 ────────────────────────────────────────────────────────────────
    def op(self, line):
        t = line.split(None, 1)
        m = t[0]
        a = _split(t[1]) if len(t) > 1 else []
        f = getattr(self, "_" + m.replace(".", "_").replace("/", "_"), None)
        assert f, f"모르는 명령: {line!r}"
        f(*a)

    def _nop(self):
        self.emit(0x0009)

    def _mov(self, s, d):
        if s.startswith("#"):
            v = int(s[1:], 0)
            assert -128 <= v <= 127, f"mov #imm 범위 밖: {v}"
            self.emit(0xE000 | (_n(d) << 8) | (v & 0xFF))
        else:
            self.emit(0x6003 | (_n(d) << 8) | (_n(s) << 4))

    def _mov_l(self, s, d):
        if s.startswith("@(") and s.endswith(",pc)"):  # mov.l @(라벨,pc),Rn
            self.fix.append((len(self.out), "pc", s[2:-4]))
            self.emit(0xD000 | (_n(d) << 8))
        elif s.startswith("@") and s.endswith("+"):  # mov.l @Rn+,Rm
            self.emit(0x6006 | (_n(d) << 8) | (_n(s[1:-1]) << 4))
        elif d.startswith("@-"):  # mov.l Rm,@-Rn
            self.emit(0x2006 | (_n(d[2:]) << 8) | (_n(s) << 4))
        else:
            raise AssertionError(f"mov.l 꼴 모름: {s},{d}")

    def _mov_b(self, s, d):
        if s.startswith("@(r0,"):  # mov.b @(r0,Rm),Rn
            self.emit(0x000C | (_n(d) << 8) | (_n(s[5:-1]) << 4))
        elif s.startswith("@"):  # mov.b @Rm,Rn
            self.emit(0x6000 | (_n(d) << 8) | (_n(s[1:]) << 4))
        elif d.startswith("@"):  # mov.b Rm,@Rn
            self.emit(0x2000 | (_n(d[1:]) << 8) | (_n(s) << 4))
        else:
            raise AssertionError(f"mov.b 꼴 모름: {s},{d}")

    def _extu_b(self, s, d):
        self.emit(0x600C | (_n(d) << 8) | (_n(s) << 4))

    def _add(self, s, d):
        if s.startswith("#"):
            v = int(s[1:], 0)
            assert -128 <= v <= 127
            self.emit(0x7000 | (_n(d) << 8) | (v & 0xFF))
        else:
            self.emit(0x300C | (_n(d) << 8) | (_n(s) << 4))

    def _sub(self, s, d):
        self.emit(0x3008 | (_n(d) << 8) | (_n(s) << 4))

    def _cmp_eq(self, s, d):
        self.emit(0x3000 | (_n(d) << 8) | (_n(s) << 4))

    def _cmp_hs(self, s, d):
        self.emit(0x3002 | (_n(d) << 8) | (_n(s) << 4))

    def _tst(self, s, d):
        self.emit(0x2008 | (_n(d) << 8) | (_n(s) << 4))

    def _or(self, s, d):
        self.emit(0x200B | (_n(d) << 8) | (_n(s) << 4))

    def _shll8(self, d):
        self.emit(0x4018 | (_n(d) << 8))

    def _shll16(self, d):
        self.emit(0x4028 | (_n(d) << 8))

    def _shlr8(self, d):
        self.emit(0x4019 | (_n(d) << 8))

    def _bt(self, lab):
        self.fix.append((len(self.out), "b8", lab))
        self.emit(0x8900)

    def _bf(self, lab):
        self.fix.append((len(self.out), "b8", lab))
        self.emit(0x8B00)

    def _bra(self, lab):
        self.fix.append((len(self.out), "b12", lab))
        self.emit(0xA000)

    def _jmp(self, s):
        self.emit(0x402B | (_n(s[1:]) << 8))

    # ── 마무리 ──────────────────────────────────────────────────────────────
    def link(self, base):
        """`base` 에 놓일 때의 최종 바이트. 리터럴 풀까지 붙여 낸다."""
        while len(self.out) % 4:
            self.emit(0x0009)  # 풀을 4바이트 정렬
        pool_at = {}
        body = len(self.out)
        for name, val in self.pool:
            pool_at[name] = len(self.out)
            self.out += val.to_bytes(4, "big")
        for at, kind, lab in self.fix:
            pc = at
            if kind == "pc":
                assert lab in pool_at, f"풀에 없는 라벨: {lab}"
                d = (pool_at[lab] - ((pc + 4) & ~3)) // 4
                assert 0 <= d <= 255, f"pc 상대 로드 범위 밖: {lab} (d={d})"
                self.out[at + 1] = d
            else:
                assert lab in self.labels, f"없는 라벨: {lab}"
                d = (self.labels[lab] - (pc + 4)) // 2
                if kind == "b8":
                    assert -128 <= d <= 127, f"bt/bf 범위 밖: {lab} (d={d})"
                    self.out[at + 1] = d & 0xFF
                else:
                    assert -2048 <= d <= 2047, f"bra 범위 밖: {lab} (d={d})"
                    w = 0xA000 | (d & 0xFFF)
                    self.out[at] = w >> 8
                    self.out[at + 1] = w & 0xFF
        return bytes(self.out), body


def assemble(lines, base):
    """`["라벨:", "mov r6,r8", ...]` → (바이트, 본문 길이)."""
    a = Asm()
    pend = []
    for ln in lines:
        ln = re.sub(r";.*$", "", ln).strip()
        if not ln:
            continue
        if ln.endswith(":"):
            a.label(ln[:-1])
        elif ln.startswith(".long"):
            _, name, val = ln.split(None, 2)
            pend.append((name, int(val, 0)))
        else:
            a.op(ln)
    for name, val in pend:
        a.long(name, val)
    return a.link(base)


def verify(code, base, body_len):
    """캡스톤으로 되읽어 **연속 디코드**되는지 본다 → 디스어셈블 문자열 목록."""
    import capstone

    md = capstone.Cs(capstone.CS_ARCH_SH, capstone.CS_MODE_SH2 | capstone.CS_MODE_BIG_ENDIAN)
    out, n = [], 0
    for ins in md.disasm(code[:body_len], base):
        out.append(f"{ins.address:08X}  {ins.bytes.hex():8s}  {ins.mnemonic:8s} {ins.op_str}")
        n += ins.size
    assert n == body_len, f"연속 디코드 실패 — {n}/{body_len}B 에서 끊겼다"
    return out
