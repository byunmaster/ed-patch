"""후킹 루틴의 논리 — 시뮬레이터로 돈다(에뮬·원본 없이). 글리프 코드 → 풀 칸 → 18B → 24B 가 `font` 와 같아야 한다."""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import font
import hook
import layout
import sim6280


def synthetic(n: int) -> list[bytes]:
    rnd = random.Random(7)
    out = []
    for _ in range(n):
        rows = [(rnd.getrandbits(11) << 5) if r < 11 else 0 for r in range(12)]  # 11×11 — 행 11·열 11 은 빈다
        out.append(b"".join(v.to_bytes(2, "big") for v in rows))
    return out


def machine(glyphs: list[bytes], flags=None, josa_idx=None):
    """패치 적용 이미지 → 시뮬레이터(뱅크별 8KB, 본 프로그램은 0xFF 패딩으로 채운 가짜)."""
    orig = bytearray(b"\xff" * (10 * layout.BANK))
    seam = (hook.SEAM_BANK - layout.BANK0) * layout.BANK + hook.SEAM_OFF
    orig[seam : seam + 2] = hook.SEAM_OLD
    aseam = (hook.ASCII_SEAM_BANK - layout.BANK0) * layout.BANK + hook.ASCII_SEAM_OFF
    orig[aseam : aseam + 2] = hook.ASCII_SEAM_OLD
    for b, o, n in layout.ZERO_PADDING:  # 0 칸
        z = (b - layout.BANK0) * layout.BANK + o
        orig[z : z + n] = bytes(n)
    prog = layout.Prog(orig=bytes(orig))
    hook.reserve(prog)
    hook.install(prog, glyphs, flags, josa_idx)
    banks = {
        b: bytearray(orig[(b - 0x68) * layout.BANK : (b - 0x67) * layout.BANK])
        for b in range(0x68, 0x72)
    }
    for lin, new, _old, label in prog.spans():
        rel_off = lin - layout.PROG_REL * 2048
        b, off = layout.BANK0 + rel_off // layout.BANK, rel_off % layout.BANK
        if label.startswith("hook seam"):  # (이음매는 호출자 쪽 — 아래에서 직접 호출한다)
            continue  # 이음매는 호출자 쪽이다 — 아래에서 직접 호출한다
        banks[b][off : off + len(new)] = new
    # MPR: 0 = 하드웨어, 1 = 작업 RAM, 2 = 0x68, 3 = 0x6C, 4 = 임의(씬 패키지), 5~7 = 0xF9..
    sim = sim6280.Sim(banks, [0xFF, 0xF8, 0x68, 0x6C, 0x75, 0x76, 0x77, 0x87], bytearray(8192))
    sim.banks[0x75] = bytearray(b"\x5a" * 8192)
    return sim


def with_package(sim, local: list[bytes], with_table: bool = True):
    """패키지 가짜 — 뱅크 0x73(머리표 · 메시지 표) + 0x74(지역 글리프 표)."""
    b73, b74 = bytearray(8192), bytearray(8192)
    b73[12:15] = bytes([0, 0x00, 0x02])  # 항목 4: 메시지 표 = 오프셋 0x0200
    if with_table:
        b73[0x200:0x202] = bytes([0x00, 0x21])  # 표 항목 0: 지역 글리프 표 = 상대 뱅크 1 + 0x0100
    for k, g in enumerate(local):
        b74[0x100 + 16 * k : 0x100 + 16 * (k + 1)] = font.pack(g)
    sim.banks[0x73], sim.banks[0x74] = b73, b74
    sim.wr(0x2041, 0x73)  # ZP $41 = 패키지 첫 뱅크


