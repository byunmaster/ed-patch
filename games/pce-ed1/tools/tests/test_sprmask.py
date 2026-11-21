"""잘린 그림 사본(`sprmask.py`) — 계획자·할당기·셀 굽기·서명 검사를 시뮬레이터로 돌려 파이썬 참조(`ref_*`)와 PRES·풀 비트맵·VRAM 워드로 대조한다.
서술자는 합성이다(원본 없이 돈다) — 실제 서술자 열의 전제는 빌드가 `sprmask.check_descriptors` 로 건다."""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cpu65
import sprmask
import winmask

DESC = 0x4000  # 합성 서술자를 두는 자리
L = sprmask.labels()


def _machine(desc: bytes, bx: int, by: int, menu: bool, dlg: str | None, seed: int):
    m = bytearray(0x10000)
    for off, code in sprmask.segments():
        m[sprmask.CODE_WINDOW + off : sprmask.CODE_WINDOW + off + len(code)] = code
    m[sprmask.D : sprmask.D + sprmask.DATA_LEN] = sprmask.data_init()
    m[DESC : DESC + len(desc)] = desc
    wins = []
    if menu:
        m[winmask.slot_addr(winmask.SLOT_MENU)] = 2
        wins.append(sprmask.WIN_MENU)
    if dlg:
        rect = winmask.DLG_BOTTOM if dlg == "bottom" else winmask.DLG_TOP
        m[winmask.slot_addr(winmask.SLOT_DLG)] = 1
        for j, v in enumerate(rect):
            m[winmask.slot_addr(winmask.SLOT_DLG, 1 + j)] = v
        wins.append(sprmask.WIN_BOTTOM if dlg == "bottom" else sprmask.WIN_TOP)
    m[0x2E], m[0x2F] = bx & 0xFF, bx >> 8 & 0xFF
    m[0x30], m[0x31] = by & 0xFF, by >> 8 & 0xFF
    m[0xFA], m[0xFB] = DESC & 0xFF, DESC >> 8
    c = cpu65.CPU(m)
    rnd = random.Random(seed)
    for k in range(sprmask.POOL_CELL * 64):
        c.vram[k] = rnd.getrandbits(16)
    return c, wins


def _sig(c):
    c.x, c.y = 7, 9
    n = c.run(L["sigchk"])
    assert (c.x, c.y) == (7, 9), "sigchk 는 X·Y 를 지킨다"
    return n


def _plan_all(c, frames=64):
    """프레임마다 `plan` 을 한 번씩 — 다 끝날 때까지(PCUR=0). 프레임 수와 프레임당 최대 명령 수."""
    worst = 0
    for f in range(frames):
        if not c.m[sprmask.PCUR]:
            return f, worst
        worst = max(worst, c.run(L["plan"]))
    raise AssertionError("계획이 안 끝난다")


def _rand_desc(rnd, n):
    out = bytearray([n])
    for _ in range(n):
        ah = rnd.choice((0, 1)) | rnd.choice((0, 1, 2, 3)) << 4 | rnd.choice((0, 8)) | rnd.choice((0, 0x80))
        cell = rnd.randrange(32, 0x78)
        out += bytes([rnd.randrange(256), rnd.randrange(256), cell * 2, 0, ah])
    return bytes(out)


