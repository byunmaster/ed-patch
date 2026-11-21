"""창 사각형 표 + SAT 스텁(`winmask.py`) — 시뮬레이터로 돌려 참조 구현(겹침 판정)과 대조하고 계약(자리·등록 루틴)을 건다."""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cpu65
import sprmask
import winmask

ZP = 0  # cpu65 의 zp 모드는 평평한 주소(0~FF)


def _load(m):
    sc, rc = winmask.stub_code(), winmask.reg_code()
    m[winmask.STUB_ORG : winmask.STUB_ORG + len(sc)] = sc
    m[winmask.REG_ORG : winmask.REG_ORG + len(rc)] = rc
    for off, code in sprmask.segments():  # 잘린 그림 사본(뱅크 0x70, `$6000` 창) — 스텁·프레임 후크가 부른다
        m[sprmask.CODE_WINDOW + off : sprmask.CODE_WINDOW + off + len(code)] = code


PAT = 0x0155  # 시험 서술자의 패턴 워드(스텁이 그대로 옮겨 써야 한다)
SAT0 = 0x7F00  # 시뮬레이터 VRAM 에서 스텁의 두 워드(패턴 · 속성)가 떨어지는 자리


def call_stub(c, y_index):
    """SAT 루프의 사이트(`$6567`)를 흉내 — X = 3 · Y = 서술자의 패턴 낮은 바이트 색인. (패턴 워드, 속성 워드, 명령 수)."""
    c.sel, c.mawr = 2, SAT0
    c.m[ZP + 0xF9] = 0  # 원판 `$6551 STZ $F9`
    c.x, c.y = 3, y_index
    n = c.run(winmask.labels()["stub"])
    assert (c.x, c.y) == (3, y_index + 3), "X 를 지키고 Y 는 조각 끝(+3)이어야 한다"
    assert c.mawr == SAT0 + 2, "워드 둘(패턴 · 속성)만 쓴다"
    return c.vram[SAT0], c.vram[SAT0 + 1], n


def run_stub(slots, x, y, w32, hcode, base_attr=0x80, f9=0x80, mode=1, kind=0):
    """슬롯 표를 깔고 스텁을 한 번 돌려 SAT 에 쓰인 속성 낮은 바이트를 돌려준다(패턴·속성 높은 바이트는 서술자 그대로인지 여기서 본다)."""
    m = bytearray(0x10000)
    _load(m)
    for k, rect in slots.items():
        m[winmask.slot_addr(k)] = mode
        for j, v in enumerate(rect):
            m[winmask.slot_addr(k, 1 + j)] = v
    m[0x36E9 + 3] = base_attr & 0x7F  # X = 3 인 스프라이트의 속성 낮은 바이트(우선순위 제외)
    m[0x3559 + 3] = f9 | 0x25  # 우선순위는 개체 플래그 비트 7 — 스텁이 `$F9` 로 옮긴다(나머지 비트는 무관해야 한다)
    m[0x3509 + 3] = kind
    m[ZP + 0xFC], m[ZP + 0xFD] = x & 0xFF, x >> 8
    m[ZP + 0xFE], m[ZP + 0xFF] = y & 0xFF, y >> 8
    m[ZP + 0xFA], m[ZP + 0xFB] = 0x00, 0x30
    ah = (1 if w32 else 0) | (hcode << 4)
    m[0x3000 + 3], m[0x3000 + 4], m[0x3000 + 5] = PAT & 0xFF, PAT >> 8, ah
    c = cpu65.CPU(m)
    pat, attr, n = call_stub(c, 3)
    assert pat == PAT, hex(pat)
    assert attr >> 8 == ah, hex(attr)
    return attr & 0xFF, n


def ref_hit(slots, x, y, w32, hcode):
    w = 32 if w32 else 16
    h = {0: 16, 1: 32, 2: 32, 3: 64}[hcode]
    x4, y4, w4, h4 = x >> 2, y >> 2, w // 4, h // 4
    for rect in slots.values():
        y0, y1, x0, x1 = rect
        if y4 < y1 and y4 + h4 > y0 and x4 < x1 and x4 + w4 > x0:
            return True
    return False


