"""대사창 모양 자막 런타임 — 작은 CPU·VDC 모형으로 **실제로 돌려** 본다(원본 없이 돈다). 손으로 짠 기계어는 이렇게 검산한다."""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gwin
import gwin_rt as R
import hook

BASE = 0xA400  # 씬 블록 창($A000~$BFFF) 안 — 시계($C1B2)와 겹치지 않는다


class VDC:
    def __init__(self):
        self.vram = [0] * 32768
        self.sel = 0
        self.mawr = self.marr = 0
        self.lo = 0
        self.writes = []

    def write(self, port, v):
        if port == 0:
            self.sel = v & 0x1F
        elif self.sel == 0:
            if port == 2:
                self.mawr = (self.mawr & 0xFF00) | v
            else:
                self.mawr = (self.mawr & 0x00FF) | v << 8
        elif self.sel == 1:
            if port == 2:
                self.marr = (self.marr & 0xFF00) | v
            else:
                self.marr = (self.marr & 0x00FF) | v << 8
        elif self.sel == 2:
            if port == 2:
                self.lo = v
            else:
                self.vram[self.mawr] = self.lo | v << 8
                self.writes.append(self.mawr)
                self.mawr = (self.mawr + 1) & 0x7FFF

    def read(self, port):
        assert self.sel == 2, "VRR 이 아닌 레지스터를 읽었다"
        w = self.vram[self.marr]
        if port == 2:
            return w & 0xFF
        self.marr = (self.marr + 1) & 0x7FFF
        return w >> 8


