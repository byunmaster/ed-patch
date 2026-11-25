"""글리프 업로더(`0x80016320`) 시뮬레이터 — unicorn 으로 **RAM 덤프 위에서** 업로더를 돌려 `LoadImage` 호출(칸 rect · 4bpp 타일 72B)을 모은다.

반각 훅(`halfwidth.py`)의 검증 틀이다 — 훅 코드를 얹은 RAM 으로 같은 명령열을 돌려 **원판 업로더와 같은 결과(훅 꺼짐) / 모델과 같은 결과(훅 켜짐)** 인지 본다.
RAM 덤프는 마스터 확인용이 아니라 시험용이다: 헤드리스 코어로 프롤로그 대사를 띄운 상태(`work/` 아래에 두며 커밋 안 한다).
unicorn MIPS 는 KSEG0 를 물리 주소로 번역하므로 RAM 을 **0 번지에 매핑**하고, 8MB 미러에 놓인 스택은 2MB 안으로 접는다.
"""

import struct

from unicorn import UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32, Uc, UcError
from unicorn.mips_const import (
    UC_MIPS_REG_A0,
    UC_MIPS_REG_A1,
    UC_MIPS_REG_PC,
    UC_MIPS_REG_RA,
    UC_MIPS_REG_SP,
)

UPLOADER = 0x80016320
LOADIMAGE = 0x8005DE50
CMD_BUF = 0x801F3510
CMD_COUNT = 0x80095D48
GATE_A = 0x801F5AB0  # != 0 이면 업로더가 건너뛴다
GATE_B = 0x80095D48
SKIP_FLAG = 0x801EFC98  # 0 이면 첫머리에서 별도 호출을 한다 — 시험에선 1 로 둔다


class Sim:
    def __init__(self, ram):
        self.mu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        self.mu.mem_map(0x0, 0x200000)
        self.mu.mem_write(0x0, ram)
        self.mu.mem_map(0x1F800000, 0x10000)
        self.loads = []
        self.stub_ret = 0x801FFF00  # 호출 복귀 표시(RAM 맨 끝 — 실행 안 함)

    # 메모리 헬퍼 — 가상 주소(0x80…)를 물리로 바꿔 쓴다
    @staticmethod
    def p(a):
        return a & 0x1FFFFF

    def rd(self, a, n):
        return bytes(self.mu.mem_read(self.p(a), n))

    def wr(self, a, b):
        self.mu.mem_write(self.p(a), bytes(b))

    def u16(self, a):
        return struct.unpack("<H", self.rd(a, 2))[0]

    def w16(self, a, v):
        self.wr(a, struct.pack("<H", v & 0xFFFF))

    def u32(self, a):
        return struct.unpack("<I", self.rd(a, 4))[0]

    def w32(self, a, v):
        self.wr(a, struct.pack("<I", v & 0xFFFFFFFF))

    def run_batches(self, batches, patch=None, max_insn=2_000_000):
        """batches = [(시작 칸, [코드…])] — 명령열을 만들어 업로더를 한 번 돌린다. 반환 = [(x, y, w, h, 72B 타일)…] (`LoadImage` 호출 순)."""
        # 명령열: 명령 하나 = [1][시작 칸][개수][코드…] (명령 종류 1 = 글리프 묶음, 점프표 `0x80010098` 의 1번 = `0x8001648c`)
        buf = bytearray()
        for start, codes in batches:
            buf += struct.pack("<HHH", 1, start, len(codes)) + b"".join(
                struct.pack("<H", c) for c in codes
            )
        self.wr(CMD_BUF, buf)
        self.w16(CMD_COUNT, len(batches))
        self.w16(GATE_A, 0)
        self.w16(SKIP_FLAG, 1)
        self.loads = []
        sp = 0x801FF000
        self.mu.reg_write(UC_MIPS_REG_SP, sp)
        self.mu.reg_write(UC_MIPS_REG_RA, self.stub_ret)

        def on_code(uc, addr, size, ud):
            a = addr | 0x80000000
            if a == LOADIMAGE:
                rect = uc.reg_read(UC_MIPS_REG_A0)
                data = uc.reg_read(UC_MIPS_REG_A1)
                x, y, w, h = struct.unpack("<4h", self.rd(rect, 8))
                self.loads.append((x, y, w, h, self.rd(data, 78)))
                # 함수를 건너뛴다 — 호출 복귀
                uc.reg_write(UC_MIPS_REG_PC, uc.reg_read(UC_MIPS_REG_RA))

        h = self.mu.hook_add(UC_HOOK_CODE, on_code)
        try:
            self.mu.emu_start(UPLOADER, self.stub_ret, count=max_insn)
        except UcError as e:
            if self.mu.reg_read(UC_MIPS_REG_PC) != self.stub_ret:
                raise RuntimeError(
                    f"업로더가 멈췄다: {e} @{self.mu.reg_read(UC_MIPS_REG_PC):#x}"
                ) from e
        finally:
            self.mu.hook_del(h)
        return self.loads