class Hook(unittest.TestCase):
    def test_지역_표_글리프가_풀린다(self):
        gl, loc = synthetic(300), synthetic(5)
        sim = machine(gl)
        with_package(sim, loc)
        for k in range(5):
            r = self.call(sim, 300 + k)
            self.assertEqual(r, -1)
            self.assertEqual(sim.c, 0)
            self.assertEqual(bytes(sim.ram[0x109B : 0x109B + 24]), loc[k], f"지역 {k}")
            self.assertEqual(sim.mpr[4], 0x75, "MPR4 되돌림")

    def test_지역_표가_없으면_원래_흐름(self):
        sim = machine(synthetic(300))
        with_package(sim, synthetic(2), with_table=False)
        sim.x = 0x44
        self.assertEqual(self.call(sim, 300), hook.ORIG_CHECK)
        self.assertEqual(sim.x, 0x44)
        self.assertEqual(sim.mpr[4], 0x75)

    def call(self, sim, idx: int):
        lead, trail = divmod(idx, font.PER_LEAD)
        sim.wr(0x20F9, font.LEAD0 + lead)
        sim.wr(0x20F8, font.TRAIL0 + trail)
        sim.sp = 0xFF
        return self.follow(sim, sim.run(0x6000 + hook.HOOK_OFF), 0xFF)

    def follow(self, sim, r, base_sp=0xFF):
        """`JMP` 가 루틴 안(우리 `orig` 디딤돌)이면 따라가, 마침내 어디로 나가는지 돌려준다."""
        while r not in (-1, hook.ORIG_CHECK):
            r = sim.run(r, base_sp=base_sp)
        return r

    def test_모든_글리프가_정확히_풀린다(self):
        gl = synthetic(300)
        sim = machine(gl)
        for idx in (0, 1, 215, 216, 217, 219, 220, 221, 255, 299):
            r = self.call(sim, idx)
            self.assertEqual(r, -1, f"글리프 {idx}: 풀 안인데 원래 흐름으로 갔다")
            self.assertEqual(sim.c, 0, "처리했으면 C=0")
            got = bytes(sim.ram[0x109B : 0x109B + 24])
            self.assertEqual(got, gl[idx], f"글리프 {idx} 불일치")

    def test_레지스터와_창을_되돌린다(self):
        sim = machine(synthetic(10))
        sim.x = 0x33
        self.call(sim, 3)
        self.assertEqual(sim.x, 0x33, "X 를 지켜야 한다")
        self.assertEqual(sim.mpr[4], 0x75, "MPR4 를 되돌려야 한다")
        self.assertEqual(sim.sp, 0xFF, "스택 균형")
        self.assertEqual(sim.i, 0, "인터럽트 마스크 복원")

    def test_리드_범위_밖은_원래_표로(self):
        sim = machine(synthetic(10))
        sim.wr(0x20F9, 0x81)
        sim.wr(0x20F8, 0x62)
        sim.sp = 0xFF
        self.assertEqual(self.follow(sim, sim.run(0x6000 + hook.HOOK_OFF)), hook.ORIG_CHECK)

    def test_풀_밖_번호는_원래_표로(self):
        sim = machine(synthetic(10))
        self.assertEqual(self.call(sim, 100), hook.ORIG_CHECK)
        self.assertEqual(sim.x, 0)  # X 복원(원래 값 0)

    def test_pack_unpack(self):
        for g in synthetic(20):
            self.assertEqual(font.unpack(font.pack(g)), g)

    def test_11x11_밖이_차면_묶기를_거부한다(self):
        g = bytearray(synthetic(1)[0])
        g[23] |= 0x10  # 행 11
        with self.assertRaises(AssertionError):
            font.pack(bytes(g))