class WinMask(unittest.TestCase):
    def test_no_active_slot_keeps_priority(self):
        out, n = run_stub({}, 100, 200, True, 1)
        self.assertEqual(out, 0x80 | 0x00 | 0)  # 원래 값(`$F9` = 우선순위 비트) 그대로
        self.assertLess(n, 240)

    def test_overlap_clears_only_priority_bit(self):
        slots = {winmask.SLOT_DLG: winmask.DLG_BOTTOM}
        out, _ = run_stub(slots, 96, 190, True, 1, base_attr=0x01)
        self.assertEqual(out, 0x01)  # 우선순위 비트(7)만 꺼짐
        out, _ = run_stub(slots, 96, 100, False, 0, base_attr=0x01)  # 창 위 멀리 — 그대로
        self.assertEqual(out, 0x81)

    def test_random_against_reference(self):
        rnd = random.Random(1119)
        for _ in range(3000):
            slots = {}
            for k in range(winmask.NSLOT):
                if rnd.random() < 0.5:
                    y0 = rnd.randrange(0, 80)
                    x0 = rnd.randrange(0, 70)
                    slots[k] = (y0, y0 + rnd.randrange(1, 40), x0, x0 + rnd.randrange(1, 60))
            x, y = rnd.randrange(0, 330), rnd.randrange(0, 360)
            w32, hc = bool(rnd.getrandbits(1)), rnd.choice([0, 1, 3])
            out, _ = run_stub(slots, x, y, w32, hc, base_attr=0x05)
            self.assertEqual(bool(out & 0x80) is False, ref_hit(slots, x, y, w32, hc), (slots, x, y, w32, hc, out))

    def test_inside_mode_against_reference(self):
        """활성 2 = 완전히 안쪽 — 스프라이트 전체가 사각형 안일 때만 우선순위를 끈다(걸친 큰 스프라이트는 그대로)."""
        rnd = random.Random(1120)
        for _ in range(3000):
            y0, x0 = rnd.randrange(0, 60), rnd.randrange(0, 60)
            rect = (y0, y0 + rnd.randrange(1, 50), x0, x0 + rnd.randrange(1, 60))
            x, y = rnd.randrange(0, 330), rnd.randrange(0, 360)
            w32, hc = bool(rnd.getrandbits(1)), rnd.choice([0, 1, 3])
            out, _ = run_stub({0: rect}, x, y, w32, hc, base_attr=0x05, mode=2)
            w, h = (32 if w32 else 16), {0: 16, 1: 32, 3: 64}[hc]
            x4, y4 = x >> 2, y >> 2
            inside = rect[0] <= y4 and y4 + h // 4 <= rect[1] and rect[2] <= x4 and x4 + w // 4 <= rect[3]
            self.assertEqual(bool(out & 0x80) is False, inside, (rect, x, y, w32, hc, out))

    def test_register_routines(self):
        lab = winmask.labels()
        for name, rect in (("dlg_bottom", winmask.DLG_BOTTOM), ("dlg_top", winmask.DLG_TOP)):
            m = bytearray(0x10000)
            _load(m)
            c = cpu65.CPU(m)
            c.run(lab[name])
            self.assertEqual(m[winmask.slot_addr(winmask.SLOT_DLG)], 1)
            self.assertEqual(tuple(m[winmask.slot_addr(winmask.SLOT_DLG, 1 + j)] for j in range(4)), rect)
            c.run(lab["dlg_close"])
            self.assertEqual(m[winmask.slot_addr(winmask.SLOT_DLG)], 0)

    def test_menu_routines(self):
        """메뉴 열기/닫기 — 슬롯 0 + 원판과 같은 우선순위 비트(`$379B`·`$379C` 개체 `$3559,X` 비트 7) 동작."""
        lab = winmask.labels()
        m = bytearray(0x10000)
        _load(m)
        m[0x379B], m[0x379C] = 3, 7
        m[0x3559 + 3] = m[0x3559 + 7] = 0xA5
        c = cpu65.CPU(m)
        c.run(lab["menu_open"])
        self.assertEqual(m[winmask.slot_addr(winmask.SLOT_MENU)], 0)  # `$623E` 는 우선순위만 — 사각형은 `menu_top` 이 켠다(「버린다」 처리기가 열이 걷힌 뒤에도 부른다)
        self.assertEqual((m[0x3559 + 3], m[0x3559 + 7]), (0x25, 0x25))  # 비트 7 꺼짐
        c.run(lab["menu_show"])
        self.assertEqual(m[winmask.slot_addr(winmask.SLOT_MENU)], 2)
        self.assertEqual(tuple(m[winmask.slot_addr(winmask.SLOT_MENU, 1 + j)] for j in range(4)), winmask.MENU_RECT)
        c.run(lab["menu_close"])
        self.assertEqual(m[winmask.slot_addr(winmask.SLOT_MENU)], 0)
        self.assertEqual((m[0x3559 + 3], m[0x3559 + 7]), (0xA5, 0xA5))  # 켜짐

    def test_engine_patches(self):
        for _, bank, off, old, new in winmask.engine_patches():
            self.assertEqual(len(old), len(new))
            self.assertEqual(new[:3], b"\x20\xd8\x4f")

    def test_site_and_layout(self):
        self.assertEqual(len(winmask.site_new()), len(winmask.SITE_OLD))
        self.assertEqual(winmask.SITE_OLD, bytes.fromhex("b1fa8d0200c8b1fa"))  # LDA ($FA),Y · STA $0002 · INY · LDA ($FA),Y
        self.assertEqual(winmask.site_new()[:3], b"\x20\xd8\x4f")  # 먼 호출
        self.assertEqual(winmask.site_new()[3], winmask.STUB_BANK - 0x68 - 1)
        self.assertEqual(winmask.site_new()[6:], b"\x80\x18")  # BRA → 조각 루프 끝
        self.assertEqual(winmask.SITE_OFF + 8 + 0x18, 0x0587)  # `$6587 DEC $33`
        self.assertEqual(winmask.TOTAL_LEN, 537)  # 뒤에 붙는 이웃(음악 복원 · 어절 판정)이 안 밀린다
        self.assertEqual(winmask.TBL + winmask.TOTAL_LEN + 320 + 307, sprmask.D)  # 그 둘 뒤가 사본 장치 데이터
        self.assertLessEqual(len(winmask.stub_code()), winmask.STUB_LEN)
        self.assertLessEqual(len(winmask.reg_code()), winmask.REG_LEN)
        self.assertTrue(0x8000 <= winmask.TBL and winmask.STUB_ORG + winmask.STUB_LEN <= 0xA000)  # 뱅크 0x73 꼬리, $8000 창

    def test_dlg_rects_match_old_stub_thresholds(self):
        # 옛 어둠 스텁: 아래 창 y+높이 ≥ 178(SAT) · 위 창 100 ≤ y+높이, y < 183 — 4px 단위 사각형이 그 근처(±3px)여야 한다
        y0, y1, _, _ = winmask.DLG_BOTTOM
        self.assertTrue(abs(y0 * 4 - 177) <= 4)
        y0, y1, _, _ = winmask.DLG_TOP
        self.assertTrue(abs(y0 * 4 - 100) <= 4 and abs(y1 * 4 - 183) <= 4)

    def test_cursor_kinds_never_masked(self):
        # 마스터 11-20 「커서 반토막」 — 커서(종류 0x63~0x67)는 창 안에 통째로 들어 있어도 가리지 않는다. X=3 슬롯의 종류가 `$3509+3`
        slots = {winmask.SLOT_MENU: winmask.MENU_RECT}
        for kind, masked in ((0x62, True), (0x63, False), (0x64, False), (0x67, False), (0x68, True), (0x00, True)):
            m = bytearray(0x10000)
            _load(m)
            m[winmask.slot_addr(winmask.SLOT_MENU)] = 2
            for j, v in enumerate(winmask.MENU_RECT):
                m[winmask.slot_addr(winmask.SLOT_MENU, 1 + j)] = v
            m[0x3509 + 3] = kind
            m[0x36E9 + 3] = 0x01
            m[0x3559 + 3] = 0x80
            x, y = 76, 190  # 메뉴 사각형 안(16×16 통째)
            m[0xFC], m[0xFD], m[0xFE], m[0xFF] = x & 0xFF, x >> 8, y & 0xFF, y >> 8
            m[0xFA], m[0xFB] = 0x00, 0x30
            m[0x3000 + 5] = 0
            c = cpu65.CPU(m)
            _, attr, _ = call_stub(c, 3)
            self.assertEqual(attr & 0xFF, 0x01 if masked else 0x81, hex(kind))

    def test_dialog_rect_limits_horizontal_overlap(self):
        # 마스터 11-20 「횃불 원 좌우 옆이 평평해져」 — 대사 슬롯은 세로만이 아니라 가로도 겹친 조각만 가린다(창 틀 x 41~222 밖은 그대로)
        slots = {winmask.SLOT_DLG: winmask.DLG_BOTTOM}
        out, _ = run_stub(slots, 120, 190, False, 1, base_attr=0x01)  # 창 가운데 — 가림
        self.assertEqual(out, 0x01)
        out, _ = run_stub(slots, 232, 190, False, 1, base_attr=0x01)  # 창 오른쪽 밖(16폭: 232~248 > 224)
        self.assertEqual(out, 0x81)
        out, _ = run_stub(slots, 10, 190, False, 1, base_attr=0x01)  # 창 왼쪽 밖(10~26 < 40)
        self.assertEqual(out, 0x81)
        out, _ = run_stub(slots, 215, 190, False, 1, base_attr=0x01)  # 오른쪽 틀에 걸침 — 가림(걸치면 모드)
        self.assertEqual(out, 0x01)
        # 화면 테두리 장식 스프라이트(폭 16, 세로 64): 왼쪽 SAT x 32~48 · 오른쪽 224~240 — 창과 세로로 겹쳐도 가리지 않는다(맵이 비친다)
        out, _ = run_stub(slots, 32, 192, False, 3, base_attr=0x01)
        self.assertEqual(out, 0x81)
        out, _ = run_stub(slots, 224, 192, False, 3, base_attr=0x01)
        self.assertEqual(out, 0x81)

    def _run_frame_hook(self, active_slots, mpr5=0x69):
        m = bytearray(0x10000)
        _load(m)
        for k in active_slots:
            m[winmask.slot_addr(k)] = 1
        m[sprmask.FLAG], m[sprmask.SIG + 5] = 4, 0xA9
        m[winmask.SITE_WINDOW : winmask.SITE_WINDOW + 8] = b"\xaa" * 8
        c = cpu65.CPU(m)
        c.a, c.x, c.y = 7, 3, 5
        c.mpr[5] = mpr5
        n = c.run(winmask.labels()["frame_hook"])
        return bytes(m[winmask.SITE_WINDOW : winmask.SITE_WINDOW + 8]), m, c, n

    def test_frame_hook_switches_site(self):
        # 창이 하나도 없으면 원판 8B, 하나라도 켜져 있으면 스텁 먼 호출 8B — 프레임당 한 번(마스터 11-20 「버린다」: 스프라이트마다 먼 호출은 +1줄/스프라이트)
        for slots, want in (([], winmask.SITE_OLD), ([0], winmask.site_new()), ([2], winmask.site_new()), ([1, 3], winmask.site_new())):
            site, m, c, n = self._run_frame_hook(slots)
            self.assertEqual(site, want, slots)
            self.assertEqual(m[0xF7], 0)  # 원래 자리의 `STA $F7`
            self.assertEqual(c.a, 0)  # 원래 자리의 `LDA #0`
            self.assertLess(n, 80)
            # 사본 장치: 창이 있으면 「이번 프레임에 본 개체」를 지우고, 창이 없으면 서명을 못 쓰게 한다(다음 창에서 처음부터)
            self.assertEqual((m[sprmask.FLAG], m[sprmask.SIG + 5]), (0, 0xA9) if slots else (4, 0), slots)
        # MPR5 가 0x69 가 아니면(타이틀·파일 선택) 사이트를 건드리지 않는다 — 다른 뱅크를 덮으면 멈춘다
        site, m, c, _ = self._run_frame_hook([0], mpr5=0x6A)
        self.assertEqual(site, b"\xaa" * 8)
        self.assertEqual((m[0xF7], c.a), (0, 0))  # 원래 자리의 명령은 그래도 한다
        self.assertEqual(winmask.frame_hook_patch()[2], bytes.fromhex("a90085f70300"))
        self.assertEqual(len(winmask.frame_hook_patch()[3]), 6)

    # ── 어둠 원(종류 0x78~0x81) 조각 — 잘린 그림 사본(`sprmask`)과의 이음 ──
    def _ring_frames(self, desc, bx, by, frames, menu=False, kind=0x7B, f9=0x80):
        """SAT 루프를 프레임 단위로 흉내 — 프레임 후크 → 조각마다 스텁. 프레임마다 [(패턴 워드, 속성 워드)] 와 기계."""
        m = bytearray(0x10000)
        _load(m)
        m[winmask.slot_addr(winmask.SLOT_DLG)] = 1
        for j, v in enumerate(winmask.DLG_BOTTOM):
            m[winmask.slot_addr(winmask.SLOT_DLG, 1 + j)] = v
        if menu:
            m[winmask.slot_addr(winmask.SLOT_MENU)] = 2
            for j, v in enumerate(winmask.MENU_RECT):
                m[winmask.slot_addr(winmask.SLOT_MENU, 1 + j)] = v
        m[0xA400 : 0xA400 + len(desc)] = desc  # 서술자는 `$A000` 창(뱅크 0x69)
        m[0x3509 + 3], m[0x3559 + 3], m[0x36E9 + 3] = kind, f9, 0x05
        c = cpu65.CPU(m)
        c.mpr[5] = 0x69
        rnd = random.Random(7)
        for k in range(sprmask.POOL_CELL * 64):
            c.vram[k] = rnd.getrandbits(16)
        out, cost = [], []
        for _ in range(frames):
            nf = c.run(winmask.labels()["frame_hook"])
            m[0x2E], m[0x2F], m[0x30], m[0x31] = bx & 0xFF, bx >> 8, by & 0xFF, by >> 8
            m[0xFA], m[0xFB] = 0x00, 0xA4
            row = []
            for k in range(desc[0]):
                dx, dy = desc[1 + 5 * k], desc[2 + 5 * k]
                x = (bx + (dx - 256 if dx > 127 else dx)) & 0xFFFF
                y = (by + (dy - 256 if dy > 127 else dy)) & 0xFFFF
                m[0xFC], m[0xFD], m[0xFE], m[0xFF] = x & 0xFF, x >> 8, y & 0xFF, y >> 8
                m[0x33] = desc[0] - k
                pat, attr, _ = call_stub(c, 3 + 5 * k)
                row.append((pat, attr))
            out.append(row)
            cost.append(nf)
        return out, c, cost

    def test_ring_piece_gets_copy_after_two_frames(self):
        # 16×16 셋: 아래 창 위 모서리에 걸침(사본) · 창 안 통째(뒤) · 창 밖(앞). 첫 두 프레임은 옛 판정(걸치면 통째로 뒤), 셋째부터 사본
        desc = bytes([3, 0, 0, 80, 0, 0x00, 0, 40, 82, 0, 0x08, 0, 0xC0, 84, 0, 0x80])
        out, c, cost = self._ring_frames(desc, 100, 170, 5)
        old = [(80, 0x0005), (82, 0x0805), (84, 0x8085)]  # 걸친 조각·안쪽 조각은 우선순위 꺼짐 · 밖은 그대로
        self.assertEqual(out[0], old)
        self.assertEqual(out[1], old)
        pres = list(c.m[sprmask.PRES : sprmask.PRES + 4])
        self.assertEqual(pres[1:3], [1, 2])
        self.assertGreaterEqual(pres[3], 0x80)
        new = [(0x100 | pres[3] & 0x7F, 0x0085), (82, 0x0805), (84, 0x8085)]  # 사본은 앞(우선순위 켬) + 패턴만 사본 · 속성 높은 바이트(뒤집기)는 그대로
        for f in (2, 3, 4):
            self.assertEqual(out[f], new, f)
        self.assertEqual(c.m[sprmask.PCUR], 0)
        self.assertLess(cost[4], 80)  # 다 구운 뒤 프레임 후크는 계획자를 안 부른다(정지 중 비용 0)
        # 사본 셀 = 원본 셀 40 에서 창 쪽(y ≥ 176 → 조각 안 6줄째부터)을 지운 것
        cell = (0x100 | pres[3] & 0x7F) >> 1
        want = list(c.vram)
        sprmask.ref_plan(desc, 100, 170, [sprmask.WIN_BOTTOM], want)
        self.assertEqual(c.vram[cell * 64 : cell * 64 + 64], want[cell * 64 : cell * 64 + 64])
        self.assertNotEqual(c.vram[cell * 64 : cell * 64 + 64], c.vram[40 * 64 : 40 * 64 + 64])

    def test_ring_without_priority_bit_keeps_behind(self):
        # 개체 우선순위 비트가 꺼져 있으면(`$3559` 비트 7 = 0) 사본도 「앞」 조각도 뒤 그대로 — 스텁이 켜지 않는다
        desc = bytes([2, 0, 0, 80, 0, 0x00, 0, 0xC0, 84, 0, 0x00])
        out, _c, _ = self._ring_frames(desc, 100, 170, 4, f9=0x00)
        self.assertTrue(all(attr & 0x80 == 0 for row in out for _, attr in row), out)
        self.assertEqual(out[3][0][0] & 0x100, 0x100)

    def test_ring_moving_stays_on_old_judgement(self):
        # 걷는 동안(프레임마다 기준 좌표가 바뀐다)은 계획이 안 선다 — 늘 옛 판정(통째로 뒤), 풀도 안 쓴다
        desc = bytes([1, 0, 0, 80, 0, 0x00])
        m_out = []
        for bx in (100, 101, 102, 103):
            out, _c, _ = self._ring_frames(desc, bx, 170, 1)
            m_out.append(out[0][0])
        self.assertTrue(all(v == (80, 0x0005) for v in m_out), m_out)

    def test_ring_two_entities_never_share_plan(self):
        # 어둠 원 개체가 둘이면 서로 서명을 갈아 치운다 → 둘 다 늘 옛 판정(틀린 사본을 끼우느니 폴백)
        desc = bytes([1, 0, 0, 80, 0, 0x00])
        m = bytearray(0x10000)
        _load(m)
        m[winmask.slot_addr(winmask.SLOT_DLG)] = 1
        for j, v in enumerate(winmask.DLG_BOTTOM):
            m[winmask.slot_addr(winmask.SLOT_DLG, 1 + j)] = v
        m[0xA400 : 0xA400 + len(desc)] = desc
        c = cpu65.CPU(m)
        c.mpr[5] = 0x69
        for _ in range(6):
            c.run(winmask.labels()["frame_hook"])
            for ent, bx in ((3, 100), (9, 60)):
                m[0x3509 + ent], m[0x3559 + ent], m[0x36E9 + ent] = 0x7B, 0x80, 0x05
                m[0x2E], m[0x2F], m[0x30], m[0x31] = bx, 0, 170, 0
                m[0xFA], m[0xFB], m[0x33] = 0x00, 0xA4, 1
                m[0xFC], m[0xFD], m[0xFE], m[0xFF] = bx, 0, 170, 0
                c.sel, c.mawr, m[0xF9] = 2, SAT0, 0
                c.x, c.y = ent, 3
                c.run(winmask.labels()["stub"])
                self.assertEqual((c.vram[SAT0], c.vram[SAT0 + 1]), (80, 0x0005))
        self.assertEqual(c.m[sprmask.PCUR], 0)

    def test_ring_window_change_rebuilds(self):
        # 창 상태가 바뀌면(메뉴가 뜬다) 사본을 버리고 다시 굽는다 — 그 사이 두 프레임은 옛 판정
        desc = bytes([1, 0, 0, 80, 0, 0x00])
        out, c, _ = self._ring_frames(desc, 100, 170, 4)
        self.assertEqual(out[3][0][0] & 0x100, 0x100)
        c.m[winmask.slot_addr(winmask.SLOT_MENU)] = 2
        for j, v in enumerate(winmask.MENU_RECT):
            c.m[winmask.slot_addr(winmask.SLOT_MENU, 1 + j)] = v
        got = []
        for _ in range(4):
            c.run(winmask.labels()["frame_hook"])
            c.m[0xFA], c.m[0xFB], c.m[0x33] = 0x00, 0xA4, 1
            got.append(call_stub(c, 3)[0])
        self.assertEqual([g & 0x100 for g in got], [0, 0, 0x100, 0x100])


if __name__ == "__main__":
    unittest.main()
