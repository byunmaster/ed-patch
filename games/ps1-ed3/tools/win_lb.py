"""윈도 정발(ED3·ED4·ED5)의 `LB DAT` 아카이브 해제 — **정발 대사집 추출용**(표기 대조).

포맷(10-12 실측, devlog): `LB DAT\\x1a\\0` + u32 개수 + u32(0) + u32 절대 오프셋 표(개수+1 개, 끝 = 파일 크기).
멤버는 **압축 청크의 열**이고 EXE 의 해제 루틴(`83 EC 10 53 8B 5C 24 1C …`)이 푼다 — 파이썬으로 옮기는 대신
**unicorn 으로 그 루틴을 그대로 돌린다**(바이트 LZ·비트 LZ 둘이 청크 머리 바이트로 갈린다).

🔴 산출물(해제된 바이트)은 원저작물이다 — 커밋하지 않는다.
"""

import struct

from unicorn import UC_ARCH_X86, UC_MODE_32, Uc, UcError
from unicorn.x86_const import UC_X86_REG_ESP

PROLOGUE = bytes.fromhex(
    "83ec10538b5c241c56578b7c242033f6"
)  # 해제 루틴 머리 (ED3_WIN.EXE 0x436710)
BYTELZ = bytes.fromhex(
    "66395d0c"
)  # 바이트 LZ 안쪽 `cmp word ptr [ebp+0xc], bx` — 바깥 루틴은 그보다 0x90 앞(ED3·ED4·ED5 공통, 실측)


class Exe:
    def __init__(self, path):
        self.b = open(path, "rb").read()
        b = self.b
        e = struct.unpack_from("<I", b, 0x3C)[0]
        n = struct.unpack_from("<H", b, e + 6)[0]
        opt = struct.unpack_from("<H", b, e + 20)[0]
        self.base = struct.unpack_from("<I", b, e + 24 + 28)[0]
        self.size = struct.unpack_from("<I", b, e + 24 + 56)[0]
        so = e + 24 + opt
        self.sec = []
        for i in range(n):
            o = so + 40 * i
            vs, va, rs, ro = struct.unpack_from("<IIII", b, o + 8)
            self.sec.append((va, vs, ro, rs))
        # 루틴 위치 — 파일 오프셋에서 찾아 VA 로
        self.fn = None
        i = b.find(BYTELZ)
        i = i - 0x90 if i >= 0 else -1
        if i >= 0 and b[i : i + 4] != PROLOGUE[:4]:
            i = -1
        if i >= 0:
            for va, _vs, ro, rs in self.sec:
                if ro <= i < ro + rs:
                    self.fn = self.base + va + (i - ro)
                    break
        if self.fn is None:
            raise SystemExit(f"해제 루틴을 못 찾았다: {path}")

    def image(self):
        img = bytearray(self.size)
        for va, _vs, ro, rs in self.sec:
            img[va : va + rs] = self.b[ro : ro + rs]
        return bytes(img)


class Unpacker:
    OUT = 0x10000000
    INP = 0x20000000
    STK = 0x30000000
    ARG = 0x38000000

    def __init__(self, exe):
        self.exe = exe
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        sz = (exe.size + 0xFFF) & ~0xFFF
        self.uc.mem_map(exe.base, sz)
        self.uc.mem_write(exe.base, exe.image())
        self.uc.mem_map(self.STK, 0x100000)
        self.uc.mem_map(self.ARG, 0x1000)
        self.outmax = 0
        self.inmax = 0

    def _ensure(self, base, size, attr):
        size = (size + 0xFFFFF) & ~0xFFFFF
        if getattr(self, attr) < size:
            if getattr(self, attr):
                self.uc.mem_unmap(base, getattr(self, attr))
            self.uc.mem_map(base, size)
            setattr(self, attr, size)

    def unpack(self, data, maxout=1 << 24):
        """압축 멤버 → (해제 바이트, 소비한 입력 길이). 실패하면 None."""
        self._ensure(self.INP, len(data) + 0x1000, "inmax")
        self._ensure(self.OUT, maxout, "outmax")
        uc = self.uc
        uc.mem_write(self.INP, bytes(data) + b"\0" * 64)
        # arg1 = &out_ptr, arg2 = &in_ptr
        uc.mem_write(self.ARG, struct.pack("<II", self.OUT, self.INP))
        esp = self.STK + 0x80000
        uc.mem_write(esp, struct.pack("<III", 0xDEAD0000, self.ARG, self.ARG + 4))
        uc.reg_write(UC_X86_REG_ESP, esp)
        try:
            uc.emu_start(self.exe.fn, 0xDEAD0000, count=200_000_000)
        except UcError:
            return None
        outp, inp = struct.unpack("<II", bytes(uc.mem_read(self.ARG, 8)))
        return bytes(uc.mem_read(self.OUT, outp - self.OUT)), inp - self.INP


def members(path):
    """[(오프셋, 길이)] — LB DAT 멤버 표."""
    b = open(path, "rb").read()
    assert b[:6] == b"LB DAT", path
    n = struct.unpack_from("<I", b, 8)[0]
    offs = struct.unpack_from(f"<{n + 1}I", b, 16)
    return b, [(offs[i], offs[i + 1] - offs[i]) for i in range(n)]
