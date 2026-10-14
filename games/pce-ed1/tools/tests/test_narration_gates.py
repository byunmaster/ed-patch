"""나레이션 게이트 자막 — 가짜 블록으로 호출 자리 바이트를 검산하고, 상주부(`resident`)를
**미니 인터프리터로 실제로 돌려** 「훑기 → 메시지 → 원래 타이머 − 읽은 시간」을 확인한다(원본 없이 돈다).
손인코딩 기계어는 이렇게 검산한다(루트 CLAUDE.md 「빌드 규율」)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hook as hook_mod
import narration_gates as N

GATE = b"\xad\x4c\xc0"
TIMER = b"\xa2\x0c\xa0\x08\x20\xd7\x5b"  # 0x080C 프레임 대기


BODY = b"\x82\xa0\x00"  # 한 글자짜리 메시지 본문


def body_at(blk, addr=0xA4D5, body=BODY):
    """메시지 적재가 가리키는 자리에 본문을 놓는다(표를 빌드가 본문에서 만든다)."""
    blk = bytes(blk)
    at = addr - N.BASE
    return blk + b"\x00" * (at - len(blk)) + body


def msg(lo, hi, tail=b"\x20\x76\x5b"):
    return bytes([0xA9, lo, 0x85, 0x10, 0xA9, hi, 0x85, 0x11]) + tail


class CPU:
    """상주부가 쓰는 명령만. `JSR $5B76/$5B5B` 는 메시지 표시 — `read` 프레임만큼 시계를 돌린다.
    `$5BD7`(대기)은 X+Y×256 프레임만큼 시계를 돌리고 그 합을 `waited` 에 쌓는다. 자리 호출부로
    돌아가는 RTS(또는 `JMP $5BD7`)에서 기다린 프레임 합을 돌려준다."""

    def __init__(self, mem, clock_s, clock_f, read):
        self.m, self.read = mem, read
        self.set_count(clock_s * 60 + clock_f)
        self.a = self.x = self.y = 0
        self.c = self.z = self.n = 0
        self.sp = 0xF0
        self.shown = None
        self.waited = 0
        self.stack = []

    def set_count(self, t):
        self.m[N.FRAMECNT], self.m[N.FRAMECNT + 1] = t & 0xFF, (t >> 8) & 0xFF

    def count(self):
        return self.m[N.FRAMECNT] | self.m[N.FRAMECNT + 1] << 8

    def tick(self, n):
        self.set_count(self.count() + n)

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
            elif op == 0xB2:
                zp = self.b()
                self.a = self.nz(m[m[zp] | m[zp + 1] << 8])
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
                    self.first = m[N.AUTO_TL] | m[N.AUTO_TH] << 8
                    self.flag_during = m[N.AUTO_FLAG]
                    self.speed_during = m[N.SPEED]
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
        blk = body_at(blk)
        return blk, *N.patch_block(9, blk)

    def voiced(self, sectors, rule="single", tail=b""):
        """ON 경로: 음성(`JSR $5815` + 인라인 4B) → 타이머(0x080C = 2060프레임)."""
        N.SITES = {9: {0: rule}}
        voice = b"\x20\x15\x58\x00\x00" + bytes([sectors & 0xFF, sectors >> 8])
        blk = (
            b"\xea" * 4
            + GATE
            + bytes([0xF0, 7 + len(voice) + 2])
            + voice
            + TIMER
            + b"\x80\x0b"
            + msg(0xD5, 0xA4)
            + tail
            + b"\x60"
        )
        blk = body_at(blk)
        return blk, N.patch_block(9, blk)[0]

    def timer_of(self, out):
        t = N.TIMER_AT.search(out)  # 패치된 자리는 JSR 상주부라 안 잡힌다 — 인라인 4B 에서 읽는다
        self.assertIsNone(t)
        at = out.index(b"\x20" + bytes([N.ENTRY & 0xFF, N.ENTRY >> 8]))
        tab = (out[at + 4] | out[at + 5] << 8) - N.BASE  # 쪽 마감 표 — 마지막 쪽 끝 = 타이머
        n = out[tab]
        return out[tab + 1 + 2 * (n - 1)] | out[tab + 2 + 2 * (n - 1)] << 8  # 마지막 쪽 끝(프레임)

    def test_voice_longer_than_subtitle_extends_timer_to_voice_end(self):
        _, out = self.voiced(240)  # 61.4초 ↔ 타이머 34.4초
        self.assertEqual(self.timer_of(out), round(240 * N.SEC_PER_SECTOR * N.FPS))

    def test_voice_within_tolerance_keeps_timer(self):
        _, out = self.voiced(131)  # 33.5초 ↔ 34.4초 — 자막이 더 길다
        self.assertEqual(self.timer_of(out), 0x080C)
        _, out = self.voiced(138)  # 35.3초 — 어긋남 0.9초 < 1.5
        self.assertEqual(self.timer_of(out), 0x080C)

    def test_extending_changes_only_the_timer_bytes(self):
        blk, out = self.voiced(240)
        diff = [i for i in range(len(blk)) if blk[i] != out[i]]
        self.assertTrue(all(blk.index(TIMER) <= i < blk.index(TIMER) + 7 for i in diff if i < len(blk)), diff)

    def test_run_after_skip_gate_is_open_and_not_extended(self):
        blk, _ = self.voiced(240)
        N.SITES = {9: {0: "single", 1: "skip"}}
        blk2 = blk[:-1] + GATE + b"\xf0\x00" + b"\x60"
        runs = N.voice_runs(blk2, 9)
        self.assertTrue(runs[0]["open"])
        self.assertEqual(N.retime(blk2, 9), {})

    def test_only_jsr_target_changes(self):
        blk, out, n = self.single()
        self.assertEqual(n, 1)
        self.assertEqual(out[:9] + out[16 : len(blk)], blk[:9] + blk[16:])  # 호출 자리 7B 만
        self.assertEqual(len(out), len(blk) + 3)  # 꼬리에 쪽 마감 표(쪽 수 1B + 쪽당 2B)

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
        blk = body_at(GATE + b"\xf0\x14" + TIMER + b"\x80\x0b" + msg(0xD5, 0xA4) + b"\xad\x00\xc1")
        N.SITES = {2: {0: "raias"}}
        out, n = N.patch_block(2, blk)
        self.assertEqual((n, out[4]), (1, 0x00))
        self.assertEqual(self.go(out, 5)[1], (N.SHOW_76, 0xA4D5))

    def test_single_pre_skips_off_path_prelude(self):
        pre = b"\x20\xcd\x5b\x64\x86"
        blk = body_at(GATE + b"\xf0\x09" + TIMER + b"\x80\x10" + pre + msg(0x42, 0xA4, b"\x20\x5b\x5b"), 0xA442)
        N.SITES = {9: {0: "single_pre"}}
        out, n = N.patch_block(9, blk)
        self.assertEqual((n, *self.go(out, 5)), (1, 0x080C, (N.SHOW_5B, 0xA442)))

    def test_on_message_first_still_shows_off_message(self):
        # ON 경로에 ON 전용 메시지가 OFF 메시지보다 먼저 있다 — 063 꼴. 거리는 빌드가 OFF 메시지로 잰다
        on = msg(0xF4, 0xAA, b"\x20\x5b\x5b")
        blk = body_at(GATE + b"\xf0\x14" + TIMER + on + b"\x80\x0b" + msg(0xD5, 0xA4))
        N.SITES = {9: {0: "single"}}
        out, _ = N.patch_block(9, blk)
        self.assertEqual(self.go(out, 5)[1], (N.SHOW_76, 0xA4D5))

    def test_single_refuses_two_timers(self):
        blk = body_at(GATE + b"\xf0\x10" + TIMER + TIMER + b"\x80\x0b" + msg(0xD5, 0xA4))
        N.SITES = {9: {0: "single"}}
        with self.assertRaises(N.GateError):
            N.patch_block(9, blk)

    def test_all_gives_each_branch_its_own_timer(self):
        t2 = b"\xa2\xe0\xa0\x01\x20\xd7\x5b"  # 0x01E0
        blk = body_at(GATE + b"\xf0\x10" + TIMER + t2 + b"\x80\x0b" + msg(0xD5, 0xA4))
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

    def timed(self, msg_, **kw):
        """메시지 본문 `msg_` 로 single 블록을 패치해 상주부를 돌린다 → (CPU, 메모리, 대기 프레임)."""
        N.SITES = {9: {0: "single"}}
        blk = body_at(
            b"\xea" * 4 + GATE + b"\xf0\x09" + TIMER + b"\x80\x0b" + msg(0xD5, 0xA4) + b"\x60", body=msg_
        )
        out, _ = N.patch_block(9, blk)
        mem = self.mem_with(out)
        mem[N.SPEED] = 2  # 설정 값
        c = CPU(mem, 10, 30, 0)
        waited = c.call(N.ENTRY, N.BASE + 9 + 2, 0, 0)
        return c, mem, waited

    def test_page_deadlines_follow_byte_weight(self):
        # 메시지 = 1쪽 5B(…05) · 2쪽 13B(…00) → W=18, T=0x080C(2060)
        msg_ = b"\x82\xa0\x82\xa2\x05" + b"\x82\xa4" * 6 + b"\x00"
        c, mem, waited = self.timed(msg_)
        start = 10 * 60 + 30
        self.assertEqual(c.first - start, 2060 * 5 // 18)  # 첫 쪽 마감
        self.assertEqual(c.flag_during, 1)
        self.assertEqual(mem[N.AUTO_FLAG], 0)  # 메시지 뒤엔 자막 모드를 끈다
        self.assertEqual(waited, 2060)  # 메시지에 시간을 안 썼으니 원래 타이머만큼

    def test_message_ends_at_06_or_07_not_only_00(self):
        # 06/07 도 종료다(messages.TERM) — 뒤는 다음 메시지라 무게(W)에 안 넣는다. 안 그러면 쪽 마감이 늦게 잡혀 자막이 음성 끝 전에 끝난다(201 실측)
        for term in (b"\x06", b"\x07"):
            msg_ = b"\x82\xa0\x82\xa2\x05" + b"\x82\xa4" * 6 + term + b"\x82\xa4" * 20 + b"\x00"
            c, _, _ = self.timed(msg_)
            start = 10 * 60 + 30
            self.assertEqual(c.first - start, 2060 * 5 // 18, term)  # W=18 (00 까지면 58)

    def test_text_is_instant_and_speed_restored(self):
        c, mem, _ = self.timed(b"\x82\xa0\x00")
        self.assertEqual(c.speed_during, 3)  # 메시지를 띄우는 동안 즉시 찍기
        self.assertEqual(mem[N.SPEED], 2)  # 끝나면 설정대로

    def test_table_overrides_page_ends(self):
        msg_ = b"\x82\xa0\x05\x82\xa2\x05\x82\xa4\x00"
        t = N.page_table(msg_, 2060, ends=[3.0, 10.5, 34.0])
        pages = [t[1 + 2 * k] | t[2 + 2 * k] << 8 for k in range(t[0])]
        self.assertEqual(pages, [round(e * N.FPS) for e in (3.0, 10.5, 34.0)])
        with self.assertRaises(N.GateError):
            N.page_table(msg_, 2060, ends=[3.0])

    def test_table_walks_pages_with_hook(self):
        # 훅이 쪽마다 npage 를 부르면 표의 다음 마감이 AUTO_TS/TF 로 나온다
        msg_ = b"\x82\xa0\x05\x82\xa2\x05\x82\xa4\x00"
        N.SITES = {9: {0: "single"}}
        blk = body_at(
            b"\xea" * 4 + GATE + b"\xf0\x09" + TIMER + b"\x80\x0b" + msg(0xD5, 0xA4) + b"\x60", body=msg_
        )
        out, _ = N.patch_block(9, blk)
        tab = (out[9 + 4] | out[9 + 5] << 8) - N.BASE
        want = [out[tab + 1 + 2 * k] | out[tab + 2 + 2 * k] << 8 for k in range(out[tab])]
        self.assertEqual(want[-1], 2060)
        mem = self.mem_with(out)
        c = CPU(mem, 10, 30, 0)
        c.call(N.ENTRY, N.BASE + 9 + 2, 0, 0)
        self.assertEqual(c.first - 630, want[0])

    def test_always_site_for_voice_without_gate(self):
        # 게이트 없이 음성 → 타이머 → (이미 들은 쪽의) 메시지 — 장면 224 꼴
        voice = b"\x20\x15\x58\x19\x11\x11\x01"
        timer = b"\xa2\x27\xa0\x10\x20\xd7\x5b"
        blk = body_at(
            b"\xea\xea" + voice + timer + b"\xa9\xff\x85\x6c\x80\x0b" + msg(0xD5, 0xA4, b"\x20\x5b\x5b") + b"\x60"
        )
        N.SITES, saved = {}, N.ALWAYS
        N.ALWAYS = {9: "voice_then_msg"}
        try:
            out, n = N.patch_block(9, blk)
        finally:
            N.ALWAYS = saved
        self.assertEqual(n, 1)
        self.assertEqual(self.go(out, 9)[1], (N.SHOW_5B, 0xA4D5))

    def test_sched_walks_global_table_and_turns_itself_off(self):
        # 전역 시각표 — 음성 시작에서 잰 쪽 끝 시각 둘(1초 · 2.5초). 한 번 켜고 쪽이 넘어갈 때마다 다음 마감, 끝나면 자동 넘김을 끈다
        tab = bytes([2]) + (60).to_bytes(2, "little") + (150).to_bytes(2, "little")  # 1초 · 2.5초(프레임)
        mem = self.mem_with(tab)
        mem[N.SPEED] = 2
        c = CPU(mem, 10, 30, 0)
        c.a, at = N.BASE & 0xFF, N.BASE
        c.call(N.SCHED, 0x0100, N.BASE >> 8, 0)  # X = 표 주소 상위(A = 하위는 위에서)
        self.assertEqual(mem[N.AUTO_FLAG], 1)
        self.assertEqual(mem[N.SPEED], 3)
        self.assertEqual(mem[N.AUTO_TL] | mem[N.AUTO_TH] << 8, 630 + 60)  # 시작(카운터 630) + 60프레임
        self.assertEqual(at, N.BASE)
        npage = N._resident_asm().labels["npage"]
        c = CPU(mem, 10, 30, 0)
        c.call(npage, 0x0100, 0, 0)
        self.assertEqual(mem[N.AUTO_TL] | mem[N.AUTO_TH] << 8, 630 + 150)
        self.assertEqual(mem[N.AUTO_FLAG], 1)  # 마지막 마감을 꺼냈지만 그 쪽이 넘어가야 끈다
        c = CPU(mem, 10, 30, 0)
        c.call(npage, 0x0100, 0, 0)  # 마지막 쪽이 넘어간 뒤의 호출
        self.assertEqual(mem[N.AUTO_FLAG], 0)
        self.assertEqual(mem[N.SPEED], 2)  # 설정대로

    def test_inst_patches_irq_site_once(self):
        mem = self.mem_with()
        mem[N.IRQ_SITE : N.IRQ_SITE + 3] = b"\x20\x63\xe0"
        inst = N._resident_asm().labels["inst"]
        for _ in range(2):  # 두 번째는 그대로
            CPU(mem, 0, 0, 0).call(inst, 0x0100, 0, 0)
            self.assertEqual(bytes(mem[N.IRQ_SITE : N.IRQ_SITE + 3]), b"\x20" + N.TICK_ADDR.to_bytes(2, "little"))

    def test_tick_routine_counts_and_chains_to_original(self):
        t = hook_mod.tick_routine()
        self.assertEqual(t[-3:], b"\x4c\x63\xe0")  # 끝은 원래 `JSR $E063` 대상으로
        self.assertEqual(t[:3], b"\xee" + hook_mod.FRAMECNT.to_bytes(2, "little"))  # 먼저 카운터를 올린다
        self.assertEqual(hook_mod.hook_routine()[hook_mod.TICK_ADDR - hook_mod.HOOK_ADDR :][: len(t)], t)
        self.assertLess(hook_mod.TICK_ADDR + len(t), hook_mod.FRAMECNT)  # 카운터·플래그 자리를 안 덮는다

    def test_auto_hook(self):
        for flag, clock, pad, want in (
            (0, (5, 0), 0x00, 0x00),  # 자막 모드 아님 — 버튼 그대로
            (0, (5, 0), 0x20, 0x20),
            (1, (4, 59), 0x00, 0x00),  # 마감 전 (카운터 299 < 310)
            (1, (5, 10), 0x00, 0x20),  # 마감(카운터 310) — 자동으로 누른다
            (1, (6, 0), 0x00, 0x20),
            (1, (4, 0), 0x40, 0x40),  # 손으로 누르면 그대로
        ):
            mem = self.mem_with()
            mem[N.AUTO_FLAG], mem[N.AUTO_TL], mem[N.AUTO_TH] = flag, 310 & 0xFF, 310 >> 8
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
