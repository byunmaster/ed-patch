"""문자열 안쪽 쓰기 보정의 오탐 거르기(`systext._inside_operand`) — 원본 없이 가짜 뱅크로 돈다.
10-16 실사고: `99 EE E7 60`(= `STA $E7EE,Y · RTS`)의 `EE E7 60` 을 `INC $60E7`(문자열 안쪽 쓰기)로 오인해 코드 두 바이트를 고쳐 썼다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import systext


def _bank() -> bytes:
    """`JSR` 대상이 여럿 붙는 가짜 뱅크 — 대상마다 `LDA #1 · STA $E7EE,Y · RTS`(오탐 꼴) 뒤에 진짜 `STA $6332` 가 이어진다."""
    d = bytearray(b"\xea" * 8192)  # NOP 로 채운다
    pos = 0x100
    starts = []
    for _ in range(6):
        starts.append(pos)
        d[pos : pos + 6] = bytes([0xA9, 0x01, 0x99, 0xEE, 0xE7, 0x60])  # LDA #1 ; STA $E7EE,Y ; RTS
        d[pos + 6 : pos + 9] = bytes([0x8D, 0x32, 0x63])  # STA $6332 (진짜 쓰기)
        d[pos + 9] = 0x60
        pos += 0x20
    # 대상들을 부르는 호출부
    for i, st in enumerate(starts):
        d[0x10 + 3 * i : 0x13 + 3 * i] = bytes([0x20, (0x6000 + st) & 0xFF, (0x6000 + st) >> 8])
    return bytes(d)


class InsideOperand(unittest.TestCase):
    def test_피연산자_바이트는_안쪽_쓰기가_아니다(self):
        d = _bank()
        # 두 번째 묶음의 `EE`(= `99 EE E7` 의 피연산자 첫 바이트)
        self.assertTrue(systext._inside_operand(d, 0x120 + 3))

    def test_진짜_쓰기_명령은_남긴다(self):
        d = _bank()
        self.assertFalse(systext._inside_operand(d, 0x120 + 6))  # `8D 32 63`

    def test_확실한_시작이_없으면_옛_동작(self):
        d = bytes(8192)
        self.assertFalse(systext._inside_operand(d, 0x200))


if __name__ == "__main__":
    unittest.main()
