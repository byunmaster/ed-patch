"""서 있는 동안 HUD 이름판 숨김(`resthide`) — 본체를 시뮬레이터로 돌려 「언제 숨기고 언제 손을 안 대는가」와 끝 상태(레지스터 0x13 · `$F7`)를 본다."""

import itertools
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cpu65
import resthide as R

SATB = 0x7F00
BAR = (0x0050, 0x00E0, 0x0300, 0x0080)  # 오른쪽 막대 — x 0xE0 · 폭 16: 이름판에 안 걸친다
NPC = (0x0070, 0x0080, 0x0200, 0x0180)


def machine(
    sprites: list[tuple[int, int, int, int]],
    sx: int = 8,
    sy: int = 8,
    first: int = 0,
    cnt: int | None = None,
) -> cpu65.CPU:
    mem = bytearray(0x10000)
    for _nm, bk, off, _old, new in R.patches():
        if bk == R.BANK:
            mem[R.W + off : R.W + off + len(new)] = new
    if cnt is not None:
        mem[R.CNT] = cnt
    mem[R.SCROLL_X], mem[R.SCROLL_X + 1] = sx & 0xFF, sx >> 8
    mem[R.SCROLL_Y], mem[R.SCROLL_Y + 1] = sy & 0xFF, sy >> 8
    mem[R.SAT_FIRST] = first
    mem[R.SAT_LEFT] = 0x40 - len(sprites)
    mem[R.SATB], mem[R.SATB + 1] = SATB & 0xFF, SATB >> 8
    mem[0xF7] = 2
    c = cpu65.CPU(mem)
    c.sp = 0xF0
    c.sel = 2
    for k, sp in enumerate(sprites):
        c.vram[SATB + 4 * k : SATB + 4 * k + 4] = sp
    return c


def field(extra: list[tuple[int, int, int, int]] | None = None) -> list[tuple[int, int, int, int]]:
    """이름판 9칸(첫 칸 = 서명) + 막대 + 게임 스프라이트."""
    panel = [R.SIG_WORDS] + [
        (0x0060 + 16 * k, 0x00F0, 0x0380 + 2 * k, 0x318D) for k in range(1, R.NPANEL)
    ]
    return panel + [BAR] * 6 + [NPC] * (R.NEED - 6) + (extra or [])


def passes(c: cpu65.CPU, n: int):
    for _ in range(n):
        c.sel, c.m[0xF7] = 2, 2  # SAT 함수 꼬리 상태
        c.run(R.MAIN)


def ys(c: cpu65.CPU, n: int) -> list[int]:
    return [c.vram[SATB + 4 * k] for k in range(n)]