class CPU:
    def __init__(self, mem, vdc):
        self.m, self.vdc = mem, vdc
        self.mpr5 = 0x76
        self.a = self.x = self.y = 0
        self.c = self.z = self.n = 0
        self.stack = []
        self.i = 0
        self.cycles = 0

    def rd(self, ad):
        return self.vdc.read(ad) if ad in (2, 3) else self.m[ad]

    def wr(self, ad, v):
        v &= 0xFF
        if ad in (0, 2, 3):
            assert self.i, f"VDC 접근({ad})이 SEI 밖이다"
            self.vdc.write(ad, v)
        else:
            self.m[ad] = v

    def nz(self, v):
        v &= 0xFF
        self.z, self.n = int(v == 0), v >> 7
        return v

    def cmp(self, r, v):
        self.c = int(r >= v)
        self.nz(r - v)

    def arith(self, v, sub):
        if sub:
            r = self.a - v - (1 - self.c)
            self.c = int(r >= 0)
        else:
            r = self.a + v + self.c
            self.c = int(r > 0xFF)
        self.a = self.nz(r)

    def run(self, pc):
        m = self.m
        for _ in range(3_000_000):
            op = m[pc]
            w = m[pc + 1] | m[pc + 2] << 8
            b = m[pc + 1]
            ln = 1

            def rel(take, pc=pc):
                d = b - 256 if b > 127 else b
                return pc + 2 + d if take else pc + 2

            if op == 0xA9: self.a = self.nz(b); ln = 2
            elif op == 0xA5: self.a = self.nz(m[b]); ln = 2
            elif op == 0x29: self.a = self.nz(self.a & b); ln = 2
            elif op == 0xAD: self.a = self.nz(self.rd(w)); ln = 3
            elif op == 0xBD: self.a = self.nz(self.rd(w + self.x)); ln = 3
            elif op == 0xB9: self.a = self.nz(self.rd(w + self.y)); ln = 3
            elif op == 0x8D: self.wr(w, self.a); ln = 3
            elif op == 0x99: self.wr(w + self.y, self.a); ln = 3
            elif op == 0x8E: self.wr(w, self.x); ln = 3
            elif op == 0x9C: self.wr(w, 0); ln = 3
            elif op == 0xA2: self.x = self.nz(b); ln = 2
            elif op == 0xAE: self.x = self.nz(self.rd(w)); ln = 3
            elif op == 0xA0: self.y = self.nz(b); ln = 2
            elif op == 0xEE: m[w] = self.nz(m[w] + 1); ln = 3
            elif op == 0xCE: m[w] = self.nz(m[w] - 1); ln = 3
            elif op == 0xC8: self.y = self.nz(self.y + 1)
            elif op == 0xE8: self.x = self.nz(self.x + 1)
            elif op == 0xAA: self.x = self.nz(self.a)
            elif op == 0x8A: self.a = self.nz(self.x)
            elif op == 0x0A: self.c = self.a >> 7; self.a = self.nz(self.a << 1)
            elif op == 0x18: self.c = 0
            elif op == 0x38: self.c = 1
            elif op == 0x69: self.arith(b, False); ln = 2
            elif op == 0x6D: self.arith(m[w], False); ln = 3
            elif op == 0xE9: self.arith(b, True); ln = 2
            elif op == 0xED: self.arith(m[w], True); ln = 3
            elif op == 0xFD: self.arith(m[w + self.x], True); ln = 3
            elif op == 0xC9: self.cmp(self.a, b); ln = 2
            elif op == 0xCD: self.cmp(self.a, m[w]); ln = 3
            elif op == 0xD9: self.cmp(self.a, m[w + self.y]); ln = 3
            elif op == 0xC0: self.cmp(self.y, b); ln = 2
            elif op == 0xE0: self.cmp(self.x, b); ln = 2
            elif op == 0xD0: pc = rel(not self.z); continue
            elif op == 0xF0: pc = rel(self.z); continue
            elif op == 0x90: pc = rel(not self.c); continue
            elif op == 0xB0: pc = rel(self.c); continue
            elif op == 0x30: pc = rel(self.n); continue
            elif op == 0x80: pc = rel(True); continue
            elif op == 0x4C:
                if w == 0xE063:  # 원래 IRQ 대상으로 빠져나감 = 틱 끝
                    return
                pc = w
                continue
            elif op == 0x7C: pc = m[w + self.x] | m[w + self.x + 1] << 8; continue
            elif op == 0x43: self.a = self.nz(self.mpr5); ln = 2
            elif op == 0x20:
                if w == R.INST:  # 카운터 트램펄린 꽂기 — 모형에선 할 일이 없다
                    pc += 3
                    continue
                self.stack.append(pc + 3)
                pc = w
                continue
            elif op == 0x60:
                if not self.stack:
                    return
                pc = self.stack.pop()
                continue
            elif op == 0x08: self.stack.append(("p", self.i))
            elif op == 0x28: self.i = self.stack.pop()[1]
            elif op == 0x78: self.i = 1
            elif op == 0x03: self.wr(0, b); ln = 2
            elif op in (0xE3, 0xF3):
                src, dst, n = w, m[pc + 3] | m[pc + 4] << 8, m[pc + 5] | m[pc + 6] << 8
                for k in range(n):
                    if op == 0xE3:
                        self.wr(dst + (k & 1), m[src + k])
                    else:
                        m[dst + k] = self.rd(src + (k & 1))
                ln = 7
            else:
                raise AssertionError(f"모르는 옵코드 {op:02X} @ {pc:04X}")
            pc += ln
        raise AssertionError("안 끝난다")