class Josa(unittest.TestCase):
    """동적 조사 — 리드 F9 토큰이 **직전에 그린 글자의 받침**으로 두 꼴 중 하나를 낸다."""

    def draw_josa(self, t, sim, kind):
        sim.wr(0x20F9, font.JOSA_LEAD)
        sim.wr(0x20F8, font.TRAIL0 + kind)
        sim.sp = 0xFF
        r = t.follow(sim, sim.run(0x6000 + hook.HOOK_OFF), 0xFF)
        return r, bytes(sim.ram[0x109B : 0x109B + 24])

    def test_받침에_따라_꼴을_고른다(self):
        gl = synthetic(300)
        flags = [0] * 300
        flags[10] = font.FLAG_BATCHIM
        josa_idx = [200 + k for k in range(8)]  # 종류 k: 200+2k = 받침 있음, 201+2k = 없음
        sim = machine(gl, flags, josa_idx)
        t = Hook()
        for kind in range(4):
            t.call(sim, 10)  # 받침 있는 글자를 그린다(조사 글리프 자신이 플래그를 덮으므로 매번)
            r, got = self.draw_josa(t, sim, kind)
            self.assertEqual(r, -1)
            self.assertEqual(got, gl[200 + 2 * kind], f"종류 {kind} 받침 있음")
        for kind in range(4):
            t.call(sim, 11)  # 받침 없는 글자
            r, got = self.draw_josa(t, sim, kind)
            self.assertEqual(got, gl[201 + 2 * kind], f"종류 {kind} 받침 없음")
        self.assertEqual(sim.sp, 0xFF)
        self.assertEqual(sim.mpr[4], 0x75)

    def test_모르는_종류는_원래_표로(self):
        sim = machine(synthetic(300), [0] * 300, [200 + k for k in range(8)])
        t = Hook()
        sim.wr(0x20F9, font.JOSA_LEAD)
        sim.wr(0x20F8, font.TRAIL0 + 9)
        sim.sp = 0xFF
        self.assertEqual(t.follow(sim, sim.run(0x6000 + hook.HOOK_OFF), 0xFF), hook.ORIG_CHECK)


class AsciiSeam(unittest.TestCase):
    """ASCII 한 글자를 그리기 직전 받침 플래그를 맞추고, 레지스터를 지킨 채 원래 그리기(`$6513`)로 이어 간다."""

    def run_ascii(self, ch):
        sim = machine(synthetic(10))
        entry = sim.banks  # noqa: F841
        sim.wr(0x20F9, ch)
        sim.a, sim.x, sim.y = 0x11, 0x22, 0x33
        sim.sp = 0xFF
        # 루틴 시작 주소 = 설치된 이음매 대상 — 라벨을 직접 구한다
        a = hook._routine(hook.MAX_RUNS)
        r = sim.run(a.labels["ascii"])
        return sim, r

    def test_영문과_부호는_받침_없음_숫자는_읽는_소리(self):
        for ch, want in [(ord("A"), 0), (ord("."), 0), (ord("0"), font.FLAG_BATCHIM), (ord("2"), 0), (ord("8"), font.FLAG_BATCHIM), (ord("9"), 0)]:
            sim, r = self.run_ascii(ch)
            self.assertEqual(r, hook.ASCII_DRAW, "원래 그리기로 이어진다")
            lastb = a_lastb(sim)
            self.assertEqual(lastb, want, chr(ch))
            self.assertEqual((sim.a, sim.x, sim.y, sim.sp), (0x11, 0x22, 0x33, 0xFF), "레지스터·스택을 지킨다")


def a_lastb(sim):
    a = hook._routine(hook.MAX_RUNS)
    return sim.rd(a.labels["LASTB"])


class Pixel(unittest.TestCase):
    """글자 모양이 11×11 묶음을 거쳐도 픽셀 단위로 같다 — 한글 음절 전부(11,172) 묶기·풀기 + 문안에 쓰는 글자 전수는 후킹 루틴(시뮬)까지."""

    def test_한글_음절_전부_왕복(self):
        for cp in range(0xAC00, 0xD7A4):
            g = font.glyph(chr(cp))
            self.assertEqual(font.unpack(font.pack(g)), g, f"U+{cp:04X}")

    def test_문안_글자_전수가_후킹_루틴을_거쳐도_같다(self):
        import glob

        chars = set()
        for f in glob.glob(str(Path(__file__).resolve().parents[2] / "data" / "dialogue_ko" / "*.tsv")):
            for ln in open(f, encoding="utf-8"):
                if "\t" in ln and not ln.startswith("#"):
                    chars |= set(c for c in ln.split("\t")[1] if c not in " \n\f§¶")
        glyphs = [font.glyph(c) for c in sorted(chars)]
        self.assertGreater(len(glyphs), 700)
        sim = machine(glyphs)
        t = Hook()
        for idx, g in enumerate(glyphs):
            self.assertEqual(t.call(sim, idx), -1)
            self.assertEqual(bytes(sim.ram[0x109B : 0x109B + 24]), g, f"글리프 {idx} {sorted(chars)[idx]!r}")


if __name__ == "__main__":
    unittest.main()
