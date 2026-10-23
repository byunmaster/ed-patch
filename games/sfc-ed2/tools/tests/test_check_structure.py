"""구조 대조 검사 회귀 — 가짜 바이트로 만든 원본·빌드 사본에서 제어 코드 한 바이트가 어긋나면 검사가 **실제로 우는지** 본다(원본 데이터를 옮기지 않는다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import check_structure as C
import common

# 가짜 롬: 뱅크 $C2(파일 0x20000~) 한 곳에 메시지 하나. 글자는 전각 2바이트 코드(`80 xx`) — 토큰 문법만 맞으면 된다.
A = 0x20000
GAP = b"\x00"


def fake_src() -> bytearray:
    d = bytearray(b"\xff" * 0x60000)
    # 구간(a..b): [화자 색 1E] 글 [색 복귀 04] 줄바꿈 글 쪽 넘김 글  — 뒤에 구조 토큰(끝 `00`)
    seg = bytes([0x1E, 0x80, 0x41, 0x04, 0x01, 0x80, 0x42, 0x05, 0x80, 0x43])
    d[A : A + len(seg)] = seg + GAP
    return d


B = A + 10  # 구간 끝(원문)


class Follow(unittest.TestCase):
    def check(self, rom):
        return C.check_segment(bytes(fake_src()), bytes(rom), A, B)

    def test_in_place_same_passes(self):
        self.assertTrue(self.check(fake_src())["ok"])

    def test_short_translation_padded_passes(self):
        rom = fake_src()
        rom[A : A + 10] = bytes([0x1E, 0x80, 0x41, 0x04, 0x05, 0x80, 0x44, 0x16, 0x16, 0x16])  # 같은 제어 열 [1E 04 05] + 채움
        src = bytes(fake_src())
        d = bytearray(src)
        d[A : A + 10] = bytes([0x1E, 0x80, 0x41, 0x04, 0x05, 0x80, 0x42, 0x80, 0x43, 0x80])
        r = C.check_segment(bytes(d), bytes(rom), A, B)
        self.assertTrue(r["ok"], r["why"])
        self.assertEqual(r["pad"], 3)

    def test_ff_padding_fails(self):
        rom = fake_src()
        rom[A + 7 : A + 10] = b"\xff\xff\xff"  # 채움이 `$16` 이 아니라 `FF` — 문법 밖(엔진이 다음 호출을 못 읽는다)
        self.assertFalse(self.check(rom)["ok"])

    def test_changed_control_byte_fails(self):
        rom = fake_src()
        rom[A + 7] = 0x02  # 쪽 넘김 `05` → 키 대기 `02`
        r = self.check(rom)
        self.assertFalse(r["ok"])
        self.assertIn("제어 코드 열", r["why"])

    def test_dropped_control_fails(self):
        rom = fake_src()
        rom[A + 3] = 0x16  # 색 복귀 `04` 를 빈 토큰으로 — 원문 열에서 빠진다
        self.assertFalse(self.check(rom)["ok"])

    def test_token_straddling_end_fails(self):
        rom = fake_src()
        rom[A + 8], rom[A + 9] = 0x16, 0x80  # 마지막 바이트가 2바이트 글자 코드의 앞 — 토큰이 구간 끝을 넘는다
        self.assertFalse(self.check(rom)["ok"])


class Tramp(unittest.TestCase):
    def build(self, ret=None, body=None):
        src = fake_src()
        rom = bytearray(src) + bytearray(b"\xff" * 0x1000)
        fa = common.off2snes(len(src))  # 새 자리(확장 영역 첫머리)
        body = body if body is not None else bytes([0x1E, 0x80, 0x41, 0x04, 0x01, 0x80, 0x42, 0x05, 0x80, 0x43, 0x80, 0x44])  # 글자가 늘었다
        rb = common.off2snes(B) if ret is None else ret
        rom[len(src) : len(src) + len(body) + 4] = body + bytes([0x17, rb & 0xFF, (rb >> 8) & 0xFF, rb >> 16])
        rom[A : A + 4] = bytes([0x17, fa & 0xFF, (fa >> 8) & 0xFF, fa >> 16])
        rom[A + 4 : B] = bytes([0x16]) * (B - A - 4)
        return bytes(src), bytes(rom)

    def test_tramp_passes(self):
        src, rom = self.build()
        r = C.check_segment(src, rom, A, B)
        self.assertTrue(r["ok"], r["why"])
        self.assertEqual(r["kind"], "옮김")

    def test_wrong_return_address_fails(self):
        src, rom = self.build(ret=common.off2snes(B + 1))  # 다음 토큰을 한 바이트 건너뛰는 복귀
        r = C.check_segment(src, rom, A, B)
        self.assertFalse(r["ok"])
        self.assertIn("복귀", r["why"])

    def test_added_page_break_is_allowed_other_control_is_not(self):
        src, rom = self.build(body=bytes([0x1E, 0x80, 0x41, 0x04, 0x01, 0x80, 0x42, 0x05, 0x80, 0x43, 0x05, 0x80, 0x44]))
        r = C.check_segment(src, rom, A, B)
        self.assertTrue(r["ok"], r["why"])
        self.assertEqual(r["added05"], 1)
        src, rom = self.build(body=bytes([0x1E, 0x80, 0x41, 0x04, 0x01, 0x80, 0x42, 0x05, 0x80, 0x43, 0x02, 0x80, 0x44]))  # 키 대기 `02` 추가 — 원문에 없다
        self.assertFalse(C.check_segment(src, rom, A, B)["ok"])


class Seq(unittest.TestCase):
    def test_diff_seq(self):
        self.assertEqual(C.diff_seq([0x1E, 0x04], [0x1E, 0x04, 0x05]), (True, 1))
        self.assertEqual(C.diff_seq([0x1E, 0x04], [0x1E, 0x02, 0x04]), (False, 0))
        self.assertEqual(C.diff_seq([0x1E, 0x04, 0x05], [0x1E, 0x04]), (False, 0))


class Ledger(unittest.TestCase):
    def test_extension_write_outside_ledger_fails(self):
        rom = bytearray(b"\xff" * (common.ROM_SIZE + 0x40000))
        rom[common.ROM_SIZE + 0x20000 : common.ROM_SIZE + 0x20004] = b"\x01\x02\x03\x04"  # 장부에 없는 새 쓰기(글꼴 영역 밖)
        self.assertTrue(C.check_extension(bytes(rom), []))
        cov = [{"key": "$C20000", "kind": "옮김", "orig": 0xC20000, "new": common.off2snes(common.ROM_SIZE + 0x20000), "n_new": 4}]
        self.assertEqual(C.check_extension(bytes(rom), cov), [])

    def test_ledger_mismatch_detected(self):
        row = {"a": A, "b": B, "kind": "옮김", "ok": True, "pad": 0, "added05": 0, "why": ""}
        self.assertTrue(C.check_ledger([row], []))  # 롬엔 옮김이 있는데 장부에 없다
        self.assertEqual(C.check_ledger([row], [{"key": "$C20000", "kind": "옮김", "orig": 0, "new": 1, "n_new": 1}]), [])


class JumpTarget(unittest.TestCase):
    """다른 메시지의 끝 점프가 들어오는 바이트(종료 바이트)가 스텁에 덮이면 우는가."""

    T = A + 0x100

    def srcs(self):
        d = fake_src()
        d[A : A + 10] = bytes([0x80, 0x41, 0x0F, 0x02, 0x01, 0x80, 0x42, 0x80, 0x43, 0x80])  # 글 · 점프(→ T+2 = 종료 바이트) · 글
        d[A + 10] = 0x00
        d[self.T : self.T + 3] = bytes([0x80, 0x44, 0x00])  # 점프가 들어오는 자리: 글 · 끝 `00`
        return bytes(d)

    def run_outside(self, rom):
        src = self.srcs()
        return C.check_outside(src, bytes(rom), [(A, A + 11)], [])[1]

    def test_target_unchanged_passes(self):
        self.assertEqual(self.run_outside(self.srcs()), [])

    def test_target_terminator_overwritten_fails(self):
        rom = bytearray(self.srcs())
        rom[self.T + 2] = 0x17  # 종료 바이트 `00` 이 다른 메시지의 트램펄린 스텁 `17` 에 덮였다
        bad = self.run_outside(rom)
        self.assertTrue(any("종료 바이트 덮임" in w for _, w in bad), bad)



if __name__ == "__main__":
    unittest.main()
