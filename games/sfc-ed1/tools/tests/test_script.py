"""스크립트 모델 — **원본 없이** 돈다. 라벨로 풀었다 되쓰는 규칙과 옮겨 쓸 때의 오프셋 재계산을 못 박는다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text  # noqa: F401, I001  (common 보다 먼저 — shared/text 와 이름이 겹친다)
import common
import script


def rom_with(block: bytes, at: int) -> bytes:
    rom = bytearray(0x100000)
    rom[at : at + len(block)] = block
    return bytes(rom)


class RoundTrip(unittest.TestCase):
    def test_원자리_되쓰기는_바이트_동일(self):
        # 글자 · 사전 · FA rel16(+5) · FC rel16 · END
        blk = bytes([0x11, 0xD0, 0x03, 0xFA, 0x05, 0x00, 0x12, 0xE0, 0x13, 0xFC, 0xFA, 0xFF, 0xE0])
        at = common.snes2off(0x078100)
        rom = rom_with(blk, at)
        items = script.parse_region(rom, at, at + len(blk))
        self.assertEqual(script.emit(items, script.identity_place(items)), blk)
        # FA 는 +5 → 0x13 자리, FC 는 -6 → 0x13 자리(자기 앞)
        fa = next(it for it in items if it.code == 0xFA)
        self.assertEqual(fa.targets, [at + 3 + 5])

    def test_옮겨_쓰면_rel16_이_다시_계산된다(self):
        blk = bytes([0xFA, 0x03, 0x00, 0x11, 0x12, 0xE0])  # FA → +3 (0x11)
        at = common.snes2off(0x078100)
        rom = rom_with(blk, at)
        items = script.parse_region(rom, at, at + len(blk))
        # 앞에 4바이트를 끼워 넣은 듯 목표만 뒤로 밀린 배치
        place = {it.off: it.off for it in items}
        for it in items[1:]:
            place[it.off] += 4
        out = script.emit(items, place)
        self.assertEqual(out[:3], bytes([0xFA, 0x07, 0x00]))

    def test_F9_절대_호출은_새_주소로(self):
        blk = bytes([0xF9, 0x00, 0x00, 0x00, 0xE0, 0x11, 0xE0])
        at = common.snes2off(0x078100)
        rom = bytearray(rom_with(blk, at))
        tgt = at + 5
        rom[at + 1 : at + 4] = common.off2snes(tgt).to_bytes(3, "little")
        items = script.parse_region(bytes(rom), at, at + len(blk))
        place = {it.off: it.off for it in items}
        place[tgt] = common.snes2off(0x098000)
        out = script.emit(items, place)
        self.assertEqual(out[1:4], (0x098000).to_bytes(3, "little"))

    def test_뱅크를_넘는_rel16_은_거부한다(self):
        blk = bytes([0xFA, 0x03, 0x00, 0x11, 0x12, 0xE0])
        at = common.snes2off(0x078100)
        items = script.parse_region(rom_with(blk, at), at, at + len(blk))
        place = {it.off: it.off for it in items}
        place[at + 3] = common.snes2off(0x088000)
        with self.assertRaises(AssertionError):
            script.emit(items, place)

    def test_FD_죽은_슬롯은_원값_유지(self):
        # FD o0..o4: o0 만 항목 시작(+6 → 0x11), 나머지는 쓰레기
        blk = bytes([0xFD, 0x06, 0x99, 0x98, 0x97, 0x96, 0x11, 0xE0])
        at = common.snes2off(0x078100)
        items = script.parse_region(rom_with(blk, at), at, at + len(blk))
        fd = items[0]
        self.assertEqual(fd.dead, {1, 2, 3, 4})
        place = {it.off: it.off for it in items}
        for it in items[1:]:
            place[it.off] += 2
        out = script.emit(items, place)
        self.assertEqual(out[:6], bytes([0xFD, 0x08, 0x99, 0x98, 0x97, 0x96]))


if __name__ == "__main__":
    unittest.main()