class RestHideTest(unittest.TestCase):
    def assert_tail(self, c: cpu65.CPU):
        self.assertEqual((c.sel, c.m[0xF7], c.a, c.i), (0x13, 0x13, 0x13, 0))

    def test_bytes_fit_and_site(self):
        p = {nm: (bk, off, old, new) for nm, bk, off, old, new in R.patches()}
        self.assertEqual(p["site"][3], bytes.fromhex("20d84f08") + R.MAIN.to_bytes(2, "little"))
        self.assertEqual(len(p["site"][3]), len(R.SITE_OLD))
        self.assertEqual(R.table(), bytes.fromhex("318d038000f00060ff"))
        spans = sorted(
            (off, off + len(new)) for nm, (bk, off, _o, new) in p.items() if bk == R.BANK
        )
        for (_a0, a1), (b0, _b1) in itertools.pairwise(spans):
            self.assertLessEqual(a1, b0)

    def test_hides_only_after_eight_rest_passes(self):
        """셈 0xFF 에서 멈춤 8번은 1 이 밀려 나와 그대로 — 9번째부터 숨긴다."""
        sp = field()
        c = machine(sp)
        before = list(c.vram[SATB : SATB + 4 * len(sp)])
        passes(c, 8)
        self.assertEqual(list(c.vram[SATB : SATB + 4 * len(sp)]), before)
        self.assert_tail(c)
        passes(c, 1)
        after = list(c.vram[SATB : SATB + 4 * len(sp)])
        self.assertEqual(ys(c, R.NPANEL), [0] * R.NPANEL)
        want = list(before)
        for k in range(R.NPANEL):
            want[4 * k] = 0
        self.assertEqual(after, want)  # y 단어만, 9번째 칸부터는 그대로
        self.assert_tail(c)

    def test_moving_resets_count_and_never_touches(self):
        for sx, sy in ((0x0E, 8), (8, 0x0A), (0x108, 8), (8, 0x108), (2, 2)):
            sp = field()
            c = machine(sp, sx=sx, sy=sy, cnt=0x00)
            before = list(c.vram)
            passes(c, 1)
            self.assertEqual(c.vram, before, (sx, sy))
            self.assertEqual(c.m[R.CNT], 0xFF)
            self.assert_tail(c)

    def test_held_button_counts_as_moving(self):
        """버튼을 쥔 프레임은 움직임으로 친다 — 메뉴를 여는 프레임에 엔진이 BG 판을 다시 쓴다(숨긴 채면 한 프레임 빈 판이 보인다)."""
        for pad in (0x02, 0x10, 0x01, 0x80):
            c = machine(field(), cnt=0x00)
            c.m[R.PAD] = pad
            before = list(c.vram)
            passes(c, 1)
            self.assertEqual(c.vram, before, pad)
            self.assertEqual(c.m[R.CNT], 0xFF)
            self.assert_tail(c)
            c.m[R.PAD] = 0
            passes(c, 8)
            self.assertEqual(ys(c, 1), [0x60])
            passes(c, 1)
            self.assertEqual(ys(c, R.NPANEL), [0] * R.NPANEL)

    def test_one_rest_frame_between_steps_keeps_panel(self):
        """걷기: 움직임 3프레임 + 멈춤 값 1프레임을 되풀이해도 셈이 8을 못 채운다."""
        sp = field()
        c = machine(sp)
        before = list(c.vram)
        for _ in range(40):
            for v in (0x0E, 0x0C, 0x0A, 0x08):
                c.m[R.SCROLL_Y] = v
                passes(c, 1)
        self.assertEqual(c.vram, before)

    def test_partial_sat_pass_is_not_rest(self):
        c = machine(field(), first=9, cnt=0x00)
        before = list(c.vram)
        passes(c, 1)
        self.assertEqual(c.vram, before)
        self.assertEqual(c.m[R.CNT], 0xFF)

    def test_signature_mismatch_keeps_panel(self):
        for word in range(4):
            sp = field()
            first = list(sp[0])
            first[word] ^= 0x0100
            sp[0] = tuple(first)
            c = machine(sp, cnt=0x00)
            before = list(c.vram)
            passes(c, 3)
            self.assertEqual(c.vram, before, word)
            self.assert_tail(c)

    def test_sprite_over_panel_keeps_panel(self):
        cases = {
            "16폭 x=E1": (0x0070, 0x00E1, 0x0200, 0x0080),
            "32폭 x=D1": (0x0070, 0x00D1, 0x0200, 0x0180),
            "32폭 x=F8(올림 넘침)": (0x0070, 0x00F8, 0x0200, 0x0180),
            "x 상위": (0x0070, 0x0100, 0x0200, 0x0080),
        }
        for nm, spr in cases.items():
            c = machine(field([NPC, spr, NPC]), cnt=0x00)
            before = list(c.vram)
            passes(c, 3)
            self.assertEqual(c.vram, before, nm)
            self.assert_tail(c)
        for nm, spr in {
            "16폭 x=E0": (0x0070, 0x00E0, 0x0200, 0x0080),
            "32폭 x=D0": (0x0070, 0x00D0, 0x0200, 0x0180),
        }.items():
            c = machine(field([spr]), cnt=0x00)
            passes(c, 1)
            self.assertEqual(ys(c, R.NPANEL), [0] * R.NPANEL, nm)

    def test_too_few_sprites_to_overflow_keeps_panel(self):
        """이름판 밖 칸이 NEED 보다 적으면(전투·한산한 장면 — 한 줄 16칸을 넘길 수 없다) 손을 안 댄다."""
        for n in (5, R.NPANEL, R.NPANEL + 6, R.NPANEL + R.NEED - 1):
            c = machine(field()[:n], cnt=0x00)
            before = list(c.vram)
            passes(c, 3)
            self.assertEqual(c.vram, before, n)
            self.assert_tail(c)
        c = machine(field()[: R.NPANEL + R.NEED], cnt=0x00)
        passes(c, 1)
        self.assertEqual(ys(c, R.NPANEL), [0] * R.NPANEL)
        self.assert_tail(c)

    def test_hide_survives_moved_write_address(self):
        """단어마다 주소를 다시 세운다 — 중간에 MAWR 이 딴 데로 가도(자막 틱) 다음 단어는 제자리에 쓴다."""
        c = machine(field(), cnt=0x00)
        c.sel, c.m[0xF7] = 2, 2
        c.push((0xFFFF - 1) >> 8)
        c.push((0xFFFF - 1) & 0xFF)
        c.pc = R.MAIN
        moved = 0
        while c.pc != 0xFFFF:
            if c.pc == R.SETA and c.a == 0:  # 숨김 쓰기 직전마다 주소를 흩뜨린다
                c.mawr = 0x1234
                moved += 1
            c.step()
        self.assertEqual(moved, R.NPANEL)
        self.assertEqual(ys(c, R.NPANEL), [0] * R.NPANEL)
        self.assertEqual(c.vram[0x1234], 0)


if __name__ == "__main__":
    unittest.main()
