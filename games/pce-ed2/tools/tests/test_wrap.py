"""전투 로그 어절 줄바꿈 훅의 논리 — 시뮬레이터(원본·에뮬 없이). 어절 폭 · 한계 · 표지 · 이름 폭."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sim6280
import wrap

MK = bytes([0x13, 0x84])  # 버퍼는 이름 토큰으로 시작한다
NL_COUNT = 0xFA  # 스텁 `$4812` 가 줄 넘김 횟수를 센다


def machine(text: bytes, x: int, width_tiles: int = wrap.LOG_WIN[2], name: bytes = b"", start: int = 1):
    """`text` = 작업 버퍼($30E5)의 내용, `$7C` 는 공백 바로 뒤(`pos` 는 호출 쪽이 정한다)."""
    b68 = bytearray(b"\xff" * 8192)
    # $5021 스텁: LDA ($7C); TAX; INC $7C; BNE +2; INC $7D; TXA; RTS
    b68[0x1021 : 0x1021 + 11] = bytes([0xB2, 0x7C, 0xAA, 0xE6, 0x7C, 0xD0, 0x02, 0xE6, 0x7D, 0x8A, 0x60])
    # $4812 스텁: 줄 넘김 횟수 +1, 반환 주소를 BIT(3바이트) 뒤로
    b68[0x0812 : 0x0812 + 13] = bytes([0xE6, NL_COUNT, 0x68, 0x18, 0x69, 0x03, 0xAA, 0x68, 0x69, 0x00, 0x48, 0xDA]) + b"\x60"
    b71 = bytearray(b"\xff" * 8192)
    c = wrap.code()
    b71[wrap.CODE_OFF : wrap.CODE_OFF + len(c)] = c
    ram = bytearray(8192)
    sim = sim6280.Sim({0x68: b68, 0x71: b71, 0x87: bytearray(8192)}, [0xFF, 0xF8, 0x68, 0x71, 0x75, 0x76, 0x77, 0x87], ram)
    ram[0x73] = x
    ram[0x77], ram[0x78], ram[0x79], ram[0x7A] = wrap.LOG_WIN[0], wrap.LOG_WIN[1], width_tiles, wrap.LOG_WIN[3]
    ram[wrap.LINE_START - 0x2000] = start
    for i, v in enumerate(text):
        ram[wrap.BUF - 0x2000 + i] = v
    for i, v in enumerate(name + b"\x00"):
        sim.banks[0x87][wrap.NAME_BUF - 0xE000 + i] = v
    return sim


G = lambda n: bytes([0xF0, 0x30]) * n  # 2바이트 글리프 n 개 = 3n 단위  # noqa: E731


def run_space(text: bytes, x: int, **kw):
    """공백 훅 — 버퍼 `text` 의 첫 바이트 = 표지, 공백(`60`) 다음 위치에서 호출."""
    sim = machine(text, x, **kw)
    pos = wrap.BUF + 1 + text[1:].index(0x60) + 1  # 첫 공백 바로 뒤
    sim.ram[0x7C], sim.ram[0x7D] = pos & 0xFF, pos >> 8
    r = sim.run(wrap.labels()["space"])
    return r, sim.ram[NL_COUNT], (sim.ram[0x7C] | sim.ram[0x7D] << 8) - pos


class WrapTest(unittest.TestCase):
    def test_fits_goes_original(self):
        text = MK + G(2) + b"\x60" + G(3) + b"\x00"  # x=7 + 공백 + 9 = 17 ≤ 43
        r, nl, moved = run_space(text, 7)
        self.assertEqual((r, nl, moved), (wrap.SPACE_ORIG, 0, 0))

    def test_overflow_newline(self):
        text = MK + G(2) + b"\x60" + G(4) + b"\x00"  # x=33 + 1 + 12 = 46 > 43
        r, nl, moved = run_space(text, 33)
        self.assertEqual((r, nl, moved), (-1, 1, 0))  # 훅이 줄을 넘기고 RTS — 스트림 포인터는 그대로

    def test_boundary_exact_fit(self):
        text = MK + G(1) + b"\x60" + G(4) + b"\x00"  # x=30 + 1 + 12 = 43 = 한계 → 들어간다
        self.assertEqual(run_space(text, 30)[:2], (wrap.SPACE_ORIG, 0))
        self.assertEqual(run_space(text, 31)[:2], (-1, 1))  # 44 > 43

    def test_other_window_never_wraps(self):
        text = MK + G(2) + b"\x60" + G(9) + b"\x00"
        sim = machine(text, 40)
        sim.ram[0x78] = 0x05  # 다른 창(대사창 · 메뉴 …)
        pos = wrap.BUF + 2 + 6 + 1
        sim.ram[0x7C], sim.ram[0x7D] = pos & 0xFF, pos >> 8
        self.assertEqual((sim.run(wrap.labels()["space"]), sim.ram[NL_COUNT]), (wrap.SPACE_ORIG, 0))

    def test_not_buffer_never_wraps(self):
        text = MK + G(2) + b"\x60" + G(9) + b"\x00"
        sim = machine(text, 40)
        sim.ram[0x7C], sim.ram[0x7D] = 0x00, 0x62  # ROM 안의 리터럴 문자열
        self.assertEqual((sim.run(wrap.labels()["space"]), sim.ram[NL_COUNT]), (wrap.SPACE_ORIG, 0))

    def test_line_start_space_kept(self):
        text = MK + G(1) + b"\x60" + G(20) + b"\x00"
        self.assertEqual(run_space(text, 1)[:2], (wrap.SPACE_ORIG, 0))  # x == 줄 머리

    def test_word_ends_at_control(self):
        # 어절 = 글리프 3 · 속성(06 … 04) 폭 0 · 0D 에서 끝 — 다음 줄 글자는 안 센다
        text = MK + G(1) + b"\x60" + G(1) + bytes([0x06]) + G(1) + bytes([0x04, 0x0D]) + G(9) + b"\x00"
        self.assertEqual(run_space(text, 33)[:2], (wrap.SPACE_ORIG, 0))  # 33 + 1 + 6 = 40 ≤ 43
        self.assertEqual(run_space(text, 37)[:2], (-1, 1))  # 44

    def test_color_arg_skipped(self):
        text = MK + G(1) + b"\x60" + bytes([0x15, 0x82]) + G(1) + bytes([0x14]) + b"\x00"
        self.assertEqual(run_space(text, 39)[:2], (wrap.SPACE_ORIG, 0))  # 39 + 1 + 3 = 43

    def test_narrow_window(self):
        old = wrap.LOG_WIN
        wrap.LOG_WIN = (old[0], old[1], 10, old[3])  # 창 폭이 다르면 한계도 따라간다(한계 2*10-1 = 19)
        try:
            text = MK + G(1) + b"\x60" + G(2) + b"\x00"
            self.assertEqual(run_space(text, 12, width_tiles=10)[:2], (wrap.SPACE_ORIG, 0))  # 12+6=18 < 19
            self.assertEqual(run_space(text, 13, width_tiles=10)[:2], (-1, 1))  # 19 ≥ 19
        finally:
            wrap.LOG_WIN = old


def run_name(text: bytes, x: int, name: bytes, **kw):
    """이름 훅 — 이어질 글(`text` 의 이름 토큰 뒤)의 포인터는 소프트웨어 스택에 있고, `$7C` 는 이미 이름 쪽(여기선 엉뚱한 값)이다."""
    sim = machine(text, x, name=name, **kw)
    pos = wrap.BUF + 2  # 이름 토큰(`13 nn`) 바로 뒤
    sim.ram[wrap.SSP] = 4
    st = wrap.SSTACK - 0xE000
    sim.banks[0x87][st : st + 4] = bytes([pos >> 8, pos & 0xFF, 0, 0])  # `$7D $7C $2C0B $2C07`
    sim.ram[0x7C], sim.ram[0x7D] = 0x97, 0x6F
    r = sim.run(wrap.labels()["name"])
    return r, sim.ram[NL_COUNT], sim.ram[0x7C]


class NameTest(unittest.TestCase):
    NAME = bytes([0x15, 0x82]) + G(4) + bytes([0x14])  # 이름 = 12 단위(색 제어는 폭 0)
    TEXT = MK + G(1) + b"\x60" + G(3) + b"\x00"  # 이름 뒤에 글리프 1개(3)가 붙고 공백에서 끝 → 폭 15

    def test_fits(self):
        self.assertEqual(run_name(self.TEXT, 28, self.NAME)[:2], (-1, 0))  # 28+15 = 43 < 44

    def test_overflow_breaks_before_name(self):
        r = run_name(self.TEXT, 29, self.NAME)  # 44 ≥ 44
        self.assertEqual(r[:2], (-1, 1))
        self.assertEqual(r[2], wrap.NAME_BUF & 0xFF)  # 원래 명령(`LDA #$8E; STA $7C`)을 대신 해 준다

    def test_line_start_name_kept(self):
        self.assertEqual(run_name(self.TEXT, 1, self.NAME)[:2], (-1, 0))

    def test_other_window(self):
        self.assertEqual(run_name(self.TEXT, 40, self.NAME, **{})[:2], (-1, 1))  # 기준: 로그 창이면 넘긴다
        sim = machine(self.TEXT, 40, name=self.NAME)
        sim.ram[0x77] = 9
        sim.ram[wrap.SSP] = 4
        st = wrap.SSTACK - 0xE000
        sim.banks[0x87][st : st + 4] = bytes([wrap.BUF >> 8, (wrap.BUF + 2) & 0xFF, 0, 0])
        self.assertEqual(sim.run(wrap.labels()["name"]), -1)
        self.assertEqual(sim.ram[NL_COUNT], 0)

    def test_rom_stream_in_log_window(self):
        """이어질 글이 ROM 문자열이어도 창이 전투 로그 창이면 켠다(플레이어 공격 로그 「…에게 11의 피해!!」 — qa 10-20). 다른 창이면 꺼진다(`test_other_window`)."""
        sim = machine(self.TEXT, 40, name=self.NAME)
        sim.ram[wrap.SSP] = 4
        st = wrap.SSTACK - 0xE000
        sim.banks[0x87][st : st + 4] = bytes([0x6B, 0x14, 0, 0])
        self.assertEqual(sim.run(wrap.labels()["name"]), -1)
        self.assertEqual(sim.ram[NL_COUNT], 1)


class AsciiTest(unittest.TestCase):
    def test_ascii_is_two_units(self):
        text = MK + G(1) + b"\x60" + b"A.?" + b"\x00"  # 어절 = 2*3 = 6
        self.assertEqual(run_space(text, 36)[:2], (wrap.SPACE_ORIG, 0))  # 36+6 = 42 < 43
        self.assertEqual(run_space(text, 37)[:2], (-1, 1))  # 43 ≥ 43