class T(unittest.TestCase):
    def setUp(self):
        self.spec = {"pages": [
            {"speaker": "라이아스", "text": "안녕히 주무셨사옵니까, 세리오스님.", "start": 0.0, "end": 1.0},
            {"speaker": "세리오스", "text": "좋은 아침이야, 라이아스.", "start": 1.0, "end": 2.0},
        ]}
        body, self.gw = R.build(self.spec, BASE)
        self.mem = bytearray(0x10000)
        stub = b"\x60" * 3 + b"\x20" + self.gw.to_bytes(2, "little") + b"\x60"
        self.mem[BASE : BASE + len(stub) + len(body)] = stub + body
        tr = hook.tick_routine()
        self.mem[hook.TICK_ADDR : hook.TICK_ADDR + len(tr)] = tr
        self.v = VDC()
        self.blank = [0x4100] * 220
        self.region = lambda: [self.v.vram[R.RA0 + r * 64 + c] for r in range(gwin.H) for c in range(gwin.W)]
        self.set_region(self.blank)
        self.cpu = CPU(self.mem, self.v)

    def set_region(self, words):
        for r in range(gwin.H):
            for c in range(gwin.W):
                self.v.vram[R.RA0 + r * 64 + c] = words[r * gwin.W + c]

    def init(self):
        self.cpu.run(BASE + 3)  # 스텁의 `JSR gw` 부터(원래 호출 3B 는 건너뛴다)

    def irq(self):
        """VBlank 한 번 = 트램펄린 실행(IRQ 안이라 I=1)."""
        self.cpu.i = 1
        self.cpu.stack = []
        self.cpu.run(hook.TICK_ADDR)
        self.cpu.i = 0

    def run_it(self, inject=None, snaps=(), n=None):
        seen = {}
        writes = []
        self.init()
        for f in range(1, (n or R.frames(2.3)) + 1):
            self.v.writes = []
            self.irq()
            writes.append(len(self.v.writes))
            if inject and f == inject[0]:
                self.set_region(inject[1])
            if f in snaps:
                seen[f] = self.region()
        self.maxw = max(writes)
        return seen

    def ours(self, speaker, text):
        _, bat = gwin.make_window(speaker, text)
        return [bat[(r, c)] for r in range(gwin.ROW0, gwin.ROW0 + gwin.H) for c in range(gwin.COL0, gwin.COL0 + gwin.W)]

    def test_init_returns_at_once_without_touching_vdc(self):
        self.v.writes = []
        self.init()
        self.assertEqual(self.v.writes, [])
        self.assertEqual(self.cpu.stack, [])
        self.assertNotEqual(self.mem[hook.GW_FLAG], 0)  # 틱이 켜졌다

    def test_shows_pages_and_restores_blank(self):
        seen = self.run_it(snaps=(R.frames(0.8), R.frames(1.8)))
        self.assertEqual(seen[R.frames(0.8)], self.ours("라이아스", "안녕히 주무셨사옵니까, 세리오스님."))
        self.assertEqual(seen[R.frames(1.8)], self.ours("세리오스", "좋은 아침이야, 라이아스."))
        self.assertEqual(self.region(), self.blank)  # 끝나면 밑그림(여기선 빈 맵)이 돌아온다
        self.assertEqual(self.mem[hook.GW_FLAG], 0)  # 틱이 꺼졌다

    def test_engine_overwrite_is_kept_as_underlay_and_restored(self):
        mapw = [0x9200 + (i % 50) for i in range(220)]  # 인사 중간(0.5초)에 엔진이 맵 타일을 그 자리에 그린다
        seen = self.run_it(inject=(R.frames(0.5), mapw), snaps=(R.frames(0.5) + 20,))
        self.assertEqual(seen[R.frames(0.5) + 20], self.ours("라이아스", "안녕히 주무셨사옵니까, 세리오스님."))  # 맵이 덮었어도 창을 다시 쓴다
        self.assertEqual(self.region(), mapw)  # 끝나면 그 맵이 그대로 남는다

    def test_page_switch_does_not_leak_our_words_into_underlay(self):
        mapw = [0x9200 + (i % 50) for i in range(220)]
        self.set_region(mapw)
        self.run_it()
        self.assertEqual(self.region(), mapw)

    def test_tiles_written_to_text_slots(self):
        self.run_it()
        tiles = gwin.expand(gwin.make_window("세리오스", "좋은 아침이야, 라이아스.")[0])  # 마지막 쪽 타일이 남는다
        got = b"".join(struct.pack("<H", self.v.vram[R.TILE_WORD + k]) for k in range(len(tiles) // 2))
        self.assertEqual(got, tiles)

    def test_per_tick_vdc_work_is_bounded(self):
        self.run_it()
        self.assertLess(self.maxw, 6 * 16 + 2 * gwin.W + 4)  # 틱마다 타일 UPT 개 · 행 둘 이내

    def test_tick_idle_when_off_or_block_gone(self):
        for how in ("flag", "bank", "sig"):
            self.setUp()
            self.init()
            if how == "flag":
                self.mem[hook.GW_FLAG] = 0
            elif how == "bank":
                self.cpu.mpr5 = 0x20
            else:
                sig = int.from_bytes(self.mem[hook.TICK_SIG_OP[0] : hook.TICK_SIG_OP[0] + 2], "little")
                self.mem[sig] ^= 0xFF  # 장면이 바뀌어 블록이 갈렸다
            self.v.writes = []
            before = self.mem[hook.FRAMECNT]
            for _ in range(10):
                self.irq()
            self.assertEqual(self.v.writes, [], how)
            self.assertEqual(self.mem[hook.FRAMECNT], before + 10)  # 카운터는 늘 올라간다


if __name__ == "__main__":
    unittest.main()
