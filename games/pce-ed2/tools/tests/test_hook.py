"""후킹 루틴의 논리 — 시뮬레이터로 돈다(에뮬·원본 없이). 글리프 코드 → 풀 칸 → 18B → 24B 가 `font` 와 같아야 한다."""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import font
import hook
import sim6280


def synthetic(n: int) -> list[bytes]:
    rnd = random.Random(7)
    out = []
    for _ in range(n):
        rows = [rnd.getrandbits(12) << 4 for _ in range(12)]
        out.append(b"".join(v.to_bytes(2, "big") for v in rows))
    return out


def machine(glyphs: list[bytes]):
    """패치 적용 이미지 → 시뮬레이터(뱅크별 8KB, 본 프로그램은 0xFF 패딩으로 채운 가짜)."""
    banks = {b: bytearray(b"\xff" * 8192) for b in range(0x68, 0x72)}
    for lin, new, _old, _label in hook.build(glyphs):
        rel_off = lin - hook.PROG_REL * 2048
        b, off = hook.BANK0 + rel_off // 8192, rel_off % 8192
        if _label.startswith("hook seam"):
            continue  # 이음매는 호출자 쪽이다 — 아래에서 직접 호출한다
        banks[b][off : off + len(new)] = new
    # MPR: 0 = 하드웨어, 1 = 작업 RAM, 2 = 0x68, 3 = 0x6C, 4 = 임의(씬 패키지), 5~7 = 0xF9..
    sim = sim6280.Sim(banks, [0xFF, 0xF8, 0x68, 0x6C, 0x75, 0x76, 0x77, 0x87], bytearray(8192))
    sim.banks[0x75] = bytearray(b"\x5a" * 8192)
    return sim


class Hook(unittest.TestCase):
    def call(self, sim, idx: int):
        lead, trail = divmod(idx, font.PER_LEAD)
        sim.wr(0x20F9, font.LEAD0 + lead)
        sim.wr(0x20F8, font.TRAIL0 + trail)
        sim.sp = 0xFF
        return self.follow(sim, sim.run(0x6000 + hook.HOOK_OFF))

    def follow(self, sim, r):
        """`JMP` 가 루틴 안(우리 `orig` 디딤돌)이면 따라가, 마침내 어디로 나가는지 돌려준다."""
        while r not in (-1, hook.ORIG_CHECK):
            r = sim.run(r)
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


if __name__ == "__main__":
    unittest.main()
