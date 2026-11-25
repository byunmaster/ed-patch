"""구조 대조 검사(struct_check) 회귀 — 가짜 모듈(원판 바이트 아님)로 검사가 실제로 우는지."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scene
import struct_check as SC


def module(body: bytes) -> bytes:
    """`lea 스트림(pc),a1; rts` 뿌리 하나 + 스트림 하나(가짜 가나 글자). 스트림 시작 = 0x20."""
    code = b"\x43\xfa\x00\x1a\x4e\x75"  # lea $20(pc),a1 (확장 워드 위치 2 + 0x1A = 0x1C?) — 아래서 맞춘다
    pad = b"\x00" * (0x20 - len(code))
    return code + pad + body


KANA = b"\x82\xa0\x82\xa2\x82\xa4"  # あいう


class StructCheck(unittest.TestCase):
    def pair(self, o: bytes, n: bytes):
        # 뿌리 lea 변위를 0x20 으로 맞춘다 — 확장 워드 위치 2, 변위 = 0x20 - 4
        fix = lambda m: m[:2] + b"\x00\x1e" + m[4:]  # noqa: E731
        return SC.compare_module(fix(module(o)), fix(module(n)), "fake")

    def test_same_stream_passes(self):
        body = KANA + b"\x01" + KANA + b"\x05" + KANA + b"\x06"
        c, _t, _u, bad, _a = self.pair(body, body)
        self.assertGreaterEqual(c, 1)  # 스트림을 실제로 대조했다(0건이면 검사가 안 본 것)
        self.assertEqual(bad, [])

    def test_layout_changes_are_free(self):
        o = KANA + b"\x01" + KANA + b"\x06"
        n = KANA + b"\x01" + KANA + b"\x05" + KANA + b"\x01" + b"\x06"  # 쪽·줄 나눔은 번역이 바꾼다
        _c, _t, _u, bad, _a = self.pair(o, n)
        self.assertEqual(bad, [])

    def test_changed_end_code_fails(self):
        o = KANA + b"\x01" + KANA + b"\x06"
        n = KANA + b"\x01" + KANA + b"\x07"  # 종결 코드가 바뀌었다
        c, _t, _u, bad, _a = self.pair(o, n)
        self.assertGreaterEqual(c, 1)
        self.assertEqual(len(bad), 1)

    def test_padding_byte_before_end_fails(self):
        o = KANA + b"\x01" + KANA + b"\x06"
        n = KANA + b"\x01" + KANA + b"\xff\xff\x06"  # 끝 앞의 채움 바이트(ss-ed3 10-21 꼴) — 제어 코드로 읽힌다
        c, _t, _u, bad, _a = self.pair(o, n)
        self.assertGreaterEqual(c, 1)
        self.assertEqual(len(bad), 1)

    def test_inbound_target_overwritten_by_stub_fails(self):
        # 글 A 끝으로 들어오는 점프의 목표(종료 바이트 06)를 다른 쪽이 점프 스텁으로 덮었다 — 목표 바이트 검사(pce-ed1 10-22 꼴)
        o = KANA + b"\x0f\x00\x02" + b"\x06" + b"\x00" * 4
        n = KANA + b"\x0f\x00\x02" + b"\x0f\x00\x01" + b"\x06" + b"\x00"
        _c, _t, _u, bad0, _a = self.pair(o, o)
        self.assertEqual(bad0, [])
        _c, _t, _u, bad, _a = self.pair(o, n)
        self.assertTrue(any(b[3] == 0 and b[4] == [("end", 6)] for b in bad))

    def test_dropped_goto_fails(self):
        o = KANA + b"\x0f\x00\x04" + b"\x00\x00" + KANA + b"\x06"  # goto 다음 글 스트림
        n = KANA + b"\x06"  # 호출·분기가 사라졌다
        _c, _t, _u, bad, _a = self.pair(o, n)
        self.assertGreaterEqual(len(bad), 1)

    def test_cols_drops_text_and_layout_only(self):
        st = scene.parse_stream(KANA + b"\x01" + KANA + b"\x05" + b"\x06", 0)
        self.assertEqual(SC.cols(st.tokens), [("end", 6)])

def fake_block(names: list[bytes]) -> bytearray:
    """레코드 둘(0x0C 부터 0x40 간격, 이름 +0x30 에 06 종결)만 있는 가짜 전투 블록."""
    end = 0x0C + 0x40 * len(names)
    b = bytearray(end + 4)
    b[0:12] = (0x0C).to_bytes(2, "big") + end.to_bytes(2, "big") + bytes(8)
    for i, nm in enumerate(names):
        at = 0x0C + 0x40 * i + 0x30
        b[at : at + len(nm) + 1] = nm + b"\x06"
    return b


class PadCheck(unittest.TestCase):
    def test_same_and_shorter_zeroed_pass(self):
        a = fake_block([KANA, KANA])
        b = bytearray(a)
        at = 0x0C + 0x30
        b[at : at + 7] = b"\x82\xa0\x06" + bytes(4)  # 짧아지고 원판 꼬리를 0 으로 — 통과
        self.assertEqual(SC.record_pad_problems(bytes(a), bytes(a), 0), [])
        self.assertEqual(SC.record_pad_problems(bytes(a), bytes(b), 0), [])

    def test_stale_tail_fails(self):
        a = fake_block([KANA, KANA])
        b = bytearray(a)
        at = 0x0C + 0x30
        b[at : at + 3] = b"\x82\xa0\x06"  # 원판 꼬리(い う)가 남았다
        self.assertEqual(len(SC.record_pad_problems(bytes(a), bytes(b), 0)), 1)

    def test_empty_slot_flip_and_head_change_fail(self):
        a = fake_block([KANA, b"\x82\xa0"])
        a[0x0C + 0x40 + 0x30] |= 0x80  # 빈 슬롯
        b = bytearray(a)
        b[0x0C + 0x40 + 0x30] &= 0x7F  # 채운 칸으로 뒤집힘 — 빈 슬롯이 다음 이름을 읽는 부류
        self.assertEqual(len(SC.record_pad_problems(bytes(a), bytes(b), 0)), 1)
        c = bytearray(a)
        c[0x0C + 5] = 1
        self.assertEqual(len(SC.record_pad_problems(bytes(a), bytes(c), 0)), 1)


if __name__ == "__main__":
    unittest.main()
