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
            elif op == 0x09:
                self.a = self.nz(self.a | self.b())
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
        self.assertTrue(
            all(blk.index(TIMER) <= i < blk.index(TIMER) + 7 for i in diff if i < len(blk)), diff
        )

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
        N.VOICE0 = set()
        out, n = N.patch_block(2, blk)
        self.assertEqual((n, out[4]), (1, 0x00))
        self.assertEqual(self.go(out, 5)[1], (N.SHOW_76, 0xA4D5))

    def raias_voice0(self):
        voice = b"\x20\x15\x58\x00\x00\x20\x00"
        pre = msg(0xD5, 0xA4)  # 인사 창(음성 호출 바로 앞)
        blk = body_at(
            pre
            + voice
            + GATE
            + b"\xf0\x14"
            + TIMER
            + b"\x80\x0b"
            + msg(0xD5, 0xA4)
            + b"\xad\x00\xc1"
        )
        N.SITES = {2: {0: "raias"}}
        N.VOICE0 = {2}
        out, n = N.patch_block(2, blk)
        return len(pre), voice, out, n

    def test_voice_call_arms_play_start_watch(self):
        v, voice, out, n = self.raias_voice0()
        self.assertEqual(n, 2)  # 게이트 1 + 음성 스텁
        self.assertEqual(out[v], 0x20)
        self.assertEqual(out[v + 3 : v + 7], b"\xea" * 4)
        stub = (out[v + 1] | out[v + 2] << 8) - N.BASE
        inst = N._resident_asm().labels["inst"]
        self.assertEqual(out[stub : stub + 3], bytes([0x20, inst & 0xFF, inst >> 8]))
        self.assertEqual(
            out[stub + 3 : stub + 8],
            bytes([0xA9, 1, 0x8D, hook_mod.VOICE_ARM & 0xFF, hook_mod.VOICE_ARM >> 8]),
        )
        self.assertEqual(
            out[stub + 20 : stub + 28], voice + b"\x60"
        )  # 음성은 원래 호출 그대로 · 시점도 그대로

    def run_stub(self, out, at, pre):
        """게이트 자리의 `JSR 스텁` 을 실행 — 스텁 안의 상주부 호출마다 창을 띄우고 시계를 돌린다. 반환 = (띄운 메시지 순서, 첫 마감들, 시계)."""
        mem = self.mem_with(out)
        for k, v in pre.items():
            mem[k] = v
        stub = (out[at + 1] | out[at + 2] << 8) - N.BASE
        c = CPU(mem, 10, 30, 0)
        shown, firsts = [], []
        pc = N.BASE + stub  # 표 없는 옛 꼴 = 앞 대기 없음(열림 대기 머리는 OpenPairs 가 본다)
        for _ in range(2):  # 스텁은 상주부 호출 둘(인사 · 설교)
            self.assertEqual(mem[pc], 0x20)
            ret = pc + 2
            c.call(N.ENTRY, ret, 0, 0)
            shown.append(c.shown)
            firsts.append(c.first)
            pc += (
                9 + 11
            )  # JSR+인라인 4 · BRA 2 · 적재 11 — 인라인 건너뜀은 호출이 처리, 다음 호출로
        return shown, firsts, c

    def test_voice0_stub_shows_greeting_then_sermon_from_play_start(self):
        v, _, out, _ = self.raias_voice0()
        at = v + 7 + 5
        self.assertEqual(out[at], 0x20)
        clock = 10 * 60 + 30
        start = clock - 150  # 소리는 150프레임 전에 시작했다(ARM = 0 → 이미 시작)
        pre = {hook_mod.PLAYSTART: start & 0xFF, hook_mod.PLAYSTART + 1: start >> 8}
        shown, firsts, _ = self.run_stub(out, at, pre)
        self.assertEqual([x[1] for x in shown], [0xA4D5, 0xA4D5])
        self.assertEqual(
            firsts[0], start + round(N.GREET_LEGACY_END[2] * N.FPS)
        )  # 인사 창은 음성 시작 + 9.35초에 닫힌다
        self.assertEqual(firsts[1], start + 0x080C)  # 설교 창 표의 0 도 같은 시작

    def test_voice0_waits_for_play_start_then_gives_up(self):
        v, _, out, _ = self.raias_voice0()
        at = v + 7 + 5
        clock = 10 * 60 + 30
        pre = {
            hook_mod.VOICE_ARM: 1,
            hook_mod.PLAYSTART: clock & 0xFF,
            hook_mod.PLAYSTART + 1: clock >> 8,
        }
        mem = self.mem_with(out)
        for k, val in pre.items():
            mem[k] = val
        c = CPU(mem, 10, 30, 0)
        stub = (out[at + 1] | out[at + 2] << 8) - N.BASE
        c.call(
            N.ENTRY, N.BASE + stub + 2, 0, 0
        )  # 시작이 안 보인다 — 8.5초 기다린 뒤 호출 때 값으로
        self.assertGreater(c.count(), clock + 400)
        self.assertEqual(mem[hook_mod.VOICE_ARM], 0)

    def test_paired_override_builds_stub_with_lead_wait_and_split_windows(self):
        body = b"\x1f\x80\x04\x01AA\x05BB\x05CC\x00"
        N.SITES = {9: {0: "single"}}
        blk = body_at(
            b"\xea" * 4 + GATE + b"\xf0\x09" + TIMER + b"\x80\x0b" + msg(0xD5, 0xA4) + b"\x60",
            body=body,
        )
        at = 4 + len(GATE) + 2
        saved = N.timing_overrides
        N.timing_overrides = lambda: {f"scn009@{at:#x}": [[2.0, 4.0], [None, 6.0], [9.0, 12.0]]}
        try:
            out, n = N.patch_block(9, blk)
        finally:
            N.timing_overrides = saved
        self.assertEqual(out[at], 0x20)
        stub = (out[at + 1] | out[at + 2] << 8) - N.BASE
        # 스텁: 앞 대기(2.0초) · 호출(쪽 0~1, 표 = 열림 기준 거리) · 간격 대기(6.0→9.0초) · 호출(쪽 2)
        f = lambda sec: round(sec * N.FPS)  # noqa: E731
        lead = N._wait(f(2.0))
        self.assertEqual(out[stub : stub + 7], lead)
        c1 = stub + 7
        self.assertEqual(out[c1 : c1 + 3], bytes([0x20, N.ENTRY & 0xFF, N.ENTRY >> 8]))
        tab1 = (out[c1 + 4] | out[c1 + 5] << 8) - N.BASE
        self.assertEqual(
            out[tab1 : tab1 + 5],
            bytes([2])
            + (f(4.0) - f(2.0)).to_bytes(2, "little")
            + (f(6.0) - f(2.0)).to_bytes(2, "little"),
        )
        self.assertEqual(out[c1 + 6], 0)  # 상대 기준(VOICE0 아님)
        self.assertEqual(
            out[c1 + 20 : c1 + 23], bytes([0x20, N.CLOSE_WINDOW & 0xFF, N.CLOSE_WINDOW >> 8])
        )  # 간격 동안 창을 닫는다
        w2 = c1 + 23
        self.assertEqual(out[w2 : w2 + 7], N._wait(f(9.0) - f(6.0)))
        c2 = w2 + 7
        tab2 = (out[c2 + 4] | out[c2 + 5] << 8) - N.BASE
        self.assertEqual(
            out[tab2 : tab2 + 3], bytes([1]) + (f(12.0) - f(9.0)).to_bytes(2, "little")
        )
        self.assertEqual(out[c2 + 20], 0x60)
        # 합성한 쪽 메시지: 첫 호출 = 머리 + 쪽 0·1 + 00, 둘째 = 머리 + 쪽 2 + 00
        ld1 = out[c1 + 9 : c1 + 20]
        m1 = (ld1[1] | ld1[5] << 8) - N.BASE
        self.assertEqual(out[m1 : m1 + 10], b"\x1f\x80\x04\x01AA\x05BB\x00")
        self.assertEqual(n, 1)

    def test_single_pre_skips_off_path_prelude(self):
        pre = b"\x20\xcd\x5b\x64\x86"
        blk = body_at(
            GATE + b"\xf0\x09" + TIMER + b"\x80\x10" + pre + msg(0x42, 0xA4, b"\x20\x5b\x5b"),
            0xA442,
        )
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
            b"\xea" * 4 + GATE + b"\xf0\x09" + TIMER + b"\x80\x0b" + msg(0xD5, 0xA4) + b"\x60",
            body=msg_,
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
            b"\xea" * 4 + GATE + b"\xf0\x09" + TIMER + b"\x80\x0b" + msg(0xD5, 0xA4) + b"\x60",
            body=msg_,
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
            b"\xea\xea"
            + voice
            + timer
            + b"\xa9\xff\x85\x6c\x80\x0b"
            + msg(0xD5, 0xA4, b"\x20\x5b\x5b")
            + b"\x60"
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
        tab = (
            bytes([2]) + (60).to_bytes(2, "little") + (150).to_bytes(2, "little")
        )  # 1초 · 2.5초(프레임)
        mem = self.mem_with(tab)
        mem[N.SPEED] = 2
        c = CPU(mem, 10, 30, 0)
        c.a, at = N.BASE & 0xFF, N.BASE
        c.call(N.SCHED, 0x0100, N.BASE >> 8, 0)  # X = 표 주소 상위(A = 하위는 위에서)
        self.assertEqual(mem[N.AUTO_FLAG], 1)
        self.assertEqual(mem[N.SPEED], 3)
        self.assertEqual(
            mem[N.AUTO_TL] | mem[N.AUTO_TH] << 8, 630 + 60
        )  # 시작(카운터 630) + 60프레임
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
        mem[N.IRQ_SITE : N.IRQ_SITE + 3] = b"\x20\xa5\x57"
        inst = N._resident_asm().labels["inst"]
        for _ in range(2):  # 두 번째는 그대로
            CPU(mem, 0, 0, 0).call(inst, 0x0100, 0, 0)
            self.assertEqual(
                bytes(mem[N.IRQ_SITE : N.IRQ_SITE + 3]), b"\x20" + N.TICK_ADDR.to_bytes(2, "little")
            )

    def test_tick_routine_counts_and_chains_to_original(self):
        t = hook_mod.tick_routine()
        self.assertEqual(t[-3:], b"\x4c\xa5\x57")  # 끝은 원래 `JSR $57A5` 대상으로
        self.assertEqual(
            t[:3], b"\xee" + hook_mod.FRAMECNT.to_bytes(2, "little")
        )  # 먼저 카운터를 올린다
        self.assertEqual(
            hook_mod.hook_routine()[hook_mod.TICK_ADDR - hook_mod.HOOK_ADDR :][: len(t)], t
        )
        self.assertLess(
            hook_mod.TICK_ADDR + len(t), hook_mod.FRAMECNT
        )  # 카운터·플래그 자리를 안 덮는다

    def test_quiet_routine_skips_page_sfx_only_in_subtitle_mode(self):
        q = hook_mod.quiet_routine()
        self.assertEqual(len(q), 9)
        self.assertEqual(
            q[:3], b"\xad" + N.AUTO_FLAG.to_bytes(2, "little")
        )  # 자막 모드 표시를 본다
        self.assertEqual(q[3:5], b"\xd0\x03")  # ≠ 0 이면 JMP(3B)를 건너뛰어 RTS 로
        self.assertEqual(
            q[5:8], b"\x4c" + hook_mod.QUIET_ORIG.to_bytes(2, "little")
        )  # 아니면 원래 `$67EC`
        self.assertEqual(q[8], 0x60)
        self.assertEqual(hook_mod.BLINK_FLAG, N.AUTO_FLAG)
        bl = hook_mod.blink_routine()
        self.assertLessEqual(
            hook_mod.BLINK_ADDR + len(bl), hook_mod.QUIET_ADDR
        )  # 깜빡임 루틴과 안 겹친다
        self.assertLessEqual(
            hook_mod.QUIET_ADDR + len(q), hook_mod.FRAMECNT
        )  # 카운터·플래그 자리를 안 덮는다
        self.assertEqual(
            hook_mod.hook_routine()[hook_mod.QUIET_ADDR - hook_mod.HOOK_ADDR :][: len(q)], q
        )

    def test_auto_hook(self):
        for flag, clock, pad, want in (
            (0, (5, 0), 0x00, 0x00),  # 자막 모드 아님 — 버튼 그대로
            (0, (5, 0), 0x20, 0x20),
            (1, (4, 59), 0x00, 0x00),  # 마감 전 (카운터 299 < 310)
            (1, (5, 10), 0x00, 0x20),  # 마감(카운터 310) — 자동으로 누른다
            (1, (6, 0), 0x00, 0x20),
            (1, (4, 0), 0x40, 0x00),  # 마감 전 손으로 눌러도 무시한다(마스터 10-16)
            (1, (4, 0), 0x20, 0x00),
            (1, (5, 10), 0x20, 0x20),  # 마감 뒤엔 어느 쪽이든 넘어간다
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

    def test_blink_hides_cursor_in_subtitle_mode(self):
        self.assertEqual(hook_mod.BLINK_FLAG, N.AUTO_FLAG)  # 같은 자막 모드 표시를 본다
        bl = hook_mod.blink_routine()
        self.assertLessEqual(hook_mod.BLINK_ADDR + len(bl), hook_mod.FRAMECNT)
        self.assertEqual(
            hook_mod.hook_routine()[hook_mod.BLINK_ADDR - hook_mod.HOOK_ADDR :][: len(bl)], bl
        )
        for flag, bit6 in ((0, 0), (1, 0x40)):
            mem = self.mem_with()
            mem[hook_mod.BLINK_ADDR : hook_mod.BLINK_ADDR + len(bl)] = bl
            # `$6CC3` 대역: 깜빡임이 「보임」(비트6=0)으로 쓴 꼴 — LDA $3559,X · AND #$BF · STA $3559,X · RTS
            mem[0x6CC3 : 0x6CC3 + 9] = bytes([0xBD, 0x59, 0x35, 0x29, 0xBF, 0x9D, 0x59, 0x35, 0x60])
            mem[N.AUTO_FLAG] = flag
            mem[0x3559 + 2] = 0xC3
            c = CPU(mem, 0, 0, 0)
            c.pc, c.x, c.y = hook_mod.BLINK_ADDR, 2, 0x23
            c.run()
            self.assertEqual(
                mem[0x3559 + 2], 0x83 | bit6, flag
            )  # 자막 모드면 비트6 고정(숨김), 아니면 원래 결과
            self.assertEqual((c.x, c.y), (2, 0x23))

    def test_resident_fits_padding(self):
        self.assertLessEqual(N.RES_ORG + len(N.resident()), N.RES_END)


class OpenPairs(unittest.TestCase):
    def test_wait_ps_waits_playstart_plus_frames_16bit(self):
        code = N._wait_ps(0xA000, 3.0 and round(3.0 * N.FPS))
        import hook

        self.assertIn(hook.PLAYSTART.to_bytes(2, "little"), code)
        self.assertEqual(code.count(bytes([0x20]) + N.WAIT_FRAMES.to_bytes(2, "little")), 2)
        self.assertEqual(N._wait_ps(0xA000, 400)[-1] != 0, True)  # 8비트를 넘는 지연도 굽는다
        with self.assertRaises(N.GateError):
            N._wait_ps(0xA000, 0x10000)

    def test_plan_splits_only_when_the_gap_exceeds_tolerance(self):
        lead, segs, cl = N.plan_segments([(2.0, 5.0), (None, 8.0), (8.2, 11.0)])
        self.assertEqual((lead, segs), (round(2.0 * N.FPS), [(0, 2, round(2.0 * N.FPS))]))
        self.assertEqual(cl, [round(c * N.FPS) for c in (5.0, 8.0, 11.0)])
        _l, segs, _c = N.plan_segments([(None, 5.0), (7.0, 9.0), (9.1, 12.0)])
        self.assertEqual([(a, b) for a, b, _o in segs], [(0, 0), (1, 2)])
        self.assertEqual(segs[1][2], round(7.0 * N.FPS))
        with self.assertRaises(N.GateError):
            N.plan_segments([(None, 5.0), (None, 4.0)])  # 닫힘이 거꾸로

    def test_seg_message_keeps_speaker_header_and_terminator(self):
        msg = b"\x1f\x80\x81\x04\x01AA\x05BB\x05CC\x00"
        self.assertEqual(N.seg_message(msg, 0, 0), b"\x1f\x80\x81\x04\x01AA\x00")
        self.assertEqual(N.seg_message(msg, 1, 2), b"\x1f\x80\x81\x04\x01BB\x05CC\x00")
        self.assertEqual(
            N.seg_message(b"\x1f\x80\x04\x01AA\x05\x1f\x82\x04\x01BB\x00", 1, 1),
            b"\x1f\x82\x04\x01BB\x00",
        )

    def test_norm_items_accepts_close_only_and_pairs(self):
        self.assertEqual(
            N.norm_items([3, [1.5, 4], [None, 6.5]]), [(None, 3.0), (1.5, 4.0), (None, 6.5)]
        )


if __name__ == "__main__":
    unittest.main()
