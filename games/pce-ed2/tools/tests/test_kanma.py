"""章間 번역(`kanma.py`) — 표기 해석 · 겹부호 · 줄 폭 · **후킹 기계어를 시뮬레이터로**(원본 없이)."""

import random
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import font
import kanma
import sim6280


def glyph24(seed: int) -> bytes:
    rnd = random.Random(seed)
    rows = [rnd.getrandbits(12) & 0xFFE for _ in range(11)] + [0]
    return b"".join((v << 4).to_bytes(2, "big") for v in rows)


class Tokens(unittest.TestCase):
    def test_표기가_바이트가_된다(self):
        g = kanma.Glyphs()
        b = kanma.encode_text("/{f06}가 나{w14}/{02}", g)
        self.assertEqual(b[:3], bytes([0x01, 0x15, 0x06]))
        self.assertIn(bytes([0x0C, 0x14]), b)
        self.assertEqual(b[-2:], bytes([0x01, 0x02]))
        self.assertEqual(g.chars(), ["가", "나"])

    def test_공백은_반각_공백_제어(self):
        # 11-06 — 해석기 개조: 공백 = 제어 0x1F(4px 전진), 전각 공백(`81 40`, 12px)이 아니다
        self.assertEqual(kanma.encode_text("가 나", kanma.Glyphs())[2:3], bytes([kanma.HALF_CODE]))

    def test_반각_공백_루틴_바이트(self):
        import dis6280

        code = kanma.half_space_code(0x7000)
        lines = dis6280.disasm(code, 0x7000, 0, 40)
        self.assertIn("JSR $5BA1", " ".join(lines))  # 보통 그리기 경로로 빈 칸을 한 번 그린다
        self.assertIn("JSR $5D21", " ".join(lines))  # 위상 1 → 0 은 패턴 포인터 +0x20(줄바꿈 `$58F1` 과 같은 처리)
        self.assertEqual(code[-1], 0x60)  # RTS
        self.assertEqual(code[:2], bytes([0xDA, 0x5A]))  # PHX · PHY — 호출한 해석기가 X·Y 를 쓴다

    def test_부호_뒤_공백은_안_만든다(self):
        toks = kanma.tokenize("가. 나, 다! 라… 마")
        sp = [t for t in toks if t[0] == "sp"]
        self.assertEqual(len(sp), 1)  # 「…」 뒤 공백만 남는다

    def test_겹부호는_한_칸(self):
        toks = kanma.tokenize("가!! 나?! 20")
        self.assertIn(("g", "!!"), toks)
        self.assertIn(("g", "?!"), toks)
        self.assertEqual([t for t in toks if t[0] == "g"][-1], ("g", "20"))  # 두 자리 숫자는 한 칸
        for d in (*kanma.DIGRAPHS, "20", "5", "99", "07"):
            font.pack(kanma.glyph_of(d))  # 11×11 묶음 조건을 지킨다

    def test_범위_물결은_두_칸(self):
        toks = kanma.tokenize("5～6세대")
        self.assertEqual(toks[:3], [("g", "5～"), ("g", "^6"), ("g", "세")])
        for t in ("5～", "^6"):
            font.pack(kanma.glyph_of(t))

    def test_좁은_숫자_열개_모두_5x11(self):
        for d, pat in kanma.DIGIT5.items():
            rows = pat.split()
            self.assertEqual(len(rows), 11, d)
            self.assertTrue(all(len(r) == 5 for r in rows), d)

    def test_번역표가_줄_폭을_지킨다(self):
        self.assertEqual(kanma.check_ko(), [])

    def test_메시지_나누기(self):
        pre, name, rest = kanma.split_message(b"\x15\x08\x17AB\x18\x01xy")
        self.assertEqual((pre, name, rest), (b"\x15\x08", b"AB", b"\x01xy"))
        self.assertEqual(kanma.split_message(b"xy\x01z"), (b"", None, b"xy\x01z"))


class Hook(unittest.TestCase):
    """후킹이 표(앞·뒤) 글리프를 24B 로 풀어 `($FA)` 에 쓰고 레지스터·MPR6 를 지키는가."""

    N_A, A_OFF, B_OFF, B_BANK = 40, 0x4100, 0x8F30, 0x6C

    def machine(self, n: int):
        gl = [glyph24(k) for k in range(n)]
        banks = {b: bytearray(8192) for b in range(0x68, 0x70)}
        hook_org = 0x6200
        gbuf = 0x7F00
        a_addr = 0x4000 + self.A_OFF
        b_addr = 0x4000 + self.B_OFF
        code = kanma.hook_code(
            hook_org, a_addr, self.N_A, (b_addr - 16 * self.N_A) & 0xFFFF, gbuf, self.B_BANK
        )

        # 논리 주소 → 뱅크: 0x4000=0x68, 0x6000=0x69, 0x8000=0x6A, 0xA000=0x6B, 0xC000=0x6C
        def put(addr, data):
            for i, v in enumerate(data):
                a = addr + i
                banks[0x68 + ((a - 0x4000) >> 13)][a & 0x1FFF] = v

        put(hook_org, code)
        put(a_addr, b"".join(font.pack(g) for g in gl[: self.N_A]))
        put(b_addr, b"".join(font.pack(g) for g in gl[self.N_A :]))
        sim = sim6280.Sim(banks, [0xFF, 0xF8, 0x68, 0x69, 0x6A, 0x6B, 0x6F, 0x87], bytearray(8192))
        sim.banks[0x6F] = bytearray(
            b"\xaa" * 8192
        )  # MPR6 의 원래 뱅크(장면 자료) — 걸었다 되돌려야 한다
        return sim, gl, hook_org

    def call(self, sim, org, idx):
        lead, trail = divmod(idx, font.PER_LEAD)
        sim.wr(0x20F9, font.LEAD0 + lead)
        sim.wr(0x20F8, font.TRAIL0 + trail)
        sim.wr(0x20FA, 0xE6)
        sim.wr(0x20FB, 0x30)  # ($FA) = $30E6
        sim.sp = 0xFF
        sim.x, sim.y = 0x33, 0x44
        return sim.run(org)

    def test_앞_뒤_표_글리프(self):
        sim, gl, org = self.machine(300)
        for idx in (0, 1, 39, 40, 41, 219, 220, 221, 299):
            r = self.call(sim, org, idx)
            self.assertEqual(r, -1, f"{idx}: 글리프 안인데 BIOS 로 갔다")
            got = bytes(sim.ram[0x10E6 : 0x10E6 + 24])
            self.assertEqual(got, gl[idx], f"글리프 {idx} 불일치")
            self.assertEqual((sim.x, sim.y), (0x33, 0x44), "X·Y 를 지킨다")
            self.assertEqual(sim.mpr[6], 0x6F, "MPR6 되돌림")

    def test_우리_코드가_아니면_BIOS(self):
        sim, _gl, org = self.machine(50)
        sim.wr(0x20F9, 0x81)
        sim.wr(0x20F8, 0x40)
        sim.sp = 0xFF
        self.assertEqual(sim.run(org), kanma.BIOS_GETFNT)


class EllipsisSpace(unittest.TestCase):
    def test_kanma_ellipsis_followed_by_space(self):
        import typeset

        for key, (_name, text) in kanma.load_ko().items():
            plain = re.sub(r"\{[a-z]*[0-9a-fA-F]+\}", " ", text).replace("/", "\n")
            self.assertEqual(typeset.spaced(plain), plain, key)


if __name__ == "__main__":
    unittest.main()