class SprMask(unittest.TestCase):
    def _case(self, desc, bx, by, menu, dlg, seed=1):
        c, wins = _machine(desc, bx, by, menu, dlg, seed)
        ref_v = list(c.vram)
        want = sprmask.ref_plan(desc, bx, by, wins, ref_v)
        _sig(c)  # 첫 프레임 — 서명이 바뀌었다: 비우고 PEND
        self.assertEqual((c.m[sprmask.PEND], c.m[sprmask.PCUR]), (1, 0))
        _sig(c)  # 둘째 프레임 — 같은 서명: 계획 시작
        self.assertEqual((c.m[sprmask.PEND], c.m[sprmask.PCUR], c.m[sprmask.PY]), (0, desc[0], 1))
        frames, worst = _plan_all(c)
        got = list(c.m[sprmask.PRES : sprmask.PRES + 32])
        self.assertEqual(got, want, (bx, by, menu, dlg))
        self.assertEqual(c.vram, ref_v, (bx, by, menu, dlg))
        self.assertEqual(c.m[0xF7], 2)  # VDC 선택 그림자 — 프레임 후크가 0 으로 돌린다
        return got, frames, worst

    def test_random_descriptors_match_reference(self):
        rnd = random.Random(20261121)
        kinds = [0, 0, 0]
        for t in range(400):
            desc = _rand_desc(rnd, rnd.randrange(1, 32))
            bx, by = rnd.randrange(0, 300), rnd.randrange(20, 300)
            menu, dlg = rnd.random() < 0.5, rnd.choice((None, "bottom", "top"))
            if not menu and not dlg:
                dlg = "bottom"
            got, _, _ = self._case(desc, bx, by, menu, dlg, seed=t)
            for v in got:
                kinds[0] += v == 1
                kinds[1] += v == 2
                kinds[2] += v >= 0x80
        self.assertTrue(all(k > 50 for k in kinds), kinds)  # 세 부류가 다 충분히 나왔나(분모 확인)

    def test_single_piece_shapes_and_flips(self):
        # 조각 하나가 아래 창 왼쪽 위 모서리(48, 176)에 걸친다 — 모양 여덟 × 뒤집기 넷 × 걸치는 정도
        for s in range(8):
            ah0 = (s & 1) | (s >> 1) << 4
            w, h = sprmask.WTAB[s], sprmask.HTAB[s]
            for flip in (0, 8, 0x80, 0x88):
                for ox in (1, w // 2, w - 1):
                    for oy in (1, h // 2, h - 1):
                        desc = bytes([1, 0, 0, 40 * 2, 0, ah0 | flip])
                        got, _, _ = self._case(desc, 48 - ox, 176 - oy, False, "bottom")
                        self.assertGreaterEqual(got[1], 0x80, (s, flip, ox, oy))

    def test_fully_inside_and_outside(self):
        desc = bytes([2, 0, 0, 80, 0, 0x11, 100, 0, 80, 0, 0x11])  # 32×32 둘 — 하나는 창 안, 하나는 오른쪽 밖(x 가 255 를 넘는다)
        got, _, _ = self._case(desc, 160, 190, False, "bottom")
        self.assertEqual((got[2], got[1]), (2, 1))

    def test_menu_and_dialogue_two_rects(self):
        # 메뉴(x 48~112 · y 96~224)와 아래 대사 창(x 48~224 · y 176~256)에 함께 걸친 32×64 조각 — 사각형 둘
        desc = bytes([1, 0, 0, 80, 0, 0x31])
        got, _, _ = self._case(desc, 100, 150, True, "bottom")
        self.assertGreaterEqual(got[1], 0x80)

    def test_budget_spreads_over_frames_same_result(self):
        # 8셀짜리(32×64) 조각 넷 = 32셀 → 프레임당 8셀이라 넷으로 갈린다, 결과는 참조(예산 없음)와 같다
        desc = bytes([4]) + b"".join(bytes([dx, 0, 80, 0, 0x31]) for dx in (0, 32, 64, 96))
        got, frames, worst = self._case(desc, 40, 150, False, "bottom")
        self.assertEqual(frames, 4)
        self.assertTrue(all(v >= 0x80 for v in got[1:5]), got[:6])
        self.assertLess(worst, 12000)  # 한 프레임 비용(명령 수) — 8셀 굽기 ≈ 1,400 명령/셀

    def test_pool_exhausted_falls_back(self):
        # 8셀 조각 다섯 — 풀(32칸)은 넷까지: 다섯째는 0(옛 판정으로 폴백)
        desc = bytes([5]) + b"".join(bytes([dx, 0, 80, 0, 0x31]) for dx in (0, 24, 48, 72, 96))
        got, _, _ = self._case(desc, 40, 150, False, "bottom")
        self.assertEqual(got[1], 0)
        self.assertEqual(got[2:6], [0xC0 + 2 * i for i in (24, 16, 8, 0)])

    def test_signature_change_flushes(self):
        desc = bytes([1, 0, 0, 80, 0, 0x11])
        c, _ = _machine(desc, 40, 170, False, "bottom", 3)
        _sig(c), _sig(c)
        _plan_all(c)
        self.assertGreaterEqual(c.m[sprmask.PRES + 1], 0x80)
        self.assertNotEqual(bytes(c.m[sprmask.G : sprmask.G + 4]), bytes(4))
        c.m[sprmask.FLAG] = 0
        n = _sig(c)  # 같은 서명 — 아무것도 안 바뀐다
        self.assertLess(n, 60)
        self.assertEqual((c.m[sprmask.FLAG], c.m[sprmask.PCUR], c.m[sprmask.PEND]), (7 + 1, 0, 0))  # FLAG = 개체 번호(X) + 1
        self.assertGreaterEqual(c.m[sprmask.PRES + 1], 0x80)
        for poke in (0x2E, 0x2F, 0x30, 0x31, 0xFA, 0xFB, winmask.slot_addr(winmask.SLOT_MENU), winmask.slot_addr(winmask.SLOT_DLG, 1)):
            c.m[poke] ^= 1
            _sig(c)
            self.assertEqual(bytes(c.m[sprmask.PRES : sprmask.PRES + 32]), bytes(32), hex(poke))
            self.assertEqual(bytes(c.m[sprmask.G : sprmask.G + 4]), bytes(4))
            self.assertEqual((c.m[sprmask.PEND], c.m[sprmask.PCUR]), (1, 0))
            c.m[sprmask.PRES + 1] = 0x99
            c.m[sprmask.G] = 1
            c.m[sprmask.PEND] = 0  # (다음 바꿈도 「바뀜」 길로 가는지 따로 보려고 지운다)

    def test_moving_never_starts_plan(self):
        # 걷는 동안(프레임마다 좌표가 바뀐다)은 계획이 시작되지 않는다 — PCUR 가 0 인 채
        desc = bytes([1, 0, 0, 80, 0, 0x11])
        c, _ = _machine(desc, 40, 170, False, "bottom", 4)
        for f in range(10):
            c.m[0x2E] = 40 + f
            _sig(c)
            self.assertEqual((c.m[sprmask.PCUR], c.m[sprmask.PEND]), (0, 1))

    def test_layout(self):
        segs = sprmask.segments()
        for (off, code), (_, s0, s1) in zip(segs, sprmask.SEGS, strict=True):
            self.assertEqual(off, s0)
            self.assertLessEqual(off + len(code), s1)
        self.assertEqual(len(sprmask.data_init()), sprmask.DATA_LEN)
        self.assertEqual(sprmask.D + sprmask.DATA_LEN, 0xA000)
        self.assertEqual(sprmask.DLG_BOTTOM_Y0, winmask.DLG_BOTTOM[0])


if __name__ == "__main__":
    unittest.main()
