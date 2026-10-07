"""나레이션 게이트 자막 — 가짜 블록으로 호출 자리 바이트를 검산하고, 상주부(`resident`)를
**미니 인터프리터로 실제로 돌려** 「훑기 → 메시지 → 원래 타이머 − 읽은 시간」을 확인한다(원본 없이 돈다).
손인코딩 기계어는 이렇게 검산한다(루트 CLAUDE.md 「빌드 규율」)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import narration_gates as N

GATE = b"\xad\x4c\xc0"
TIMER = b"\xa2\x0c\xa0\x08\x20\xd7\x5b"  # 0x080C 프레임 대기


def msg(lo, hi, tail=b"\x20\x76\x5b"):
    return bytes([0xA9, lo, 0x85, 0x10, 0xA9, hi, 0x85, 0x11]) + tail


class CPU:
    """상주부가 쓰는 명령만. `JSR $5B76/$5B5B` 는 메시지 표시 — `read` 프레임만큼 시계를 돌린다.
    `$5BD7`(대기)은 X+Y×256 프레임만큼 시계를 돌리고 그 합을 `waited` 에 쌓는다. 자리 호출부로
    돌아가는 RTS(또는 `JMP $5BD7`)에서 기다린 프레임 합을 돌려준다."""

    def __init__(self, mem, clock_s, clock_f, read):
        self.m, self.read = mem, read
        self.m[N.CLOCK_S], self.m[N.CLOCK_F] = clock_s, clock_f
        self.a = self.x = self.y = 0
        self.c = self.z = self.n = 0
        self.sp = 0xF0
        self.shown = None
        self.waited = 0
        self.stack = []

    def tick(self, n):
        m = self.m
        t = m[N.CLOCK_S] * 60 + m[N.CLOCK_F] + n
        m[N.CLOCK_S], m[N.CLOCK_F] = (t // 60) & 0xFF, t % 60

    def call(self, entry, ret, x, y):
        """호출 자리의 `JSR entry` 를 흉내 — 반환 주소(JSR 마지막 바이트)를 스택에 넣는다."""
        self.m[0x2100 + self.sp] = ret >> 8
        self.m[0x2100 + self.sp - 1] = ret & 0xFF
        self.sp -= 2
        self.pc, self.x, self.y = entry, x, y
        return self.run()

    def w(self):
        v = self.m[self.pc] | self.m[self.pc + 1] << 8
        self.pc += 2
        return v

    def b(self):
        v = self.m[self.pc]
        self.pc += 1
        return v

    def nz(self, v):
        v &= 0xFF
        self.z, self.n = int(v == 0), v >> 7
        return v

    def cmp(self, r, v):
        self.c = int(r >= v)
        self.nz(r - v)

    def br(self, take):
        d = self.b()
        if take:
            self.pc += d - 256 if d > 127 else d

    def arith(self, v, sub):
        if sub:
            r = self.a - v - (1 - self.c)
            self.c = int(r >= 0)
        else:
            r = self.a + v + self.c
            self.c = int(r > 0xFF)
        self.a = self.nz(r)

    def run(self):
        m = self.m
        for _ in range(200000):
            op = self.b()
            if op == 0xA9:
                self.a = self.nz(self.b())
            elif op == 0xAD:
                self.a = self.nz(m[self.w()])
            elif op == 0xA5:
                self.a = self.nz(m[self.b()])
            elif op == 0xBD:
                self.a = self.nz(m[self.w() + self.x])
            elif op == 0xB1:
                zp = self.b()
                self.a = self.nz(m[(m[zp] | m[zp + 1] << 8) + self.y])
            elif op == 0x8D:
                m[self.w()] = self.a
            elif op == 0x85:
                m[self.b()] = self.a
            elif op == 0x86:
                m[self.b()] = self.x
            elif op == 0x9C:
                m[self.w()] = 0
            elif op == 0x8E:
                m[self.w()] = self.x
            elif op == 0x8C:
                m[self.w()] = self.y
            elif op == 0xA2:
                self.x = self.nz(self.b())
            elif op == 0xA0:
                self.y = self.nz(self.b())
            elif op == 0xAE:
                self.x = self.nz(m[self.w()])
            elif op == 0xAC:
                self.y = self.nz(m[self.w()])
            elif op == 0xBA:
                self.x = self.nz(self.sp)
            elif op == 0xAA:
                self.x = self.nz(self.a)
            elif op == 0xA8:
                self.y = self.nz(self.a)
            elif op == 0x8A:
                self.a = self.nz(self.x)
            elif op == 0x98:
                self.a = self.nz(self.y)
            elif op == 0xC8:
                self.y = self.nz(self.y + 1)
            elif op == 0xCA:
                self.x = self.nz(self.x - 1)
            elif op == 0x38:
                self.c = 1
            elif op == 0x18:
                self.c = 0
            elif op == 0x69:
                self.arith(self.b(), False)
            elif op == 0x6D:
                self.arith(m[self.w()], False)
            elif op == 0x7D:
                self.arith(m[self.w() + self.x], False)
            elif op == 0x65:
                self.arith(m[self.b()], False)
            elif op == 0xE9:
                self.arith(self.b(), True)
            elif op == 0xED:
                self.arith(m[self.w()], True)
            elif op == 0x49:
                self.a = self.nz(self.a ^ self.b())
            elif op == 0xC9:
                self.cmp(self.a, self.b())
            elif op == 0xDD:
                self.cmp(self.a, m[self.w() + self.x])
            elif op == 0xC0:
                self.cmp(self.y, self.b())
            elif op == 0xCE:
                ad = self.w()
                m[ad] = self.nz(m[ad] - 1)
            elif op == 0xEE:
                ad = self.w()
                m[ad] = self.nz(m[ad] + 1)
            elif op == 0xE6:
                ad = self.b()
                m[ad] = self.nz(m[ad] + 1)
            elif op == 0x80:
                self.br(True)
            elif op == 0xB0:
                self.br(self.c)
            elif op == 0x90:
                self.br(not self.c)
            elif op == 0xF0:
                self.br(self.z)
            elif op == 0xD0:
                self.br(not self.z)
            elif op == 0x10:
                self.br(not self.n)
            elif op == 0x30:
                self.br(self.n)
            elif op == 0x20:
                tgt = self.w()
                if tgt in (N.SHOW_76, N.SHOW_5B):
                    self.shown = (tgt, m[0x10] | m[0x11] << 8)
                    self.first = (m[N.AUTO_TS], m[N.AUTO_TF])
                    self.flag_during = m[N.AUTO_FLAG]
                    self.tick(self.read)
                elif tgt == N.WAIT_FRAMES:
                    n = self.x | self.y << 8
                    self.waited += n
                    self.tick(n)
                else:
                    self.stack.append(self.pc)
                    self.pc = tgt
            elif op == 0x4C:
                tgt = self.w()
                if tgt == N.WAIT_FRAMES:
                    return self.waited + (self.x | self.y << 8)
                self.pc = tgt
            elif op == 0x60:
                if not self.stack:
                    return self.waited  # 자리 호출부로
                self.pc = self.stack.pop()
            elif op == 0x48:
                self.stack.append(("a", self.a))
            elif op == 0x68:
                self.a = self.nz(self.stack.pop()[1])
            elif op in (0x5A, 0x08):
                self.stack.append(("y", self.y))
            elif op == 0x7A:
                self.y = self.nz(self.stack.pop()[1])
            elif op == 0x28:
                self.stack.pop()
            elif op == 0x78:
                pass  # SEI
            elif op in (0x43, 0x53):
                self.b()  # TMA/TAM — 뱅크는 흉내 내지 않는다(평면 메모리)
            elif op == 0xDA:
                self.stack.append(("x", self.x))
            elif op == 0xFA:
                self.x = self.nz(self.stack.pop()[1])
            elif op == 0x9D:
                m[self.w() + self.x] = self.a
            elif op == 0xE0:
                self.cmp(self.x, self.b())
            elif op == 0xE8:
                self.x = self.nz(self.x + 1)
            elif op == 0xCD:
                self.cmp(self.a, m[self.w()])
            elif op == 0x29:
                self.a = self.nz(self.a & self.b())
            elif op == 0x0D:
                self.a = self.nz(self.a | m[self.w()])
            elif op == 0xFD:
                self.arith(m[self.w() + self.x], True)
            else:
                raise AssertionError(f"모르는 옵코드 {op:02X} @ {self.pc - 1:04X}")
        raise AssertionError("안 끝난다")


class PatchBlock(unittest.TestCase):
    def setUp(self):
        self._sites = N.SITES
        N.SITES = {}

    def tearDown(self):
        N.SITES = self._sites

    @staticmethod
    def mem_with(blk=b""):
        mem = bytearray(0x10000)
        mem[N.BASE : N.BASE + len(blk)] = blk
        for org, code in ((N.RES_ORG, N.resident()), (N.AUTO_ORG, N.auto_hook())):
            mem[org : org + len(code)] = code
        return mem

    def go(self, out, at, read=0, clock_s=10, clock_f=30):
        """호출 자리 `at`(JSR 상주부 + 인라인 4B)를 실행한다 → (대기 프레임, 띄운 메시지)."""
        self.assertEqual(out[at], 0x20)
        self.assertEqual(out[at + 1] | out[at + 2] << 8, N.ENTRY)
        mem = self.mem_with(out)
        c = CPU(mem, clock_s, clock_f, read)
        waited = c.call(N.ENTRY, N.BASE + at + 2, 0, 0)
        ret = mem[0x2100 + c.sp + 1] | mem[0x2100 + c.sp + 2] << 8
        self.assertEqual(ret, N.BASE + at + 6)  # 인라인 4B 를 건너뛰어 돌아간다
        return waited, c.shown

    def single(self, tail=b"\x20\x76\x5b"):
        N.SITES = {9: {0: "single"}}
        blk = (
            b"\xea" * 4 + GATE + b"\xf0\x09" + TIMER + b"\x80\x0b" + msg(0xD5, 0xA4, tail) + b"\x60"
        )
        return blk, *N.patch_block(9, blk)

    def test_only_jsr_target_changes(self):
        blk, out, n = self.single()
        self.assertEqual(n, 1)
        self.assertEqual(len(out), len(blk))  # 블록 길이 그대로 — 컨테이너 슬롯이 안 흔들린다
        self.assertEqual(out[:9] + out[16:], blk[:9] + blk[16:])  # 호출 자리 7B 만

    def test_waits_timer_minus_reading_time(self):
        _, out, _ = self.single()
        for read, want in ((0, 0x080C), (100, 0x080C - 100), (61, 0x080C - 61), (0x0900, 0)):
            w, shown = self.go(out, 9, read, clock_f=59)  # 초 경계를 넘는 경우를 섞는다
            self.assertEqual(w, want, read)
            self.assertEqual(shown, (N.SHOW_76, 0xA4D5))

    def test_reading_time_equal_to_timer_does_not_wait(self):
        _, out, _ = self.single()
        self.assertEqual(self.go(out, 9, 0x080C)[0], 0)  # 0 을 넘기면 65536 프레임이 된다

    def test_show_routine_follows_off_path_tail(self):
        for tail, want in (
            (b"\x20\x5b\x5b", N.SHOW_5B),
            (b"\x4c\x06\x5b", N.SHOW_5B),
            (b"\x4c\x0b\x5b", N.SHOW_76),
        ):
            _, out, _ = self.single(tail)
            self.assertEqual(self.go(out, 9)[1][0], want, tail.hex())

    def test_raias_sends_off_into_on_path(self):
        blk = GATE + b"\xf0\x14" + TIMER + b"\x80\x0b" + msg(0xD5, 0xA4) + b"\xad\x00\xc1"
        N.SITES = {2: {0: "raias"}}
        out, n = N.patch_block(2, blk)
        self.assertEqual((n, out[4]), (1, 0x00))
        self.assertEqual(self.go(out, 5)[1], (N.SHOW_76, 0xA4D5))

    def test_single_pre_skips_off_path_prelude(self):
        pre = b"\x20\xcd\x5b\x64\x86"
        blk = GATE + b"\xf0\x09" + TIMER + b"\x80\x10" + pre + msg(0x42, 0xA4, b"\x20\x5b\x5b")
        N.SITES = {9: {0: "single_pre"}}
        out, n = N.patch_block(9, blk)
        self.assertEqual((n, *self.go(out, 5)), (1, 0x080C, (N.SHOW_5B, 0xA442)))

    def test_on_message_first_still_shows_off_message(self):
        # ON 경로에 ON 전용 메시지가 OFF 메시지보다 먼저 있다 — 063 꼴. 거리는 빌드가 OFF 메시지로 잰다
        on = msg(0xF4, 0xAA, b"\x20\x5b\x5b")
        blk = GATE + b"\xf0\x14" + TIMER + on + b"\x80\x0b" + msg(0xD5, 0xA4)
        N.SITES = {9: {0: "single"}}
        out, _ = N.patch_block(9, blk)
        self.assertEqual(self.go(out, 5)[1], (N.SHOW_76, 0xA4D5))

    def test_single_refuses_two_timers(self):
        blk = GATE + b"\xf0\x10" + TIMER + TIMER + b"\x80\x0b" + msg(0xD5, 0xA4)
        N.SITES = {9: {0: "single"}}
        with self.assertRaises(N.GateError):
            N.patch_block(9, blk)

    def test_all_gives_each_branch_its_own_timer(self):
        t2 = b"\xa2\xe0\xa0\x01\x20\xd7\x5b"  # 0x01E0
        blk = GATE + b"\xf0\x10" + TIMER + t2 + b"\x80\x0b" + msg(0xD5, 0xA4)
        N.SITES = {9: {0: "all"}}
        out, n = N.patch_block(9, blk)
        self.assertEqual(n, 2)
        self.assertEqual([self.go(out, at)[0] for at in (5, 12)], [0x080C, 0x01E0])

    def test_last_page2_points_after_page_break(self):
        code = GATE + b"\xf0\x10" + TIMER + TIMER + b"\x80\x0b"
        off_msg = msg(0x00, 0xA1)  # 메시지는 $A100(블록 +0x100)
        blk = bytearray(code + off_msg + b"\x00" * (0x100 - len(code) - len(off_msg)))
        blk += b"\x0b\x82\xcd\x05\x82\xb3\x00"  # 1쪽 · 05 · 2쪽 · 끝
        N.SITES = {9: {0: "last_page2"}}
        out, n = N.patch_block(9, bytes(blk))
        self.assertEqual(n, 1)
        self.assertEqual(out[5:12], TIMER)  # 앞 타이머(연출 박자)는 그대로
        self.assertEqual(self.go(out, 12)[1], (N.SHOW_76, 0xA104))

    def test_page_deadlines_follow_byte_weight(self):
        # 메시지 = 1쪽 5B(…05) · 2쪽 13B(…00) → W=18, T=0x080C(2060)
        _, out, _ = self.single()
        msg_ = b"\x82\xa0\x82\xa2\x05" + b"\x82\xa4" * 6 + b"\x00"
        out = bytearray(out) + b"\x00" * (0x4D5 + len(msg_) - len(out))
        out[0x4D5 : 0x4D5 + len(msg_)] = msg_
        mem = self.mem_with(out)
        c = CPU(mem, 10, 30, 0)
        waited = c.call(N.ENTRY, N.BASE + 9 + 2, 0, 0)
        start = 10 * 60 + 30
        self.assertEqual(c.first[0] * 60 + c.first[1] - start, 2060 * 5 // 18)  # 첫 쪽 마감
        self.assertEqual(c.flag_during, 1)
        self.assertEqual(mem[N.AUTO_FLAG], 0)  # 메시지 뒤엔 자막 모드를 끈다
        self.assertEqual(waited, 2060)  # 메시지에 시간을 안 썼으니 원래 타이머만큼

    def test_auto_hook(self):
        for flag, clock, pad, want in (
            (0, (5, 0), 0x00, 0x00),  # 자막 모드 아님 — 버튼 그대로
            (0, (5, 0), 0x20, 0x20),
            (1, (4, 59), 0x00, 0x00),  # 마감 전
            (1, (5, 10), 0x00, 0x20),  # 마감(5초 10프레임) — 자동으로 누른다
            (1, (6, 0), 0x00, 0x20),
            (1, (4, 0), 0x40, 0x40),  # 손으로 누르면 그대로
        ):
            mem = self.mem_with()
            mem[N.AUTO_FLAG], mem[N.AUTO_TS], mem[N.AUTO_TF] = flag, 5, 10
            fin = N._resident_asm().labels["fin"]
            mem[fin] = 1  # 다음 쪽 계산은 끝났다고 둔다(여기선 버튼 판정만 본다)
            mem[N.PAD] = pad
            c = CPU(mem, *clock, 0)
            c.pc, c.x, c.y = N.AUTO_ORG, 0x48, 0x23
            c.run()
            self.assertEqual((c.a & 0x60, c.x, c.y), (want, 0x48, 0x23), (flag, clock, pad))

    def test_resident_fits_padding(self):
        self.assertLessEqual(N.RES_ORG + len(N.resident()), N.RES_END)


if __name__ == "__main__":
    unittest.main()
