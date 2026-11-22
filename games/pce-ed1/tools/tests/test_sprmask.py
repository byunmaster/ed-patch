"""잘린 그림 사본(`sprmask.py`) — 계획자·할당기·셀 굽기·서명 검사를 시뮬레이터로 돌려 파이썬 참조(`ref_*`)와 PRES·풀 비트맵·VRAM 워드로 대조한다.
서술자는 합성이다(원본 없이 돈다) — 실제 서술자 열의 전제는 빌드가 `sprmask.check_descriptors` 로 건다."""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cpu65
import hook
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
        _sig(c)  # 첫 프레임 — 서명이 비어 있었다(창이 처음 뜬다, 11-22): 기다리지 않고 바로 계획 시작
        self.assertEqual((c.m[sprmask.PEND], c.m[sprmask.PCUR], c.m[sprmask.PY]), (0, desc[0], 1))
        _sig(c)  # 둘째 프레임 — 같은 서명: 그대로
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
        # 8셀짜리(32×64) 조각 넷 = 32셀 → 예산 32셀이면 한 프레임(결과는 참조와 같다) — 예산을 바꾸면 이 시험의 프레임 수가 따라 바뀐다
        desc = bytes([4]) + b"".join(bytes([dx, 0, 80, 0, 0x31]) for dx in (0, 32, 64, 96))
        got, frames, worst = self._case(desc, 40, 150, False, "bottom")
        self.assertEqual(frames, -(-32 // sprmask.BUDGET))
        self.assertTrue(all(v >= 0x80 for v in got[1:5]), got[:6])
        self.assertLess(worst, 1500 * sprmask.BUDGET)  # 한 프레임 비용(명령 수) — 셀 굽기 ≈ 1,400 명령/셀

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
            if poke >= 0x8000:  # 창만 바뀜(11-22) — 한 프레임 기다리지 않고 바로 계획 시작(PEND 0 · PY 1)
                self.assertEqual((c.m[sprmask.PEND], c.m[sprmask.PY]), (0, 1))
            else:
                self.assertEqual((c.m[sprmask.PEND], c.m[sprmask.PCUR]), (1, 0))
            c.m[sprmask.PRES + 1] = 0x99
            c.m[sprmask.G] = 1
            c.m[sprmask.PEND] = 0  # (다음 바꿈도 「바뀜」 길로 가는지 따로 보려고 지운다)

    def test_window_only_change_starts_plan_at_once(self):
        # 11-22 마스터 02 — 좌표·서술자는 그대로인데 창만 바뀌면(음성 자막 창이 뜰 때) 한 프레임 기다리지 않고 바로 계획을 시작한다
        desc = bytes([1, 0, 0, 80, 0, 0x11])
        c, _ = _machine(desc, 40, 170, False, None, 3)
        _sig(c), _sig(c)  # 서명 안정(창 없음)
        c.m[sprmask.FLAG] = 0
        c.m[winmask.slot_addr(winmask.SLOT_DLG)] = 1  # 아래 대사 창이 켜진다
        for j, v in enumerate(winmask.DLG_BOTTOM):
            c.m[winmask.slot_addr(winmask.SLOT_DLG, 1 + j)] = v
        _sig(c)
        self.assertEqual((c.m[sprmask.PEND], c.m[sprmask.PCUR], c.m[sprmask.PY]), (0, 1, 1))
        # 좌표가 같이 바뀌면(걷는 중) 옛대로 기다린다
        c.m[0x2E] ^= 1
        c.m[winmask.slot_addr(winmask.SLOT_MENU)] = 1
        _sig(c)
        self.assertEqual((c.m[sprmask.PEND], c.m[sprmask.PCUR]), (1, 0))

    def test_moving_never_starts_plan(self):
        # 걷는 동안(프레임마다 좌표가 바뀐다)은 계획이 시작되지 않는다 — PCUR 가 0 인 채
        desc = bytes([1, 0, 0, 80, 0, 0x11])
        c, _ = _machine(desc, 40, 170, False, "bottom", 4)
        _sig(c)  # 첫 서명(창이 막 떴다 — 바로 시작)
        c.m[sprmask.PCUR] = 0
        for f in range(1, 11):
            c.m[0x2E] = 40 + f
            _sig(c)
            self.assertEqual((c.m[sprmask.PCUR], c.m[sprmask.PEND]), (0, 1))

    # ── 엔진 가림 루틴 후크 ──
    def test_eg_bits_drops_band_rows(self):
        # 화면 위 띠(SAT y < 96) 셀의 비트만 뺀다 — 윗줄 셀 = 비트 0·1, 아랫줄 = 비트 2·3
        c, _ = _machine(bytes([1, 0, 0, 80, 0, 0]), 40, 170, True, None, 1)
        for y in range(40, 256):
            for bits in range(16):
                c.m[sprmask.ENG_Y], c.m[0x0E], c.x = y, bits, 2
                c.run(L["eg_bits"])
                want = bits if y >= 96 else bits & 0x0C if y >= 88 else 0
                self.assertEqual((c.m[sprmask.ENG_BITS + 2], c.x), (want, 2), (y, bits))

    def _gate(self, c, obj=7, kind=0x7D, cnt=3):
        c.m[sprmask.ENG_KIND + obj] = kind
        c.m[sprmask.ENG_CNT] = cnt
        c.x, c.y, c.mpr[4] = obj, 9, 0x12
        c.run(L["eg_gate"])
        self.assertEqual((c.x, c.y, c.mpr[4]), (obj, 9, 0x12))
        return c.z  # 1 = 엔진이 가림 장을 안 깐다

    def _gate_machine(self, menu=True, dlg=None, pres=0xC4):
        """서명이 맞고(두 프레임) 계획이 끝난 상태 — PRES[3] 만 `pres` 로 갈아 놓는다."""
        c, _ = _machine(bytes([1, 0, 0, 80, 0, 0]), 40, 170, menu, dlg, 1)
        c.m[sprmask.ENG_MENU_FLAG] = 1
        _sig(c)
        _sig(c)
        c.m[sprmask.PCUR] = 0
        c.m[sprmask.FLAG] = 0  # 새 프레임
        c.m[sprmask.PRES + 3] = pres
        return c

    def test_eg_gate(self):
        site = sprmask.CODE_WINDOW + sprmask.ENG_GATE_OFF
        armed = b"\x20" + L["eg_gate"].to_bytes(2, "little")
        # 메뉴 열만 떠 있고 그 조각이 사본으로 나간다 → 가림 장 없음. 그 밖의 PRES 값은 원판대로
        for pres, want in ((0xC4, 1), (0x80, 1), (0, 0), (1, 0), (2, 0)):
            c = self._gate_machine(pres=pres)
            self.assertEqual(bytes(c.m[site : site + 3]), armed)  # sigchk 가 걸어 놨다
            self.assertEqual(self._gate(c), want, pres)
            self.assertEqual(c.m[sprmask.FLAG], 8)  # 서명을 여기서 봤다 — 스텁은 건너뛴다
            self.assertEqual(bytes(c.m[site : site + 3]), armed)
        # 메뉴가 안 열렸다(`$37B9` = 0) → 원판대로 Z
        c = self._gate_machine()
        c.m[sprmask.ENG_MENU_FLAG] = 0
        self.assertEqual(self._gate(c), 1)
        # 어둠 원이 아닌 개체 → 원판대로
        for kind in (0x77, 0x82, 0x00):
            self.assertEqual(self._gate(self._gate_machine(), kind=kind), 0)
        for kind in range(0x78, 0x82):
            self.assertEqual(self._gate(self._gate_machine(), kind=kind), 1)
        # 목록·대사·기타 창이 같이 떠 있다 → 원판대로(자리는 그대로)
        for k in (winmask.SLOT_LIST, winmask.SLOT_DLG, winmask.SLOT_ETC):
            c = self._gate_machine()
            c.m[winmask.slot_addr(k)] = 1
            self.assertEqual(self._gate(c), 0, k)
            self.assertEqual(bytes(c.m[site : site + 3]), armed)
        # 메뉴 열이 걷혔다(부 메뉴 — PRES 는 묵은 채) → 원판대로 + 자리를 원판 명령으로 되돌린다
        c = self._gate_machine()
        c.m[winmask.slot_addr(winmask.SLOT_MENU)] = 0
        self.assertEqual(self._gate(c), 0)
        self.assertEqual(bytes(c.m[site : site + 3]), sprmask.ENG_GATE_OLD)

    def test_eg_gate_never_trusts_stale_pres(self):
        # 서명이 바뀐 프레임(원 크기가 바뀜 등)의 첫 조각 — 스텁보다 먼저 불려도 묵은 PRES 를 안 쓴다
        c = self._gate_machine()
        c.m[0xFB] ^= 1
        self.assertEqual(self._gate(c), 0)
        self.assertEqual(c.m[sprmask.PRES + 3], 0)
        # 이 개체를 이번 프레임에 이미 봤는데 프레임 후크가 서명을 못 쓰게 해 둔 경우(창이 다 꺼졌던 프레임)
        c = self._gate_machine()
        c.m[sprmask.FLAG] = 8
        c.m[sprmask.SIG + 5] = 0
        self.assertEqual(self._gate(c), 0)

    def test_sigchk_arms_gate_only_for_menu_alone(self):
        site = sprmask.CODE_WINDOW + sprmask.ENG_GATE_OFF
        for menu, dlg, want in ((True, None, True), (True, "bottom", False), (False, "bottom", False), (False, "top", False)):
            c, _ = _machine(bytes([1, 0, 0, 80, 0, 0]), 40, 170, menu, dlg, 1)
            c.m[site : site + 3] = sprmask.ENG_GATE_OLD
            _sig(c)
            self.assertEqual(bytes(c.m[site : site + 3]) != sprmask.ENG_GATE_OLD, want, (menu, dlg))

    def test_engine_patches(self):
        (_n1, b1, o1, was1, now1), (_n2, b2, o2, was2, now2) = sprmask.engine_patches()
        self.assertEqual((b1, o1, was1, now1), (0x70, 0x120, bytes.fromhex("a50e9d2e61"), b"\x20" + L["eg_bits"].to_bytes(2, "little") + b"\xea\xea"))
        self.assertEqual((b2, o2, was2, now2), (0x70, 0x28, bytes.fromhex("adb937"), bytes.fromhex("adb937")))  # 이미지는 원판 그대로

    def test_layout(self):
        segs = sprmask.segments()
        for (off, code), (_, s0, s1) in zip(segs, sprmask.SEGS, strict=True):
            self.assertEqual(off, s0)
            self.assertLessEqual(off + len(code), s1)
        spans = sorted((s0, s1) for _, s0, s1 in sprmask.SEGS)
        self.assertTrue(all(a1 <= b0 for (_, a1), (b0, _) in zip(spans, spans[1:], strict=False)), spans)  # 토막끼리 안 겹친다
        self.assertEqual(len(sprmask.data_init()), sprmask.DATA_LEN)
        self.assertEqual(sprmask.D + sprmask.DATA_LEN, 0x8000 + hook.WCK_VEC_OFF)  # 뱅크 끝 10B = 인터럽트 벡터 사본(6B) + 빈 4B
        self.assertEqual(sprmask.DLG_BOTTOM_Y0, winmask.DLG_BOTTOM[0])


if __name__ == "__main__":
    unittest.main()
