"""반각 합성 훅 회귀 — 업로더를 unicorn 으로 돌려 **모델(tilecomp)과 같은 타일**이 올라가는지 본다.

원본 실행파일이 필요하다(업로더·글꼴 표가 거기 있다) — 없으면 건너뛴다(게이트 `check.sh` 는 원본이 있는 자리에서 돈다).
RAM 은 실행파일 + 합성 상태(창 구조체 · 칸 표)로 짓는다 — 라이브 덤프에 기대지 않는다.
"""

import os
import struct
import unittest

import _path  # noqa: F401
import common
import halfwidth
import tilecomp

CODE, DATA = 0x80150000, 0x80158000
FONT = 0x80070BD4
BASE = 63  # 실제 대사창의 글자 칸 기점(창 구조체 +0x22, 실측)


def build_ram(cols=24, base=BASE):
    exe = common.read_file(common.EXE_PATH)
    ram = bytearray(0x200000)
    body = exe[common.EXE_HDR :]
    ram[0x10000 : 0x10000 + len(body)] = body
    # 칸 표(0x800C6F20): 칸 i → 열 i%21 · 줄 i//21, 칸 12px · 13px 높이
    for i in range(240):
        px, y = (i % 21) * 12, (i // 21) * 13
        struct.pack_into("<H", ram, 0xC6F20 + 2 * i, px | (y << 8))
    w = 0x1EF9C8  # 창 0
    struct.pack_into("<H", ram, w + 6, cols)
    struct.pack_into("<H", ram, w + 8, 4)
    struct.pack_into("<H", ram, w + 0x1E, 7)  # 틀 칸 기점 — 글자 칸 기점(0x22)과 다르다
    struct.pack_into("<H", ram, w + 0x22, base)
    struct.pack_into("<h", ram, 0x1F3452, 0)
    return ram


@unittest.skipUnless(os.path.exists(common.DISC_DIR), "원본 없음")
class TestHalfwidth(unittest.TestCase):
    COLS, BASE0 = 24, BASE  # 창 열 수 · 글자 칸 기점

    @classmethod
    def setUpClass(cls):
        import uploader_sim

        cls.uploader_sim = uploader_sim
        cls.ram = build_ram(cls.COLS, cls.BASE0)
        cls.codes = [c for c in range(1, 400) if any(cls.glyph(c))][:48]

    @classmethod
    def glyph(cls, c):
        a = (FONT + 18 * c) & 0x1FFFFF
        return bytes(cls.ram[a : a + 18])

    def run_batches(self, batches, half, hook=True):
        r = bytearray(self.ram)
        if hook:
            halfwidth.install(r, CODE, DATA, sorted(half))
        sim = self.uploader_sim.Sim(bytes(r))
        return sim.run_batches(batches)

    def final(self, loads):
        out = {}
        for x, y, _w, _h, d in loads:
            out[(x, y)] = d
        return out

    def key(self, cell):
        i = cell
        return (0x140 + 3 * (i % 21), (i // 21) * 13)

    def model(self, rows, half):
        tiles = {}
        for row, start, codes in rows:
            line = tilecomp.Line(pos=start * 12)
            for c in codes:
                adv = 6 if c in half else 12
                for t, tile in line.put(tilecomp.unpack(self.glyph(c)), adv):
                    tiles[row * self.COLS + t] = tilecomp.expand(tile)
        return tiles

    def check(self, rows, half):
        batches = [(self.BASE0 + row * self.COLS + start, codes) for row, start, codes in rows]
        final = self.final(self.run_batches(batches, half))
        for cell, data in self.model(rows, half).items():
            self.assertEqual(final.get(self.key(self.BASE0 + cell)), data, f"칸 {cell}")

    def test_반각이_없으면_원판과_같은_타일(self):
        batches = [(BASE, self.codes[:24]), (BASE + 24, self.codes[24:48])]
        a = self.final(self.run_batches(batches, set(), hook=False))
        b = self.final(self.run_batches(batches, set(), hook=True))
        self.assertEqual(a, b)

    def test_한_줄_반각_섞임(self):
        c = self.codes
        self.check([(0, 0, c[:20])], set(c[2:20:3]))

    def test_반각_연속과_줄_둘(self):
        c = self.codes
        self.check([(0, 0, c[:22]), (1, 0, c[22:46])], set(c[3:12]) | set(c[30:36]))

    def test_줄_중간에서_시작하는_묶음은_그_칸_위치로(self):
        c = self.codes
        half = set(c[:4])
        batches = [(self.BASE0 + 5, c[:4])]
        final = self.final(self.run_batches(batches, half))
        want = self.model([(0, 5, c[:4])], half)
        for cell, data in want.items():
            self.assertEqual(final.get(self.key(self.BASE0 + cell)), data)

    def run_josa(self, batches):
        """조사 블록(표지 → 조사 글리프)이 켜진 훅으로 돌린다 — 받침 비트표는 램 안 빈 자리에 둔다."""
        c = self.codes
        bt_at = 0x80170000
        bt = bytearray(256)
        bt[c[3] >> 3] |= 1 << (c[3] & 7)  # c[3] = 받침 있는 글자, c[4] = 받침 없는 글자(비트 0)
        r = bytearray(self.ram)
        josa = {"markers": [(c[10], c[11], c[12]), (c[13], c[14], c[15]), (c[16], c[17], c[18])], "bt_addr": bt_at, "bt": bytes(bt)}
        halfwidth.install(r, CODE, DATA, [], josa=josa)
        return self.final(self.uploader_sim.Sim(bytes(r)).run_batches(batches))

    def test_조사_표지는_직전_글자_받침으로_갈린다(self):
        c = self.codes
        for mk, w, wo in ((c[10], c[11], c[12]), (c[13], c[14], c[15]), (c[16], c[17], c[18])):
            have = self.run_josa([(BASE, [c[3], mk]), (BASE + 24, [c[4], mk])])
            want = self.run_josa([(BASE, [c[3], w]), (BASE + 24, [c[4], wo])])
            self.assertEqual(have, want, f"표지 {mk}")

    def test_조사_훅은_표지_아닌_글자를_안_건드린다(self):
        c = self.codes
        batches = [(BASE, c[20:44])]
        a = self.final(self.run_batches(batches, set(), hook=False))
        self.assertEqual(self.run_josa(batches), a)

    def test_직전_글자는_묶음을_건너_이어진다(self):
        # 변수(아이템 이름)와 조사가 다른 묶음에 있어도 직전 글자 받침을 본다
        c = self.codes
        have = self.run_josa([(BASE, [c[3]]), (BASE + 1, [c[10]])])
        want = self.run_josa([(BASE, [c[3]]), (BASE + 1, [c[11]])])
        self.assertEqual(have, want)


@unittest.skipUnless(os.path.exists(common.DISC_DIR), "원본 없음")
class TestHalfwidthNarrow(TestHalfwidth):
    """창 열 수가 24 가 아닌 창(메뉴·상태·장비 …, 10-25 실측 열 3~20) — 훅이 창마다 열 수·칸 기점을 읽어 같은 모델을 따른다."""

    COLS, BASE0 = 11, 83

    def test_열_11_창_두_줄_반각_섞임(self):
        c = self.codes
        self.check([(0, 0, c[:11]), (1, 0, c[11:22])], set(c[2:9:3]) | set(c[13:19]))

    def test_열_11_창_줄_중간_시작(self):
        c = self.codes
        self.check([(0, 3, c[:6]), (1, 2, c[6:10])], set(c[:2]) | set(c[7:9]))

    # 상위 클래스의 24 열 전제 시험은 이 창에선 뜻이 없다
    def test_반각이_없으면_원판과_같은_타일(self):
        batches = [(self.BASE0, self.codes[:11]), (self.BASE0 + 11, self.codes[11:22])]
        a = self.final(self.run_batches(batches, set(), hook=False))
        b = self.final(self.run_batches(batches, set(), hook=True))
        self.assertEqual(a, b)

    def test_한_줄_반각_섞임(self):
        pass

    def test_반각_연속과_줄_둘(self):
        pass


@unittest.skipUnless(os.path.exists(common.DISC_DIR), "원본 없음")
class TestHalfwidthOtherWindow(TestHalfwidthNarrow):
    """🔴 현재 창 번호(`0x801F3452`)가 **다른 창**을 가리키는데 글자는 둘째 창 칸에 그려지는 경우(타이틀 불러오기 목록, 10-25) — 현재 창 안이 아니면 창 배열을 훑어 칸이 든 창을 찾는다."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        r = bytearray(cls.ram)
        w0, w1 = 0x1EF9C8, 0x1EF9C8 + 42
        r[w1 : w1 + 42] = r[w0 : w0 + 42]  # 둘째 창 = 열 11·칸 기점 83
        struct.pack_into("<H", r, w0 + 6, 7)  # 현재 창(0번) = 열 7·칸 기점 63 — 글자 칸은 이 창 밖이다
        struct.pack_into("<H", r, w0 + 0x22, 63)
        struct.pack_into("<H", r, w0 + 8, 2)  # 현재 창 칸 범위 63~76 — 둘째 창(83~)과 안 겹친다
        struct.pack_into("<h", r, 0x1F3452, 0)
        cls.ram = r


@unittest.skipUnless(os.path.exists(common.DISC_DIR), "원본 없음")
class TestCursorRow(TestHalfwidth):
    """커서(선택) 줄 경로 — `0x800178C4` 가 부르는 타일 만들기(`0x800177C0`)가 합성한 줄과 같은 타일을 캐시에 채운다(10-25: 커서 줄만 공백이 전각이던 결함)."""

    COLS, BASE0 = 7, 63
    CODE2 = halfwidth.CAVE2
    CACHE, CODES = 0x801F6000, 0x801FE000
    # 상위 클래스의 24 열 전제 시험은 이 창에선 뜻이 없다
    test_반각이_없으면_원판과_같은_타일 = test_한_줄_반각_섞임 = test_반각_연속과_줄_둘 = None
    test_줄_중간에서_시작하는_묶음은_그_칸_위치로 = test_조사_표지는_직전_글자_받침으로_갈린다 = None
    test_조사_훅은_표지_아닌_글자를_안_건드린다 = test_직전_글자는_묶음을_건너_이어진다 = None

    def run_row(self, codes, half, color=0):
        from unicorn.mips_const import (
            UC_MIPS_REG_A0,
            UC_MIPS_REG_A1,
            UC_MIPS_REG_A2,
            UC_MIPS_REG_A3,
            UC_MIPS_REG_PC,
            UC_MIPS_REG_RA,
            UC_MIPS_REG_S3,
            UC_MIPS_REG_S4,
            UC_MIPS_REG_SP,
        )

        r = bytearray(self.ram)
        halfwidth.install(r, CODE, DATA, sorted(half))
        halfwidth.install_hx(r, self.CODE2, CODE, DATA)
        sim = self.uploader_sim.Sim(bytes(r))
        arr = list(codes) + [0] * (self.COLS - len(codes))
        sim.wr(self.CODES, b"".join(struct.pack("<H", c) for c in arr))
        sim.w32(0x80097BBC, self.CACHE)
        sim.wr(self.CACHE, bytes(84 * (self.COLS + 2)))
        mu = sim.mu
        mu.reg_write(UC_MIPS_REG_SP, 0x801FF000)
        mu.reg_write(UC_MIPS_REG_RA, sim.stub_ret)
        mu.reg_write(UC_MIPS_REG_A0, self.CODES)
        mu.reg_write(UC_MIPS_REG_A1, self.COLS)
        mu.reg_write(UC_MIPS_REG_A2, self.COLS)
        mu.reg_write(UC_MIPS_REG_A3, color)
        mu.reg_write(UC_MIPS_REG_S3, 0x801EF9C8)
        mu.reg_write(UC_MIPS_REG_S4, 0)
        mu.reg_write(UC_MIPS_REG_PC, self.CODE2)
        try:
            mu.emu_start(self.CODE2, sim.stub_ret, count=3_000_000)
        except Exception as e:  # noqa: BLE001
            if mu.reg_read(UC_MIPS_REG_PC) != sim.stub_ret:
                raise RuntimeError(f"커서 줄이 멈췄다 @{mu.reg_read(UC_MIPS_REG_PC):#x}: {e}") from e
        return [sim.rd(self.CACHE + 84 * k, 78) for k in range(self.COLS)]

    def test_커서_줄은_합성_줄과_같은_타일(self):
        c = self.codes
        for codes, half in (
            (c[:6], {c[3]}),
            (c[:7], set(c[1:3]) | {c[5]}),
            (c[:4], {c[0], c[1], c[2], c[3]}),
            (c[:6], set()),
        ):
            tiles = self.run_row(codes, half)
            want = self.model([(0, 0, codes)], half)
            for cell, data in want.items():
                self.assertEqual(tiles[cell], data, f"칸 {cell} 코드 {len(codes)}")

    def run_list_line(self, codes, half, cols=14, a3=8):
        """로드/세이브 목록 줄 `0x80017BEC`(왼쪽 지명 + 오른쪽 시간)를 돌려 왼쪽 칸 타일을 읽는다 — 훅이 칸을 미리 채운다(HXQ)."""
        from unicorn.mips_const import (
            UC_MIPS_REG_A0,
            UC_MIPS_REG_A1,
            UC_MIPS_REG_A2,
            UC_MIPS_REG_A3,
            UC_MIPS_REG_PC,
            UC_MIPS_REG_RA,
            UC_MIPS_REG_SP,
        )

        r = bytearray(self.ram)
        w = 0x1EF9C8
        struct.pack_into("<H", r, w + 6, cols)
        halfwidth.install(r, CODE, DATA, sorted(half))
        halfwidth.install_hx(r, self.CODE2, CODE, DATA)
        sim = self.uploader_sim.Sim(bytes(r))
        name = 0x801FE000
        sim.wr(name, b"".join(struct.pack("<H", c) for c in [*codes, 0x8002]))
        timebuf = 0x801FE100
        sim.wr(timebuf, bytes([0x0A]) * 16)
        sim.w32(0x80097BBC, self.CACHE)
        sim.wr(self.CACHE, bytes(84 * (cols + 2)))
        sp = 0x801FF000
        sim.w16(sp + 0x10, 0)
        sim.w16(sp + 0x14, 0)
        mu = sim.mu
        mu.reg_write(UC_MIPS_REG_SP, sp)
        mu.reg_write(UC_MIPS_REG_RA, sim.stub_ret)
        mu.reg_write(UC_MIPS_REG_A0, 0x801EF9C8)
        mu.reg_write(UC_MIPS_REG_A1, name)
        mu.reg_write(UC_MIPS_REG_A2, timebuf)
        mu.reg_write(UC_MIPS_REG_A3, a3)
        mu.reg_write(UC_MIPS_REG_PC, 0x80017BEC)
        try:
            mu.emu_start(0x80017BEC, sim.stub_ret, count=3_000_000)
        except Exception as e:  # noqa: BLE001
            if mu.reg_read(UC_MIPS_REG_PC) != sim.stub_ret:
                raise RuntimeError(f"목록 줄이 멈췄다 @{mu.reg_read(UC_MIPS_REG_PC):#x}: {e}") from e
        return [sim.rd(self.CACHE + 84 * k, 78) for k in range(cols)]

    def test_목록_줄_왼쪽_칸이_합성_줄과_같다(self):
        c = self.codes
        codes, half = c[:9], {c[2], c[5]}
        tiles = self.run_list_line(codes, half, cols=14, a3=8)  # 왼쪽 칸 = 14 − 4 = 10
        want = self.model([(0, 0, codes)], half)
        for cell, data in want.items():
            self.assertEqual(tiles[cell], data, f"칸 {cell}")

    def test_둘째_풀기는_깃발이_0일_때_원래_함수로_넘어간다(self):
        """다른 호출처(`0x800171A0`)는 HX2 를 거쳐도 원래 풀기를 한다 — HX2 끝이 `j 0x80016268`."""
        words, lab = halfwidth.build_hx(self.CODE2, CODE, DATA)
        want = 0x08000000 | ((halfwidth.EXPAND_FN >> 2) & 0x3FFFFFF)
        self.assertIn(want, words[(lab["hx2"] - self.CODE2) // 4 :])


@unittest.skipUnless(os.path.exists(common.DISC_DIR), "원본 없음")
class TestCave(unittest.TestCase):
    """🔴 동굴이 정말 죽은 구간인가 — 바깥에서 분기·점프로 **들어오는** 곳이 없어야 한다(10-25: 꼬리 점프 `j 0x800189B8` 을 내부 점프로 오분류해 살아 있는 함수를 덮고 필드 로드에서 죽었다).
    함수 포인터(워드 값)·`lui+주소` 참조도 없어야 한다."""

    def test_바깥에서_들어오는_진입이_없다(self):
        self.entries_ok(halfwidth.CAVE, halfwidth.CAVE_SIZE)

    def test_둘째_동굴도_들어오는_진입이_없다(self):
        self.entries_ok(halfwidth.CAVE2, halfwidth.CAVE2_SIZE)

    def test_동굴_앞은_함수_끝이다(self):
        """🔴 둘째 동굴을 처음 잡은 자리(`0x800274F4`)는 함수 몸통 중간이었다 — `jal 0x800274EC` 로 시작 8B 앞이 불렸다. 구간 바로 앞이 `jr ra` + 지연 슬롯이어야 진짜 함수 경계다."""
        exe = common.read_file(common.EXE_PATH)
        for lo in (halfwidth.CAVE, halfwidth.CAVE2):
            o = lo - common.EXE_TADDR + common.EXE_HDR
            self.assertEqual(struct.unpack_from("<I", exe, o - 8)[0], 0x03E00008, hex(lo))

    def entries_ok(self, lo, size):
        exe = common.read_file(common.EXE_PATH)
        base, hdr = common.EXE_TADDR, common.EXE_HDR
        hi = lo + size
        n = (len(exe) - hdr) // 4
        bad = []
        for i in range(n):
            w = struct.unpack_from("<I", exe, hdr + 4 * i)[0]
            a = base + 4 * i
            inside = lo <= a < hi
            op = w >> 26
            t = None
            if op in (2, 3):
                t = ((w & 0x3FFFFFF) << 2) | 0x80000000
            elif op in (1, 4, 5, 6, 7):
                imm = w & 0xFFFF
                imm = imm - 0x10000 if imm >= 0x8000 else imm
                t = a + 4 + imm * 4
            if t is not None and lo <= t < hi and not inside:
                bad.append(("진입", hex(a), hex(t)))
            if lo <= w < hi and not inside:
                bad.append(("포인터", hex(a), hex(w)))
        self.assertEqual(bad, [])

    def test_동굴_바로_뒤는_함수_시작이다(self):
        """동굴 끝 직전이 `jr ra` + 지연 슬롯이어야 한다(뒤 함수를 안 덮는다)."""
        exe = common.read_file(common.EXE_PATH)
        end = halfwidth.CAVE + halfwidth.CAVE_SIZE - common.EXE_TADDR + common.EXE_HDR
        jr_ra = struct.unpack_from("<I", exe, end - 8)[0]
        self.assertEqual(jr_ra, 0x03E00008)


if __name__ == "__main__":
    unittest.main()
